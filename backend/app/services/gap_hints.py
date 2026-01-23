# backend/app/services/gap_hints.py
# Phase 2.2B v0: Gap hints (READ-ONLY)
# Constraints: conservative, non-judgmental, no LLM, no stance labeling.

from sqlalchemy import text
from app.database import engine


# v0 official whitelist: keep tiny & explicit; expand later if needed
# We match against sources.url with ILIKE.
OFFICIAL_URL_SUBSTRINGS = [
    "un.org",
    "whitehouse.gov",
    "europa.eu",
]

SQL_GAP_BASE = """
WITH base AS (
  SELECT
    ea.event_id,
    COUNT(*) AS total_articles,
    COUNT(DISTINCT a.source_id) AS distinct_sources,
    SUM(CASE WHEN a.article_type='FACT' THEN 1 ELSE 0 END) AS fact_cnt,
    SUM(CASE WHEN a.article_type='INTERPRETATION' THEN 1 ELSE 0 END) AS interpretation_cnt,
    SUM(CASE WHEN a.article_type='COMMENTARY' THEN 1 ELSE 0 END) AS commentary_cnt,
    SUM(
      CASE
        WHEN
          -- official whitelist checks (expanded in python into OR clauses)
          {official_url_or}
        THEN 1 ELSE 0
      END
    ) AS official_hits
  FROM event_articles ea
  JOIN articles a ON a.id = ea.article_id
  JOIN sources s ON s.id = a.source_id
  WHERE ea.event_id = :event_id
  GROUP BY ea.event_id
)
SELECT
  event_id,
  total_articles,
  distinct_sources,
  fact_cnt,
  interpretation_cnt,
  commentary_cnt,
  official_hits
FROM base;
"""


def _build_official_or_clause() -> str:
    # produces: s.url ILIKE '%a%' OR s.url ILIKE '%b%' ...
    parts = [f"s.url ILIKE '%{sub}%'" for sub in OFFICIAL_URL_SUBSTRINGS]
    if not parts:
        # never match
        return "FALSE"
    return " OR ".join(parts)


def get_gap_hints(event_id: int) -> dict:
    """
    Returns gap hints for an event. Hints are non-judgmental.
    Only 3 gaps in v0:
      - GAP_OFFICIAL_MISSING
      - GAP_SOURCE_CONCENTRATION (proxy for 'international' in v0 due to missing metadata)
      - GAP_NO_ANALYSIS_OR_CRITIQUE
    """
    sql = SQL_GAP_BASE.format(official_url_or=_build_official_or_clause())

    with engine.connect() as conn:
        row = conn.execute(text(sql), {"event_id": event_id}).mappings().first()

    if not row:
        # event has no articles
        return {"event_id": event_id, "hints": []}

    total_articles = int(row["total_articles"])
    distinct_sources = int(row["distinct_sources"])
    interpretation_cnt = int(row["interpretation_cnt"])
    commentary_cnt = int(row["commentary_cnt"])
    official_hits = int(row["official_hits"])

    hints = []

    # Gap A: missing official/primary statements (conservative)
    if total_articles >= 4 and distinct_sources >= 2 and official_hits == 0:
        hints.append(
            {
                "code": "GAP_OFFICIAL_MISSING",
                "message": "Hint: no official/primary statements detected among current sources.",
                "evidence": {
                    "total_articles": total_articles,
                    "distinct_sources": distinct_sources,
                    "official_hits": official_hits,
                },
            }
        )

    # Gap B: source concentration (v0 proxy; do NOT claim international)
    if total_articles >= 4 and distinct_sources == 1:
        hints.append(
            {
                "code": "GAP_SOURCE_CONCENTRATION",
                "message": "Hint: coverage currently comes from a single source; additional outlets may add context.",
                "evidence": {
                    "total_articles": total_articles,
                    "distinct_sources": distinct_sources,
                },
            }
        )

    # Gap C: no analysis/critique detected (using article_type distribution)
    if total_articles >= 5 and (interpretation_cnt + commentary_cnt) == 0:
        hints.append(
            {
                "code": "GAP_NO_ANALYSIS_OR_CRITIQUE",
                "message": "Hint: mostly straight reporting; little analysis/critique detected yet.",
                "evidence": {
                    "total_articles": total_articles,
                    "interpretation_cnt": interpretation_cnt,
                    "commentary_cnt": commentary_cnt,
                },
            }
        )

    return {"event_id": event_id, "hints": hints}
