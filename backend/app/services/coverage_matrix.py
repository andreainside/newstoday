from __future__ import annotations

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
JOIN sources s ON s.id = a.source_id
WHERE ea.event_id = :event_id
GROUP BY ea.event_id, s.id, s.name, effective_type
ORDER BY s.name, effective_type;
"""


KNOWN_TYPES = ["FACT", "INTERPRETATION", "COMMENTARY", "UNKNOWN"]


def _normalize_type(raw: str | None) -> str:
    if not raw:
        return "UNKNOWN"
    t = str(raw).strip().upper()
    if not t:
        return "UNKNOWN"
    if t in ("ANALYSIS", "EXPLAINER"):
        return "INTERPRETATION"
    if t in ("OPINION", "EDITORIAL", "COMMENT"):
        return "COMMENTARY"
    if t in KNOWN_TYPES:
        return t
    return "UNKNOWN"


def get_coverage_matrix(event_id: int) -> dict:
    with engine.connect() as conn:
        rows = conn.execute(text(SQL_COVERAGE_MATRIX), {"event_id": int(event_id)}).mappings().all()

    rows_by_source: dict[int, dict] = {}
    totals = {t: 0 for t in KNOWN_TYPES}

    for r in rows:
        sid = int(r["source_id"])
        if sid not in rows_by_source:
            rows_by_source[sid] = {
                "source_id": sid,
                "source_name": r["source_name"],
                "counts": {t: 0 for t in KNOWN_TYPES},
                "article_ids": {t: [] for t in KNOWN_TYPES},
            }

        etype = _normalize_type(r.get("effective_type"))
        cnt = int(r["cnt"])
        ids = list(r["article_ids"] or [])

        rows_by_source[sid]["counts"][etype] = cnt
        rows_by_source[sid]["article_ids"][etype] = ids
        totals[etype] += cnt

    return {
        "event_id": int(event_id),
        "types": KNOWN_TYPES,
        "rows": list(rows_by_source.values()),
        "totals": totals,
    }
