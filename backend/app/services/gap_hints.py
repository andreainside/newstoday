# backend/app/services/gap_hints.py
# Phase 2.2B v0: Gap hints (READ-ONLY)
# Constraints: conservative, non-judgmental, no LLM, no stance labeling.

from sqlalchemy import text
from app.database import engine

MIN_SOURCES_FOR_GAP = 3
MIN_ARTICLES_FOR_GAP = 4
GAP_TYPES = ["FACT", "INTERPRETATION", "COMMENTARY"]

SQL_GAP_COUNTS = """
SELECT
  a.source_id,
  s.name AS source_name,
  CASE
    WHEN a.article_type IS NULL OR a.article_type = 'DEFAULT_FACT' THEN 'FACT'
    ELSE a.article_type
  END AS effective_type,
  COUNT(*) AS cnt
FROM event_articles ea
JOIN articles a ON a.id = ea.article_id
JOIN sources s ON s.id = a.source_id
WHERE ea.event_id = :event_id
GROUP BY a.source_id, s.name, effective_type
ORDER BY s.name, effective_type;
"""


def get_gap_hints(event_id: int) -> dict:
    """
    Returns gap hints for an event. Hints are non-judgmental.
    Gap codes (v0): MISSING_TYPES, DOMINANT_SOURCE
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text(SQL_GAP_COUNTS),
            {"event_id": event_id},
        ).mappings().all()

    if not rows:
        missing_types = list(GAP_TYPES)
        evidence_summary = {
            "total_articles": 0,
            "distinct_sources": 0,
            "type_counts": {t: 0 for t in GAP_TYPES},
            "dominant_source_ratio": 0.0,
            "dominant_source": {
                "source_id": None,
                "source_name": None,
                "articles": 0,
            },
            "missing_types": missing_types,
            "thresholds": {
                "min_sources_for_gap": MIN_SOURCES_FOR_GAP,
                "min_articles_for_gap": MIN_ARTICLES_FOR_GAP,
            },
            "reason": "no_articles",
        }
        return {
            "event_id": event_id,
            "status": "INSUFFICIENT_DATA",
            "message": "Insufficient data to assess gaps yet.",
            "gaps": [],
            "gap_codes": [],
            "hints": [],
            "evidence_summary": evidence_summary,
        }

    type_counts = {t: 0 for t in GAP_TYPES}
    source_counts = {}
    source_names = {}
    total_articles = 0

    for r in rows:
        etype = r["effective_type"]
        cnt = int(r["cnt"])
        total_articles += cnt
        if etype in type_counts:
            type_counts[etype] += cnt
        sid = int(r["source_id"])
        source_counts[sid] = source_counts.get(sid, 0) + cnt
        source_names[sid] = r["source_name"]

    distinct_sources = len(source_counts)
    dominant_source_id = None
    dominant_source_articles = 0
    dominant_source_name = None
    if source_counts:
        dominant_source_id = max(source_counts, key=lambda k: source_counts[k])
        dominant_source_articles = source_counts[dominant_source_id]
        dominant_source_name = source_names.get(dominant_source_id)
    dominant_source_ratio = (
        float(dominant_source_articles) / float(total_articles)
        if total_articles > 0
        else 0.0
    )
    missing_types = [t for t, cnt in type_counts.items() if cnt == 0]

    evidence_summary = {
        "total_articles": total_articles,
        "distinct_sources": distinct_sources,
        "type_counts": type_counts,
        "dominant_source_ratio": dominant_source_ratio,
        "dominant_source": {
            "source_id": dominant_source_id,
            "source_name": dominant_source_name,
            "articles": dominant_source_articles,
        },
        "missing_types": missing_types,
        "thresholds": {
            "min_sources_for_gap": MIN_SOURCES_FOR_GAP,
            "min_articles_for_gap": MIN_ARTICLES_FOR_GAP,
        },
    }

    if total_articles < MIN_ARTICLES_FOR_GAP or distinct_sources < MIN_SOURCES_FOR_GAP:
        evidence_summary["reason"] = "below_thresholds"
        return {
            "event_id": event_id,
            "status": "INSUFFICIENT_DATA",
            "message": "Insufficient data to assess gaps yet.",
            "gaps": [],
            "gap_codes": [],
            "hints": [],
            "evidence_summary": evidence_summary,
        }

    gaps = []
    if missing_types:
        gaps.append(
            {
                "code": "MISSING_TYPES",
                "message": "Some article types are missing from current coverage.",
                "evidence": {
                    "missing_types": missing_types,
                    "type_counts": type_counts,
                    "total_articles": total_articles,
                    "distinct_sources": distinct_sources,
                },
            }
        )

    if dominant_source_ratio > 0.6:
        gaps.append(
            {
                "code": "DOMINANT_SOURCE",
                "message": "Coverage is concentrated in a single source.",
                "evidence": {
                    "dominant_source_ratio": dominant_source_ratio,
                    "dominant_source_id": dominant_source_id,
                    "dominant_source_name": dominant_source_name,
                    "dominant_source_articles": dominant_source_articles,
                    "total_articles": total_articles,
                    "distinct_sources": distinct_sources,
                },
            }
        )

    if gaps:
        status = "GAP_FOUND"
        message = "Potential gaps detected."
        evidence_summary["reason"] = "gap_found"
    else:
        status = "NO_GAP"
        message = "No gaps detected at current thresholds."
        evidence_summary["reason"] = "no_gap"

    gap_codes = [g["code"] for g in gaps]

    return {
        "event_id": event_id,
        "status": status,
        "message": message,
        "gaps": gaps,
        "gap_codes": gap_codes,
        "hints": gaps,
        "evidence_summary": evidence_summary,
    }
