#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone

try:
    import psycopg
except ModuleNotFoundError:  # pragma: no cover
    psycopg = None

URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9\-]{1,}")
PHRASE_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b")
ACRONYM_RE = re.compile(r"\b[A-Z]{2,}\b")

STOPWORDS = {
    "the",
    "a",
    "an",
    "to",
    "for",
    "of",
    "in",
    "on",
    "and",
    "or",
    "with",
    "from",
    "after",
    "before",
    "amid",
    "over",
    "under",
    "about",
    "new",
    "news",
    "says",
    "say",
    "live",
    "latest",
    "update",
    "updates",
    "video",
    "breaking",
    "watch",
    "analysis",
    "report",
}

ORG_EVENT_KEYWORDS = {
    "government",
    "ministry",
    "agency",
    "court",
    "police",
    "military",
    "fifa",
    "olympics",
    "cup",
    "election",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build event signature_v0 (optimized)")
    parser.add_argument("--db-url", default=os.getenv("DATABASE_URL", ""))
    parser.add_argument("--since-days", type=int, default=7)
    parser.add_argument("--limit-events", type=int, default=500)
    parser.add_argument("--top-n", type=int, default=12)
    parser.add_argument("--docs-per-event", type=int, default=5, help="recent article docs sampled per event")
    parser.add_argument("--write-db", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--mock-llm", action="store_true", help="accepted for CLI compatibility")
    return parser.parse_args(argv)


def _log(message: str) -> None:
    sys.stderr.write(message.rstrip() + "\n")


def _normalize_db_url(db_url: str) -> str:
    if db_url.startswith("postgresql+psycopg://"):
        return "postgresql://" + db_url[len("postgresql+psycopg://") :]
    return db_url


def _clean_token(token: str) -> str:
    t = token.strip().lower()
    t = t.replace("’", "'").replace("`", "'")
    t = re.sub(r"(^[-']+|[-']+$)", "", t)
    return t


def _allow_token(token: str) -> bool:
    if not token:
        return False
    if token in STOPWORDS:
        return False
    if URL_RE.search(token):
        return False
    if len(token) < 2:
        return False
    if token.isdigit():
        return False
    return True


def _extract_from_text(text: str) -> list[str]:
    clean_text = URL_RE.sub(" ", text or "")
    out: list[str] = []
    for p in PHRASE_RE.findall(clean_text):
        cp = _clean_token(p)
        if _allow_token(cp):
            out.append(cp)
    for ac in ACRONYM_RE.findall(clean_text):
        ca = _clean_token(ac)
        if _allow_token(ca):
            out.append(ca)
    for w in WORD_RE.findall(clean_text):
        cw = _clean_token(w)
        if _allow_token(cw):
            out.append(cw)
    return out


def _build_signature(event_title: str, docs: list[dict], top_n: int) -> list[str]:
    # Weighted token voting:
    # - event title tokens get strongest weight
    # - article titles medium
    # - summaries low
    score = Counter()

    for t in _extract_from_text(event_title):
        score[t] += 4

    for doc in docs:
        for t in _extract_from_text(str(doc.get("title", ""))):
            score[t] += 2
        for t in _extract_from_text(str(doc.get("summary", ""))):
            score[t] += 1

    if not score:
        return []

    ranked = [t for t, _ in score.most_common(max(1, top_n * 2))]
    for kw in ORG_EVENT_KEYWORDS:
        if kw in score:
            ranked.append(kw)

    uniq: list[str] = []
    seen = set()
    for t in ranked:
        if t not in seen and _allow_token(t):
            seen.add(t)
            uniq.append(t)
        if len(uniq) >= max(1, top_n):
            break
    return uniq


def _ensure_schema(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS signature_v0 jsonb;")
    conn.commit()


def _load_events(conn: psycopg.Connection, since_days: int, limit_events: int, docs_per_event: int) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH recent_events AS (
              SELECT
                e.id AS event_id,
                COALESCE(e.representative_title, e.title, '') AS event_title,
                COALESCE(e.last_updated_at, e.end_time, e.created_at) AS ts
              FROM events e
              WHERE COALESCE(e.last_updated_at, e.end_time, e.created_at) >= (now() - (%s || ' days')::interval)
              ORDER BY COALESCE(e.last_updated_at, e.end_time, e.created_at) DESC, e.id DESC
              LIMIT %s
            ),
            ranked_docs AS (
              SELECT
                ea.event_id,
                a.title,
                a.summary,
                ROW_NUMBER() OVER (
                  PARTITION BY ea.event_id
                  ORDER BY a.published_at DESC NULLS LAST, a.id DESC
                ) AS rn
              FROM recent_events re
              JOIN event_articles ea ON ea.event_id = re.event_id
              JOIN articles a ON a.id = ea.article_id
            )
            SELECT
              re.event_id,
              re.event_title,
              re.ts,
              COALESCE(
                JSON_AGG(
                  JSON_BUILD_OBJECT('title', rd.title, 'summary', rd.summary)
                  ORDER BY rd.rn
                ) FILTER (WHERE rd.rn <= %s),
                '[]'::json
              ) AS docs
            FROM recent_events re
            LEFT JOIN ranked_docs rd ON rd.event_id = re.event_id
            GROUP BY re.event_id, re.event_title, re.ts
            ORDER BY re.ts DESC, re.event_id DESC;
            """,
            (max(0, since_days), max(1, limit_events), max(1, docs_per_event)),
        )
        rows = cur.fetchall()

    out = []
    for r in rows:
        docs = r[3] if isinstance(r[3], list) else []
        out.append({"event_id": r[0], "title": r[1] or "", "ts": r[2], "docs": docs})
    return out


def _write_signatures(conn: psycopg.Connection, rows: list[dict]) -> int:
    updated = 0
    with conn.cursor() as cur:
        for row in rows:
            cur.execute(
                """
                UPDATE events
                SET signature_v0 = CAST(%s AS jsonb)
                WHERE id = %s;
                """,
                (json.dumps(row["signature_v0"], ensure_ascii=False), row["event_id"]),
            )
            updated += cur.rowcount
    conn.commit()
    return updated


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    args.db_url = _normalize_db_url(args.db_url)
    dry_run = args.dry_run or not args.write_db

    if not args.db_url:
        if not dry_run:
            _log("ERROR: DATABASE_URL is missing. Set env or use --db-url.")
            return 2
        now = datetime.now(timezone.utc)
        events = [
            {
                "event_id": i + 1,
                "title": f"Mock event {i+1} city council update",
                "ts": now,
                "docs": [{"title": "Mock related article", "summary": "Mock summary for event pipeline"}],
            }
            for i in range(min(args.limit_events, 5))
        ]
        conn = None
    else:
        if psycopg is None:
            _log("ERROR: psycopg is not installed in current Python env.")
            return 2
        conn = psycopg.connect(args.db_url)
        _ensure_schema(conn)
        events = _load_events(conn, args.since_days, args.limit_events, args.docs_per_event)

    result_rows = []
    for ev in events:
        sig = _build_signature(ev["title"], ev.get("docs", []), args.top_n)
        result_rows.append(
            {
                "event_id": ev["event_id"],
                "signature_v0": sig,
                "keywords_hit": sorted(set(sig).intersection(ORG_EVENT_KEYWORDS)),
                "updated_at": ev["ts"].astimezone(timezone.utc).isoformat() if hasattr(ev["ts"], "astimezone") else str(ev["ts"]),
            }
        )

    empty_count = sum(1 for r in result_rows if not r["signature_v0"])
    nonempty_count = len(result_rows) - empty_count
    updated = 0

    if not dry_run and result_rows and conn is not None:
        try:
            updated = _write_signatures(conn, result_rows)
        finally:
            conn.close()
    elif conn is not None:
        conn.close()

    _log(
        "[done] build_event_signatures_v0 "
        f"scanned={len(result_rows)} updated={updated} "
        f"empty_signature_count={empty_count} nonempty_signature_count={nonempty_count}"
    )

    payload = {
        "mode": "dry_run" if dry_run else "write_db",
        "ts": datetime.now(timezone.utc).isoformat(),
        "since_days": args.since_days,
        "limit_events": args.limit_events,
        "top_n": args.top_n,
        "events": result_rows,
    }
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
