#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

try:
    import psycopg
except ModuleNotFoundError:  # pragma: no cover
    psycopg = None


SQLS = {
    "articles_total": "SELECT COUNT(*) FROM articles;",
    "articles_recent_7d": "SELECT COUNT(*) FROM articles WHERE published_at >= now() - interval '7 days';",
    "articles_with_embedding": "SELECT COUNT(*) FROM articles WHERE embedding IS NOT NULL;",
    "events_total": "SELECT COUNT(*) FROM events;",
    "event_articles_total": "SELECT COUNT(*) FROM event_articles;",
    "events_with_signature": "SELECT COUNT(*) FROM events WHERE signature_v0 IS NOT NULL AND jsonb_array_length(signature_v0) > 0;",
    "merge_suggestions_total": "SELECT COUNT(*) FROM event_merge_suggestions;",
}


def _normalize_db_url(db_url: str) -> str:
    if db_url.startswith("postgresql+psycopg://"):
        return "postgresql://" + db_url[len("postgresql+psycopg://") :]
    return db_url


def main() -> int:
    db_url = os.getenv("DATABASE_URL", "")
    db_url = _normalize_db_url(db_url)
    if not db_url:
        sys.stderr.write("ERROR: DATABASE_URL is missing.\n")
        return 2
    if psycopg is None:
        sys.stderr.write("ERROR: psycopg is not installed in current Python env.\n")
        return 2

    out = {"ts": datetime.now(timezone.utc).isoformat()}
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            for k, sql in SQLS.items():
                try:
                    cur.execute(sql)
                    out[k] = int(cur.fetchone()[0])
                except Exception as exc:
                    out[k] = f"error: {exc}"

    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
