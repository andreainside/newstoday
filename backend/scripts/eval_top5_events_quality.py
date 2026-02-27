#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

try:
    import psycopg
except ModuleNotFoundError:  # pragma: no cover
    psycopg = None

from app.services.eval_logger import log_eval_run


STOPWORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "but",
    "to",
    "of",
    "in",
    "on",
    "at",
    "for",
    "with",
    "from",
    "by",
    "as",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "this",
    "that",
    "these",
    "those",
    "after",
    "before",
    "during",
    "over",
    "under",
    "up",
    "down",
    "into",
    "out",
    "off",
    "near",
    "new",
    "latest",
    "live",
    "update",
    "updates",
    "watch",
    "video",
}

NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


@dataclass
class EventRow:
    event_id: int
    title: str
    last_seen_at: datetime
    articles_count: int
    sources_count: int
    score: float | None = None


def _normalize_db_url(db_url: str) -> str:
    if db_url.startswith("postgresql+psycopg://"):
        return "postgresql://" + db_url[len("postgresql+psycopg://") :]
    return db_url


def _tokenize(title: str) -> List[str]:
    t = (title or "").strip().lower()
    t = NON_ALNUM_RE.sub(" ", t)
    out = []
    for tok in t.split():
        if tok in STOPWORDS or len(tok) <= 1:
            continue
        out.append(tok)
    return out


def _jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    set_a = set(a)
    set_b = set(b)
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def _kendall_like(rank_a: Dict[int, int], rank_b: Dict[int, int]) -> float:
    ids = list({*rank_a.keys(), *rank_b.keys()})
    if len(ids) < 2:
        return 0.0
    concordant = 0
    discordant = 0
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a_i = rank_a[ids[i]]
            a_j = rank_a[ids[j]]
            b_i = rank_b[ids[i]]
            b_j = rank_b[ids[j]]
            if a_i == a_j or b_i == b_j:
                continue
            order_a = a_i < a_j
            order_b = b_i < b_j
            if order_a == order_b:
                concordant += 1
            else:
                discordant += 1
    denom = concordant + discordant
    if denom == 0:
        return 0.0
    return (concordant - discordant) / denom


def _fetch_candidate_events(
    conn: "psycopg.Connection",
    window_hours: int,
    limit_events: int,
) -> List[EventRow]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              e.id AS event_id,
              COALESCE(e.representative_title, e.title, '') AS title,
              COALESCE(e.last_updated_at, e.end_time, e.created_at) AS last_seen_at,
              COUNT(ea.article_id) AS articles_count,
              COUNT(DISTINCT a.source_id) AS sources_count
            FROM events e
            JOIN event_articles ea ON ea.event_id = e.id
            JOIN articles a ON a.id = ea.article_id
            WHERE COALESCE(e.last_updated_at, e.end_time, e.created_at) >= (now() - (%s || ' hours')::interval)
            GROUP BY e.id, e.representative_title, e.title, COALESCE(e.last_updated_at, e.end_time, e.created_at)
            ORDER BY COALESCE(e.last_updated_at, e.end_time, e.created_at) DESC, e.id DESC
            LIMIT %s;
            """,
            (max(1, int(window_hours)), max(1, int(limit_events))),
        )
        rows = cur.fetchall()
    out = []
    for r in rows:
        out.append(
            EventRow(
                event_id=int(r[0]),
                title=r[1] or "",
                last_seen_at=r[2],
                articles_count=int(r[3]),
                sources_count=int(r[4]),
            )
        )
    return out


def _fetch_algo_topk(
    conn: "psycopg.Connection",
    *,
    window_hours: int,
    tau_hours: int,
    weights: Dict[str, float],
    top_k: int,
) -> List[EventRow]:
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH stats AS (
              SELECT
                e.id AS event_id,
                COALESCE(e.representative_title, e.title, '') AS title,
                COALESCE(e.last_updated_at, e.end_time, e.created_at) AS last_seen_at,
                COUNT(ea.article_id) AS articles_count,
                COUNT(DISTINCT a.source_id) AS sources_count
              FROM events e
              JOIN event_articles ea ON ea.event_id = e.id
              JOIN articles a ON a.id = ea.article_id
              WHERE COALESCE(e.last_updated_at, e.end_time, e.created_at) >= (now() - (%s || ' hours')::interval)
              GROUP BY e.id, e.representative_title, e.title, COALESCE(e.last_updated_at, e.end_time, e.created_at)
            ),
            scored AS (
              SELECT
                s.*,
                EXTRACT(EPOCH FROM (now() - s.last_seen_at))/3600.0 AS age_hours,
                LN(1 + s.articles_count) AS hot,
                LN(1 + s.sources_count) AS div,
                EXP(-(EXTRACT(EPOCH FROM (now() - s.last_seen_at))/3600.0) / %s) AS fresh,
                (%s * LN(1 + s.articles_count)
                 + %s * LN(1 + s.sources_count)
                 + %s * EXP(-(EXTRACT(EPOCH FROM (now() - s.last_seen_at))/3600.0) / %s)
                ) AS score
              FROM stats s
            )
            SELECT event_id, title, last_seen_at, articles_count, sources_count, score
            FROM scored
            ORDER BY score DESC, last_seen_at DESC, event_id DESC
            LIMIT %s;
            """,
            (
                max(1, int(window_hours)),
                max(1, int(tau_hours)),
                float(weights["hot"]),
                float(weights["div"]),
                float(weights["fresh"]),
                max(1, int(tau_hours)),
                max(1, int(top_k)),
            ),
        )
        rows = cur.fetchall()
    out = []
    for r in rows:
        out.append(
            EventRow(
                event_id=int(r[0]),
                title=r[1] or "",
                last_seen_at=r[2],
                articles_count=int(r[3]),
                sources_count=int(r[4]),
                score=float(r[5]),
            )
        )
    return out


def _fetch_event_articles(
    conn: "psycopg.Connection",
    event_ids: Iterable[int],
    per_event: int,
) -> List[Dict[str, Any]]:
    ids = list(dict.fromkeys(int(x) for x in event_ids))
    if not ids:
        return []
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH ranked AS (
              SELECT
                ea.event_id,
                a.id AS article_id,
                a.title,
                a.published_at,
                ROW_NUMBER() OVER (
                  PARTITION BY ea.event_id
                  ORDER BY a.published_at DESC NULLS LAST, a.id DESC
                ) AS rn
              FROM event_articles ea
              JOIN articles a ON a.id = ea.article_id
              WHERE ea.event_id = ANY(%s)
            )
            SELECT event_id, article_id, title, published_at
            FROM ranked
            WHERE rn <= %s
            ORDER BY event_id, rn;
            """,
            (ids, max(1, int(per_event))),
        )
        rows = cur.fetchall()
    out = []
    for r in rows:
        out.append(
            {
                "event_id": int(r[0]),
                "article_id": int(r[1]),
                "title": r[2] or "",
                "published_at": r[3],
            }
        )
    return out


def _rank_map(ids: List[int], missing_rank: int) -> Dict[int, int]:
    out = {eid: i + 1 for i, eid in enumerate(ids)}
    for eid in list(out.keys()):
        if out[eid] > missing_rank:
            out[eid] = missing_rank
    return out


def _compute_metrics(algo_ids: List[int], baseline_ids: List[int]) -> Dict[str, float]:
    overlap = len(set(algo_ids) & set(baseline_ids))
    overlap_at_5 = overlap / max(1, len(algo_ids))

    missing_rank = max(len(algo_ids), len(baseline_ids)) + 1
    rank_a = _rank_map(algo_ids, missing_rank)
    rank_b = _rank_map(baseline_ids, missing_rank)
    union_ids = list({*rank_a.keys(), *rank_b.keys()})
    deltas = [abs(rank_a.get(eid, missing_rank) - rank_b.get(eid, missing_rank)) for eid in union_ids]
    mean_abs_rank_delta = sum(deltas) / max(1, len(deltas))

    tau_like = _kendall_like(
        {eid: rank_a.get(eid, missing_rank) for eid in union_ids},
        {eid: rank_b.get(eid, missing_rank) for eid in union_ids},
    )

    return {
        "overlap_at_5": round(overlap_at_5, 3),
        "mean_abs_rank_delta": round(mean_abs_rank_delta, 3),
        "kendall_like": round(tau_like, 3),
    }


def _audit_articles(
    articles: List[Dict[str, Any]],
    top_event_titles: Dict[int, str],
    misattach_threshold: float,
) -> Dict[str, Any]:
    if not articles:
        return {
            "avg_title_match": 0.0,
            "avg_margin_vs_other_top5": 0.0,
            "cross_event_conflict_rate": 0.0,
            "suspected_misattach": [],
        }

    scored = []
    for a in articles:
        event_id = int(a["event_id"])
        art_title = a["title"] or ""
        self_title = top_event_titles.get(event_id, "")
        self_score = _jaccard(_tokenize(art_title), _tokenize(self_title))
        best_other = 0.0
        best_other_event = None
        for other_id, other_title in top_event_titles.items():
            if other_id == event_id:
                continue
            s = _jaccard(_tokenize(art_title), _tokenize(other_title))
            if s > best_other:
                best_other = s
                best_other_event = other_id
        margin = self_score - best_other
        scored.append(
            {
                "event_id": event_id,
                "article_id": int(a["article_id"]),
                "title": art_title,
                "self_score": round(self_score, 4),
                "best_other_score": round(best_other, 4),
                "best_other_event_id": best_other_event,
                "margin": round(margin, 4),
            }
        )

    avg_title_match = sum(s["self_score"] for s in scored) / len(scored)
    avg_margin = sum(s["margin"] for s in scored) / len(scored)
    conflict_rate = sum(1 for s in scored if s["margin"] <= 0) / len(scored)

    suspected = [
        s
        for s in scored
        if (s["best_other_score"] - s["self_score"]) >= float(misattach_threshold)
    ]

    return {
        "avg_title_match": round(avg_title_match, 4),
        "avg_margin_vs_other_top5": round(avg_margin, 4),
        "cross_event_conflict_rate": round(conflict_rate, 4),
        "suspected_misattach": suspected,
    }


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate top5 events quality vs human baseline")
    parser.add_argument("--db-url", default=os.getenv("DATABASE_URL", ""))
    parser.add_argument("--window-hours", type=int, default=72)
    parser.add_argument("--sample-events", type=int, default=200)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--min-articles", type=int, default=3)
    parser.add_argument("--min-sources", type=int, default=2)
    parser.add_argument("--tau-hours", type=int, default=24)
    parser.add_argument("--w-hot", type=float, default=0.45)
    parser.add_argument("--w-div", type=float, default=0.35)
    parser.add_argument("--w-fresh", type=float, default=0.20)
    parser.add_argument("--articles-per-event", type=int, default=5)
    parser.add_argument("--misattach-threshold", type=float, default=0.15)
    parser.add_argument("--write-log", action="store_true")
    parser.add_argument("--output-json", default="")
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv)
    db_url = _normalize_db_url(args.db_url)
    if not db_url:
        raise SystemExit("ERROR: DATABASE_URL is missing.")
    if psycopg is None:
        raise SystemExit("ERROR: psycopg is not installed in current Python env.")

    weights = {"hot": args.w_hot, "div": args.w_div, "fresh": args.w_fresh}

    with psycopg.connect(db_url) as conn:
        candidates = _fetch_candidate_events(conn, args.window_hours, args.sample_events)
        algo_top = _fetch_algo_topk(
            conn,
            window_hours=args.window_hours,
            tau_hours=args.tau_hours,
            weights=weights,
            top_k=args.top_k,
        )

        baseline_pool = [
            c
            for c in candidates
            if c.articles_count >= args.min_articles and c.sources_count >= args.min_sources
        ]
        baseline_sorted = sorted(
            baseline_pool,
            key=lambda r: (r.sources_count, r.articles_count, r.last_seen_at, r.event_id),
            reverse=True,
        )
        baseline_top = baseline_sorted[: args.top_k]

        algo_ids = [r.event_id for r in algo_top]
        baseline_ids = [r.event_id for r in baseline_top]

        metrics = _compute_metrics(algo_ids, baseline_ids)

        top_titles = {r.event_id: r.title for r in algo_top}
        articles = _fetch_event_articles(conn, algo_ids, args.articles_per_event)
        audit = _audit_articles(articles, top_titles, args.misattach_threshold)

    payload: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "window_hours": args.window_hours,
        "sample_events": args.sample_events,
        "min_articles": args.min_articles,
        "min_sources": args.min_sources,
        "weights": weights,
        "tau_hours": args.tau_hours,
        "top_k": args.top_k,
        "algo_top5": [r.__dict__ for r in algo_top],
        "baseline_top5": [r.__dict__ for r in baseline_top],
        "metrics": metrics,
        "audit": audit,
    }

    if args.output_json:
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=str)

    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))

    if args.write_log:
        log_eval_run(
            run_id=f"top5_quality_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
            eval_type="top5_quality",
            algorithm_name="top_events_v0",
            algorithm_version="v0",
            baseline_name="human_baseline_v0",
            baseline_version="v0",
            sample_window_hours=args.window_hours,
            sample_event_ids=[r.event_id for r in candidates],
            algo_topk=algo_ids,
            baseline_topk=baseline_ids,
            metrics={
                **metrics,
                "avg_title_match": audit["avg_title_match"],
                "avg_margin_vs_other_top5": audit["avg_margin_vs_other_top5"],
                "cross_event_conflict_rate": audit["cross_event_conflict_rate"],
                "misattach_threshold": args.misattach_threshold,
                "suspected_misattach_count": len(audit["suspected_misattach"]),
            },
            params={
                "window_hours": args.window_hours,
                "tau_hours": args.tau_hours,
                "weights": weights,
                "top_k": args.top_k,
                "sample_events": args.sample_events,
                "min_articles": args.min_articles,
                "min_sources": args.min_sources,
                "articles_per_event": args.articles_per_event,
            },
            notes="auto logged by eval_top5_events_quality.py",
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
