# backend/app/services/coverage_matrix.py
# Phase 2.2B v0: Coverage Matrix computation (READ-ONLY)

from sqlalchemy import text
from app.database import engine


SQL_COVERAGE_MATRIX = """
SELECT
  ea.event_id,
  s.id   AS source_id,
  s.name AS source_name,
  CASE
    WHEN a.article_type IS NULL OR a.article_type = 'DEFAULT_FACT' THEN 'FACT'
    ELSE a.article_type
  END AS effective_type,
  COUNT(*) AS cnt,
  ARRAY_AGG(a.id ORDER BY a.published_at DESC NULLS LAST) AS article_ids
FROM event_articles ea
JOIN articles a ON a.id = ea.article_id
JOIN sources  s ON s.id = a.source_id
WHERE ea.event_id = :event_id
GROUP BY ea.event_id, s.id, s.name, effective_type
ORDER BY s.name, effective_type;
"""


def get_coverage_matrix(event_id: int) -> dict:
    """
    Return coverage matrix for a given event_id.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text(SQL_COVERAGE_MATRIX),
            {"event_id": event_id},
        ).mappings().all()

    rows_by_source = {}
    totals = {"FACT": 0, "INTERPRETATION": 0, "COMMENTARY": 0, "UNKNOWN": 0}
    totals = {"FACT": 0, "INTERPRETATION": 0, "COMMENTARY": 0}

    for r in rows:
        sid = r["source_id"]
        if sid not in rows_by_source:
            rows_by_source[sid] = {
                "source_id": sid,
                "source_name": r["source_name"],
                "counts": {"FACT": 0, "INTERPRETATION": 0, "COMMENTARY": 0, "UNKNOWN": 0},
                "article_ids": {
                    "FACT": [],
                    "INTERPRETATION": [],
                    "COMMENTARY": [],
                    "UNKNOWN": [],
                },
            }

        atype = r.get("article_type") or "UNKNOWN"
        rows_by_source[sid]["counts"][atype] = r["cnt"]
        rows_by_source[sid]["article_ids"][atype] = list(r["article_ids"])
        totals[atype] += r["cnt"]
        etype = r["effective_type"]
        rows_by_source[sid]["counts"][etype] = r["cnt"]
        rows_by_source[sid]["article_ids"][etype] = list(r["article_ids"])
        totals[etype] += r["cnt"]

    return {
        "event_id": event_id,
        "types": ["FACT", "INTERPRETATION", "COMMENTARY", "UNKNOWN"],
        "rows": list(rows_by_source.values()),
        "totals": totals,
    }
