# backend/scripts/cluster_events.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, UTC
from typing import List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.services.title_similarity import explain_jaccard, fuzz_token_set_ratio

LOOKBACK_HOURS = 72
CANDIDATE_WINDOW_HOURS = 48

FUZZ_ACCEPT = 85.0
FUZZ_MAYBE = 60.0
JACCARD_MAYBE = 0.20
TIME_NEAR_HOURS = 6

# ==============================================

MAX_ARTICLES = 100            # 安全阀：最多处理多少篇
DO_WRITE_DEFAULT = False     # 默认不写库


@dataclass
class CandidateScore:
    event_id: int
    rep_title: str
    end_time: Optional[datetime]
    fuzz: float
    jaccard: float


def get_recent_articles(db: Session, since: datetime) -> List[dict]:
    q = text("""
        SELECT id, source_id, title, published_at
        FROM articles
        WHERE published_at >= :since
        ORDER BY published_at ASC;
    """)
    rows = db.execute(q, {"since": since}).mappings().all()
    return [dict(r) for r in rows]


def get_candidate_events(db: Session, min_end_time: datetime) -> List[dict]:
    q = text("""
        SELECT id, title, representative_title, start_time, end_time, created_at
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


def pick_best_event(article: dict, candidates: List[dict]) -> Optional[CandidateScore]:
    best: Optional[CandidateScore] = None
    for e in candidates:
        rep = e["representative_title"] or e["title"]
        fuzz, j = score_article_to_event(article["title"], rep)
        cs = CandidateScore(
            event_id=e["id"],
            rep_title=rep,
            end_time=e["end_time"],
            fuzz=fuzz,
            jaccard=j,
        )
        if best is None or cs.fuzz > best.fuzz:
            best = cs
    return best



def decide_action(best: Optional[CandidateScore], article_time: datetime, event_end_time: Optional[datetime]) -> str:
    if best is None:
        return "new"

    # 强合并
    if best.fuzz >= FUZZ_ACCEPT:
        return "merge"

    # 灰区：需要第二证据
    if best.fuzz >= FUZZ_MAYBE:
        # 证据1：关键词重叠
        if best.jaccard >= JACCARD_MAYBE:
            return "merge"

        # 证据2：时间非常近（注意 end_time 可能为 None）
        if event_end_time is not None:
            if abs(article_time - event_end_time) <= timedelta(hours=TIME_NEAR_HOURS):
                return "merge"

    return "new"


def create_event(db: Session, title: str, start_time: datetime, end_time: datetime) -> int:
    q = text("""
        INSERT INTO events (title, representative_title, start_time, end_time, created_at)
        VALUES (:title, :rep, :start_time, :end_time, :created_at)
        RETURNING id;
    """)
    new_id = db.execute(q, {
        "title": title,
        "rep": title,
        "start_time": start_time,
        "end_time": end_time,
        "created_at": datetime.now(UTC).replace(tzinfo=None),  # 你的表是 without time zone
    }).scalar_one()
    return int(new_id)


def link_article(db: Session, event_id: int, article_id: int) -> None:
    q = text("""
        INSERT INTO event_articles (event_id, article_id)
        VALUES (:event_id, :article_id)
        ON CONFLICT DO NOTHING;
    """)
    db.execute(q, {"event_id": event_id, "article_id": article_id})


def update_event_end_time(db: Session, event_id: int, new_end_time: datetime) -> None:
    q = text("""
        UPDATE events
        SET end_time = GREATEST(COALESCE(end_time, :new_end), :new_end)
        WHERE id = :id;
    """)
    db.execute(q, {"id": event_id, "new_end": new_end_time})


def main(do_write: bool = DO_WRITE_DEFAULT) -> None:
    now_utc = datetime.now(UTC)
    since = (now_utc - timedelta(hours=LOOKBACK_HOURS)).replace(tzinfo=None)
    min_end_time = (now_utc - timedelta(hours=CANDIDATE_WINDOW_HOURS)).replace(tzinfo=None)

    db = SessionLocal()
    try:
        articles = get_recent_articles(db, since)[:MAX_ARTICLES]
        candidates = get_candidate_events(db, min_end_time)

        print(f"[mode] {'WRITE' if do_write else 'DRY-RUN'} (A=conservative)")
        print(f"[info] articles since {since.isoformat()} = {len(articles)} (max {MAX_ARTICLES})")
        print(
            f"[info] candidate events window end_time >= {min_end_time.isoformat()} (or NULL) = {len(candidates)}"
        )
        print("-" * 80)

        if do_write:
            # 写库模式：事务块内全部成功 -> 自动 commit；中途异常 -> 自动 rollback
            db.rollback()
            with db.begin():
                for i, a in enumerate(articles, start=1):
                    best = pick_best_event(a, candidates) if candidates else None

                    article_time = a["published_at"]  # timestamp without time zone -> naive datetime
                    action = decide_action(best, article_time, best.end_time if best else None)

                    print(f"{i:02d}. article_id={a['id']}  time={a['published_at']}  title={a['title'][:80]!r}")
                    if best:
                        print(f"    best_event={best.event_id}  fuzz={best.fuzz:.1f}  jaccard={best.jaccard:.3f}")
                        print(f"    rep_title={best.rep_title[:80]!r}")
                    else:
                        print("    best_event=None")
                    print(f"    DECISION: {action.upper()}")

                    published_at = a["published_at"]
                    if action == "new":
                        new_event_id = create_event(db, a["title"], published_at, published_at)
                        link_article(db, new_event_id, a["id"])

                        # 新事件加入 candidates，后续文章才有机会 merge 到它
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
                        update_event_end_time(db, best.event_id, published_at)
                        for e in candidates:
                           if e["id"] == best.event_id:
                                old_end = e.get("end_time")
                                if old_end is None or published_at > old_end:
                                    e["end_time"] = published_at
                                break

                        print(f"    [write] linked to event_id={best.event_id} + updated end_time")

                    print("-" * 80)

            print("[done] committed.")
        else:
            # DRY-RUN：不写库，不开事务
            for i, a in enumerate(articles, start=1):
                best = pick_best_event(a, candidates) if candidates else None

                article_time = a["published_at"]
                action = decide_action(best, article_time, best.end_time if best else None)

                print(f"{i:02d}. article_id={a['id']}  time={a['published_at']}  title={a['title'][:80]!r}")
                if best:
                    print(f"    best_event={best.event_id}  fuzz={best.fuzz:.1f}  jaccard={best.jaccard:.3f}")
                    print(f"    rep_title={best.rep_title[:80]!r}")
                else:
                    print("    best_event=None")
                print(f"    DECISION: {action.upper()}")
                print("-" * 80)

            print("[done] dry-run complete (no database writes).")

    except Exception:
        # 事务块内异常会自动回滚；这里兜底关闭 session
        raise
    finally:
        db.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="actually write events/event_articles to DB")
    args = parser.parse_args()
    main(do_write=args.write)
