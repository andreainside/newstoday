# backend/scripts/cluster_events_live.py
from __future__ import annotations


import sys
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, UTC
from typing import List, Optional, Tuple, Set

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.services.title_similarity import explain_jaccard, fuzz_token_set_ratio

# Avoid Windows console encoding crashes during logging (e.g., GBK can't encode some chars).
# We prefer replacing unencodable glyphs rather than aborting a write transaction.
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(errors="replace")
except Exception:
    pass

LOOKBACK_HOURS = 240
CANDIDATE_WINDOW_HOURS = 48

FUZZ_ACCEPT = 85.0
FUZZ_MAYBE = 60.0
JACCARD_MAYBE = 0.20
TIME_NEAR_HOURS = 6

# ===== Phase 2.1 Retrieval Control (Top-M articles -> Top-N events) =====
RETR_WINDOW_DAYS = 7
TOP_M_ARTICLES = 2000
TOP_N_EVENTS = 20
MAX_ARTICLES_PER_EVENT = 20
VEC_MERGE_SIM = 0.62



# ==============================================

MAX_ARTICLES = int(os.getenv("CLUSTER_MAX_ARTICLES", "300"))            # 瀹夊叏闃€锛氭渶澶氬鐞嗗灏戠瘒
DO_WRITE_DEFAULT = False     # 榛樿涓嶅啓搴?


@dataclass
class CandidateScore:
    event_id: int
    rep_title: str
    end_time: Optional[datetime]
    fuzz: float
    jaccard: float
    vec_sim: float

def touch_event_on_merge(db, event_id: int, article_time: datetime) -> None:
    """
    MERGE 鎴愬姛鍚庣殑浜嬩欢瀵硅薄缁存姢锛?
    - start_time锛氬彧浼氭洿鏃╋紙min锛?
    - end_time锛氬彧浼氭洿鏅氾紙max锛?
    - last_updated_at锛氭洿鏂颁负 now()
    """
    db.execute(
        text(
            """
            UPDATE events
            SET
              start_time = LEAST(COALESCE(start_time, :t), :t),
              end_time = GREATEST(COALESCE(end_time, :t), :t),
              last_updated_at = now()
            WHERE id = :event_id
            """
        ),
        {"event_id": event_id, "t": article_time},
    )


def get_recent_articles(db: Session, since: datetime, limit: int) -> List[dict]:
    q = text("""
        SELECT a.id, a.source_id, a.title, a.published_at
        FROM articles a
        LEFT JOIN event_articles ea ON ea.article_id = a.id
        WHERE a.published_at >= :since
          AND ea.article_id IS NULL            -- 鍙鐞嗘湭閾炬帴鏂囩珷锛堥伩鍏嶉噸澶嶆壂锛?
          AND a.embedding IS NOT NULL          -- 鍚戦噺鍙洖蹇呴』鏈?embedding
        ORDER BY a.published_at ASC, a.id ASC            -- backlog-safe: oldest unlinked first
        LIMIT :limit;
    """)
    rows = db.execute(q, {"since": since, "limit": limit}).mappings().all()
    return [dict(r) for r in rows]



def get_candidate_events(db: Session, min_end_time: datetime) -> List[dict]:
    q = text("""
        SELECT id, title, representative_title, start_time, end_time, created_at, status
        FROM events
        WHERE end_time IS NULL OR end_time >= :min_end_time
        ORDER BY COALESCE(end_time, created_at) DESC;

    """)
    rows = db.execute(q, {"min_end_time": min_end_time}).mappings().all()
    return [dict(r) for r in rows]



def score_article_to_event(article_title: str, event_rep_title: str) -> Tuple[float, float]:
    fuzz = fuzz_token_set_ratio(article_title, event_rep_title)
    j = explain_jaccard(article_title, event_rep_title).jaccard
    return fuzz, j


def pick_best_event(article: dict, candidates: List[dict], closed_ids: Optional[Set[int]] = None) -> Optional[CandidateScore]:
    best: Optional[CandidateScore] = None
    closed_ids = closed_ids or set()

    for e in candidates:
        if e["id"] in closed_ids:
            continue  # skip closed events

        rep = e["representative_title"] or e["title"]
        fuzz, j = score_article_to_event(article["title"], rep)
        cs = CandidateScore(
            event_id=e["id"],
            rep_title=rep,
            end_time=e["end_time"],
            fuzz=fuzz,
            jaccard=j,
            vec_sim=float(e.get("best_sim", 0.0)),
        )

        if best is None:
            best = cs
        else:
            # 鍏堟瘮鍚戦噺鐩镐技搴︼紝鍐嶆瘮 fuzz
            if (cs.vec_sim, cs.fuzz) > (best.vec_sim, best.fuzz):
                best = cs

    return best




def decide_action(best: Optional[CandidateScore], article_time: datetime, event_end_time: Optional[datetime]) -> str:
    if best is None:
        return "new"
    
    # Phase 2.2A-final: vector strong signal -> merge
    # 0) safety gate: very low lexical overlap + not-very-strong vec => force NEW
    # (鏀惧湪鎵€鏈?vector merge 涔嬪墠锛岄槻姝⑩€滆涔夋硾鐩稿叧鈥濊鍚堝苟)
    if best.vec_sim < 0.74 and best.jaccard <= 0.01 and best.fuzz < 45:
        return "new"

    # 1) strong vector signal -> merge
    if best.vec_sim >= VEC_MERGE_SIM:   # 浠嶇劧鏄?0.62
        return "merge"

    # 2) medium vector signal + light lexical support -> merge
    #    瑕嗙洊澶ч噺 vec鈮?.56~0.61 & fuzz鈮?5~54 鐨勭湡瀹炲悓浜嬩欢
    if best.vec_sim >= 0.54 and best.fuzz >= 45:
        return "merge"


    # 寮哄悎骞?
    if best.fuzz >= FUZZ_ACCEPT:
        return "merge"

    # 鐏板尯锛氶渶瑕佺浜岃瘉鎹?
    if best.fuzz >= FUZZ_MAYBE:
        # 璇佹嵁1锛氬叧閿瘝閲嶅彔
        if best.jaccard >= JACCARD_MAYBE:
            return "merge"

        # 璇佹嵁2锛氭椂闂撮潪甯歌繎锛堟敞鎰?end_time 鍙兘涓?None锛?
        if event_end_time is not None:
            if abs(article_time - event_end_time) <= timedelta(hours=TIME_NEAR_HOURS):
                return "merge"

    return "new"


def create_event(db: Session, title: str, start_time: datetime, end_time: datetime) -> int:
    q = text("""
        INSERT INTO events (title, representative_title, start_time, end_time, created_at, last_updated_at)
        VALUES (:title, :rep, :start_time, :end_time, :created_at, :last_updated_at)
        RETURNING id;
    """)
    now_ts = datetime.now(UTC).replace(tzinfo=None)
    new_id = db.execute(q, {
        "title": title,
        "rep": title,
        "start_time": start_time,
        "end_time": end_time,
        "created_at": now_ts,
        "last_updated_at": now_ts,
    }).scalar_one()
    return int(new_id)


def link_article(db: Session, event_id: int, article_id: int) -> None:
    q = text("""
    INSERT INTO event_articles (event_id, article_id)
    VALUES (:event_id, :article_id)
    ON CONFLICT (article_id) DO NOTHING;
    """)
    db.execute(q, {"event_id": event_id, "article_id": article_id})


def update_event_end_time(db: Session, event_id: int, new_end_time: datetime) -> None:
    q = text("""
        UPDATE events
        SET end_time = GREATEST(COALESCE(end_time, :new_end), :new_end)
        WHERE id = :id;
    """)
    db.execute(q, {"id": event_id, "new_end": new_end_time})

def get_candidate_event_ids_via_vector(
    db: Session,
    query_article_id: int,
    *,
    window_days: int = RETR_WINDOW_DAYS,
    top_m_articles: int = TOP_M_ARTICLES,
    top_n_events: int = TOP_N_EVENTS,
    max_articles_per_event: int = MAX_ARTICLES_PER_EVENT,
) -> dict[int, float]:
    """
    Phase 2.1 retrieval v0:
    1) 鐢?query_article 鐨?embedding 鍦?articles 琛ㄥ彫鍥?Top-M 鐩镐技鏂囩珷锛堝甫鏃堕棿绐?window_days锛?
    2) 閫氳繃 event_articles 鏄犲皠鍒?event_id
    3) 瀵规瘡涓?event 鏈€澶氫繚鐣?max_articles_per_event 绡囪础鐚枃绔狅紙閬垮厤澶т簨浠堕湼姒滐級
    4) 鎸?event 鐨?best similarity 鎺掑簭锛屽彇 Top-N events锛堢‖涓婇檺锛?
    """
    q = text("""
    WITH q AS (
      SELECT id, published_at, embedding
      FROM articles
      WHERE id = :qid AND embedding IS NOT NULL
    ),
    nn_articles AS (
      SELECT a.id AS article_id,
             a.published_at,
             1.0 - (a.embedding <=> q.embedding) AS sim
      FROM q
      JOIN articles a ON a.embedding IS NOT NULL
      WHERE a.id <> q.id
        AND a.published_at >= (q.published_at - (:window_days || ' days')::interval)
        AND a.published_at <= (q.published_at + (:window_days || ' days')::interval)
      ORDER BY a.embedding <=> q.embedding
      LIMIT :top_m
    ),
    mapped AS (
      SELECT ea.event_id,
             nn.article_id,
             nn.sim,
             ROW_NUMBER() OVER (PARTITION BY ea.event_id ORDER BY nn.sim DESC) AS rn
      FROM nn_articles nn
      JOIN event_articles ea ON ea.article_id = nn.article_id
    ),
    capped AS (
      SELECT event_id, sim
      FROM mapped
      WHERE rn <= :max_per_event
    ),
    event_best AS (
      SELECT event_id, MAX(sim) AS best_sim
      FROM capped
      GROUP BY event_id
    )
    SELECT event_id,best_sim
    FROM event_best
    ORDER BY best_sim DESC
    LIMIT :top_n;
    """)

    rows = db.execute(
        q,
        {
            "qid": query_article_id,
            "window_days": window_days,
            "top_m": top_m_articles,
            "top_n": top_n_events,
            "max_per_event": max_articles_per_event,
        },
    ).all()

    return {int(r[0]): float(r[1]) for r in rows}

def fetch_events_by_ids(db: Session, event_ids: List[int]) -> List[dict]:
    if not event_ids:
        return []
    q = text("""
        SELECT id, title, representative_title, start_time, end_time, created_at, status
        FROM events
        WHERE id = ANY(:ids);
    """)
    rows = db.execute(q, {"ids": event_ids}).mappings().all()
    return [dict(r) for r in rows]


def main(do_write: bool = DO_WRITE_DEFAULT) -> None:
    now_utc = datetime.now(UTC)
    since = (now_utc - timedelta(hours=LOOKBACK_HOURS)).replace(tzinfo=None)
    min_end_time = (now_utc - timedelta(hours=CANDIDATE_WINDOW_HOURS)).replace(tzinfo=None)



    db = SessionLocal()
    try:
        articles = get_recent_articles(db, since, limit=MAX_ARTICLES)

        # Phase 2.2A: 涓嶅啀鍏ㄦ壂鍊欓€?events锛堢獥鍙ｅ叏琛級锛岃€屾槸 per-article 鐢ㄥ悜閲忓彫鍥炲緱鍒?Top-N events
        print(f"[mode] {'WRITE' if do_write else 'DRY-RUN'} (A=conservative)")
        print(f"[info] articles since {since.isoformat()} = {len(articles)} (max {MAX_ARTICLES})")
        print(f"[info] retrieval: window_days={RETR_WINDOW_DAYS} top_m_articles={TOP_M_ARTICLES} top_n_events={TOP_N_EVENTS} max_articles_per_event={MAX_ARTICLES_PER_EVENT}")
        print("-" * 80)


        if do_write:
            # 鍐欏簱妯″紡锛氫簨鍔″潡鍐呭叏閮ㄦ垚鍔?-> 鑷姩 commit锛涗腑閫斿紓甯?-> 鑷姩 rollback
            db.rollback()
            with db.begin():
                for i, a in enumerate(articles, start=1):
                    cand_map = get_candidate_event_ids_via_vector(db, a["id"])  # {event_id: best_sim}
                    candidates = fetch_events_by_ids(db, list(cand_map.keys()))
                    for e in candidates:
                        e["best_sim"] = cand_map.get(e["id"], 0.0)
                    closed_ids = {e["id"] for e in candidates if e.get("status") == "closed"}


                    print(f"[retrieval] article_id={a['id']} candidate_events={len(candidates)} (cap={TOP_N_EVENTS})")

                    best = pick_best_event(a, candidates, closed_ids=closed_ids) if candidates else None



                    article_time = a["published_at"]  # timestamp without time zone -> naive datetime
                    action = decide_action(best, article_time, best.end_time if best else None)

                    print(f"{i:02d}. article_id={a['id']}  time={a['published_at']}  title={a['title'][:80]!r}")
                    if best:
                        print(f"    best_event={best.event_id}  vec_sim={best.vec_sim:.3f}  fuzz={best.fuzz:.1f}  jaccard={best.jaccard:.3f}")
                        print(f"    rep_title={best.rep_title[:80]!r}")
                    else:
                        print("    best_event=None")
                    print(f"    DECISION: {action.upper()}")

                    # --- Step 3C.1: 鍙墦鍗扳€滃皢瑕佹洿鏂?鍒涘缓鈥濈殑瀵硅薄缁存姢鍔ㄤ綔锛圖RY-RUN 涓嬩笉鍐欏簱锛?---
                    if action == "merge":
                    # best 涓€瀹氫笉涓?None锛屽惁鍒?decide_action 浼氳繑鍥?"new"
                        print(
                            f"    [will_update] event_id={best.event_id} "
                            f"end_time: {best.end_time} -> {article_time} "
                            f"last_updated_at -> now()"
                        )

                    elif action == "new":
                        print(
                            f"    [will_create] new event "
                            f"start_time={article_time} "
                            f"end_time={article_time} "
                            f"last_updated_at -> now()"
                        )



                    published_at = a["published_at"]
                    if action == "new":
                        new_event_id = create_event(db, a["title"], published_at, published_at)
                        link_article(db, new_event_id, a["id"])

                        # 鏂颁簨浠跺姞鍏?candidates锛屽悗缁枃绔犳墠鏈夋満浼?merge 鍒板畠
                        candidates.insert(
                            0,
                            {
                                "id": new_event_id,
                                "title": a["title"],
                                "representative_title": a["title"],
                                "start_time": published_at,
                                "end_time": published_at,
                                "created_at": datetime.now(UTC).replace(tzinfo=None),
                            },
                        )
                        print(f"    [write] created event_id={new_event_id} + linked article")
                    else:
                        link_article(db, best.event_id, a["id"])
                        
                        # 鉁?浜嬩欢瀵硅薄缁存姢锛氫竴娆?SQL 鎼炲畾 start/end/last_updated_at
                        touch_event_on_merge(db, best.event_id, published_at)
                        
                        # 鉁?鍚屾鍐呭瓨 candidates锛岄伩鍏嶄笅涓€绡囨枃绔犵敤鍒版棫鏃堕棿
                        for e in candidates:
                            if e["id"] == best.event_id:
                                old_end = e.get("end_time")
                                if old_end is None or published_at > old_end:
                                    e["end_time"] = published_at
                                
                                old_start = e.get("start_time")
                                if old_start is None or published_at < old_start:
                                    e["start_time"] = published_at
                                break
                    
                        print(f"    [write] linked to event_id={best.event_id} + touched event window")
                        print("-" * 80)

            print("[done] committed.")
        else:
            # DRY-RUN锛氫笉鍐欏簱锛屼笉寮€浜嬪姟
            # DRY-RUN锛氫笉鍐欏簱锛屼笉寮€浜嬪姟
            for i, a in enumerate(articles, start=1):
                # 1) per-article retrieval: Top-N events (cap=20)
                cand_map = get_candidate_event_ids_via_vector(db, a["id"])  # dict: {event_id: best_sim}
                candidates = fetch_events_by_ids(db, list(cand_map.keys()))
                for e in candidates:
                    e["best_sim"] = cand_map.get(e["id"], 0.0)

                closed_ids = {e["id"] for e in candidates if e.get("status") == "closed"}

                print(f"[retrieval] article_id={a['id']} candidate_events={len(candidates)} (cap={TOP_N_EVENTS})")

                # 2) decision unchanged
                best = pick_best_event(a, candidates, closed_ids=closed_ids) if candidates else None

                article_time = a["published_at"]
                action = decide_action(best, article_time, best.end_time if best else None)

                print(f"{i:02d}. article_id={a['id']}  time={a['published_at']}  title={a['title'][:80]!r}")
                if best:
                    print(f"    best_event={best.event_id}  vec_sim={best.vec_sim:.3f}  fuzz={best.fuzz:.1f}  jaccard={best.jaccard:.3f}")
                    print(f"    rep_title={best.rep_title[:80]!r}")
                else:
                    print("    best_event=None")
                print(f"    DECISION: {action.upper()}")

                if action == "merge":
                    old_end = best.end_time
                    new_end = article_time if old_end is None else max(old_end, article_time)
                    if old_end != new_end:
                        print(f"    [will_update] event_id={best.event_id} end_time: {old_end} -> {new_end} last_updated_at -> now()")
                    else:
                        print(f"    [will_update] event_id={best.event_id} end_time unchanged ({old_end}); last_updated_at -> now()")

                elif action == "new":
                    print(f"    [will_create] new event start_time={article_time} end_time={article_time} last_updated_at -> now()")

                print("-" * 80)

            print("[done] dry-run complete (no database writes).")


    except Exception:
        # 浜嬪姟鍧楀唴寮傚父浼氳嚜鍔ㄥ洖婊氾紱杩欓噷鍏滃簳鍏抽棴 session
        raise
    finally:
        db.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="actually write events/event_articles to DB")
    args = parser.parse_args()
    main(do_write=args.write)
