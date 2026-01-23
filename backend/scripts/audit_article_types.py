# backend/scripts/audit_article_types.py
# Phase 2.2B v0: audit article typing (READ-ONLY)
# Uses existing SQLAlchemy engine from app.database

from __future__ import annotations

import argparse
from sqlalchemy import text

# ✅ 复用你现有的数据库配置
from app.database import engine

# ✅ 引入规则分类器
from app.services.article_typing_rules import classify_article_type


SQL_RECENT_ARTICLES = """
SELECT
  a.id AS article_id,
  a.title AS title,
  a.summary AS summary,
  a.url AS url,
  a.published_at AS published_at
FROM articles a
ORDER BY a.published_at DESC NULLS LAST
LIMIT :limit
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    rows = []
    with engine.connect() as conn:
        result = conn.execute(text(SQL_RECENT_ARTICLES), {"limit": args.limit})
        for r in result.mappings():
            rows.append(dict(r))

    stats = {"FACT": 0, "INTERPRETATION": 0, "COMMENTARY": 0}
    outputs = []

    for row in rows:
        res = classify_article_type(
            title=row.get("title"),
            summary=row.get("summary"),
            url=row.get("url"),
        )
        stats[res.article_type] += 1
        outputs.append(
            {
                "article_id": row["article_id"],
                "type": res.article_type,
                "reasons": ",".join(res.reasons),
                "title": (row.get("title") or "")[:120],
            }
        )

    print("=== Phase 2.2B v0 Audit: Article Types (READ-ONLY) ===")
    print(f"limit={args.limit}")
    print(
        f"STATS: FACT={stats['FACT']}  "
        f"INTERPRETATION={stats['INTERPRETATION']}  "
        f"COMMENTARY={stats['COMMENTARY']}"
    )
    print("-" * 100)

    print("Sample (first 20):")
    for o in outputs[:20]:
        print(
            f"{o['article_id']:>6} | "
            f"{o['type']:<14} | "
            f"{o['reasons']:<28} | "
            f"{o['title']}"
        )

    print("-" * 100)
    print("COMMENTARY candidates (inspect carefully):")
    comm = [o for o in outputs if o["type"] == "COMMENTARY"]
    if not comm:
        print("(none)")
    else:
        for o in comm:
            print(
                f"{o['article_id']:>6} | "
                f"{o['type']:<14} | "
                f"{o['reasons']:<28} | "
                f"{o['title']}"
            )


if __name__ == "__main__":
    main()
