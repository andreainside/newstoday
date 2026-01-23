# backend/scripts/backfill_article_types.py
# Phase 2.2B v0: backfill article_type into articles table
# SAFE DEFAULT: only recent articles, conservative, idempotent-ish

from __future__ import annotations

import argparse
from datetime import datetime, timedelta

from sqlalchemy import text

# 复用你现有的数据库 engine
from app.database import engine

# 复用已经验证过的规则
from app.services.article_typing_rules import classify_article_type


SQL_SELECT_ARTICLES = """
SELECT
  a.id AS article_id,
  a.title AS title,
  a.summary AS summary,
  a.url AS url
FROM articles a
WHERE
  a.published_at >= :since
ORDER BY a.published_at DESC
LIMIT :limit
"""

SQL_UPDATE_ARTICLE = """
UPDATE articles
SET
  article_type = :article_type,
  article_type_reason = :article_type_reason
WHERE id = :article_id
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill article_type for articles")
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Only backfill articles published in the last N days (default: 7)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1000,
        help="Maximum number of articles to backfill (default: 1000)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force overwrite existing article_type (default: only fill NULLs)",
    )
    args = parser.parse_args()

    since = datetime.utcnow() - timedelta(days=args.days)

    print("=== Phase 2.2B v0 Backfill: article_type ===")
    print(f"since = {since.isoformat()}  limit = {args.limit}  force = {args.force}")

    with engine.begin() as conn:
        rows = conn.execute(
            text(SQL_SELECT_ARTICLES),
            {
                "since": since,
                "limit": args.limit,
            },
        ).mappings().all()

        print(f"Loaded {len(rows)} candidate articles")

        updated = 0

        for row in rows:
            res = classify_article_type(
                title=row.get("title"),
                summary=row.get("summary"),
                url=row.get("url"),
            )

            # 默认只填空值，避免反复覆盖历史结果
            if not args.force:
                existing = conn.execute(
                    text(
                        "SELECT article_type FROM articles WHERE id = :id"
                    ),
                    {"id": row["article_id"]},
                ).scalar_one_or_none()

                if existing is not None:
                    continue

            conn.execute(
                text(SQL_UPDATE_ARTICLE),
                {
                    "article_id": row["article_id"],
                    "article_type": res.article_type,
                    "article_type_reason": ",".join(res.reasons),
                },
            )
            updated += 1

        print(f"Updated {updated} articles")


if __name__ == "__main__":
    main()
