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


def main() -> int:
    db_url = os.getenv("DATABASE_URL", "")
    if db_url.startswith("postgresql+psycopg://"):
        db_url = "postgresql://" + db_url[len("postgresql+psycopg://") :]
    if not db_url:
        sys.stderr.write("ERROR: DATABASE_URL is missing.\n")
        return 2
    if psycopg is None:
        sys.stderr.write("ERROR: psycopg is not installed in current Python env.\n")
        return 2

    out = {"ts": datetime.now(timezone.utc).isoformat()}
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  s.id,
                  s.name,
                  COUNT(a.id) AS article_count,
                  MAX(a.published_at) AS last_article_at
                FROM sources s
                LEFT JOIN articles a ON a.source_id = s.id
                GROUP BY s.id, s.name
                ORDER BY article_count DESC, s.id ASC
                LIMIT 30;
                """
            )
            rows = cur.fetchall()
    out["top_sources"] = [
        {
            "source_id": r[0],
            "source_name": r[1],
            "article_count": int(r[2]),
            "last_article_at": str(r[3]) if r[3] else None,
        }
        for r in rows
    ]
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
