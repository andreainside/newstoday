# app/services/event_reader.py
from __future__ import annotations
import math
import os
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional,Tuple

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Result

# 重要：只用 app.database，避免你根目录 database.py / app/database.py 混用
from app.database import SessionLocal
from app.observability import log_json
from app.services.article_types import effective_type
from app.services.event_title_ai import (
  current_deepseek_settings,
  summarize_event_title,
)

# v0 固定口径参数（稳定、可复现）
WINDOW_HOURS = 72
TAU_HOURS = 12
WEIGHTS = {"hot": 0.25, "div": 0.20, "fresh": 0.55}

SQL_TOP_EVENTS = """
WITH stats AS (
  SELECT
    e.id AS event_id,
    COALESCE(e.representative_title, e.title) AS title,
    e.start_time,
    e.end_time,
    MAX(a.published_at) AS max_article_time,
    COALESCE(MAX(a.published_at), e.end_time, e.created_at) AS last_seen_at,
    COUNT(ea.article_id) AS articles_count,
    COUNT(DISTINCT a.source_id) AS sources_count
  FROM events e
  JOIN event_articles ea ON ea.event_id = e.id
  JOIN articles a ON a.id = ea.article_id
  GROUP BY e.id, e.representative_title, e.title, e.start_time, e.end_time, e.created_at
  HAVING MAX(a.published_at) >= (:as_of_ts - (:window_hours || ' hours')::interval)
),
scored AS (
  SELECT
    s.*,
    EXTRACT(EPOCH FROM (:as_of_ts - s.max_article_time))/3600.0 AS age_hours,
    (LN(1 + s.articles_count) / (1 + (EXTRACT(EPOCH FROM (:as_of_ts - s.max_article_time))/3600.0) / 24.0)) AS hot,
    LN(1 + s.sources_count) AS div,
    EXP(-(EXTRACT(EPOCH FROM (:as_of_ts - s.max_article_time))/3600.0) / :tau_hours) AS fresh,
    (:w_hot * (LN(1 + s.articles_count) / (1 + (EXTRACT(EPOCH FROM (:as_of_ts - s.max_article_time))/3600.0) / 24.0))
     + :w_div * LN(1 + s.sources_count)
     + :w_fresh * EXP(-(EXTRACT(EPOCH FROM (:as_of_ts - s.max_article_time))/3600.0) / :tau_hours)
    ) AS score
  FROM stats s
)
SELECT *
FROM scored
ORDER BY score DESC, last_seen_at DESC, event_id DESC
LIMIT :limit;
"""

SQL_EVENT_DETAIL = """
WITH base AS (
  SELECT
    e.id AS event_id,
    COALESCE(e.representative_title, e.title) AS title,
    e.start_time,
    e.end_time,
    COALESCE(e.last_updated_at, e.end_time, e.created_at) AS last_seen_at,
    COUNT(ea.article_id) AS articles_count,
    COUNT(DISTINCT a.source_id) AS sources_count
  FROM events e
  JOIN event_articles ea ON ea.event_id = e.id
  JOIN articles a ON a.id = ea.article_id
  WHERE e.id = :event_id
  GROUP BY e.id, e.representative_title, e.title, e.start_time, e.end_time, COALESCE(e.last_updated_at, e.end_time, e.created_at)
)
SELECT * FROM base;
"""

SQL_EVENT_ARTICLES = """
SELECT
  a.id AS article_id,
  a.published_at,
  a.title,
  a.url AS link,
  a.article_type,
  a.article_type_reason,
  s.id AS source_id,
  s.name AS source_name,
  s.url AS source_url,
  COALESCE(s.country, 'Unknown') AS source_country,
  COALESCE(s.region, 'Unknown') AS source_region,
  COALESCE(s.language, 'Unknown') AS source_language,
  s.ownership_group AS source_ownership_group
FROM event_articles ea
JOIN articles a ON a.id = ea.article_id
JOIN sources s ON s.id = a.source_id
WHERE ea.event_id = :event_id
ORDER BY a.published_at DESC NULLS LAST, a.id DESC;
"""

SQL_EVENT_TITLES_FOR_TOP = """
SELECT
  ea.event_id,
  a.title
FROM event_articles ea
JOIN articles a ON a.id = ea.article_id
WHERE ea.event_id IN :event_ids
ORDER BY ea.event_id ASC, a.published_at DESC NULLS LAST, a.id DESC;
"""

SQL_EVENT_AI_CACHE_UPSERT = """
INSERT INTO event_ai_cache (event_id, provider, model, status, output_json, error, updated_at)
VALUES (:event_id, :provider, :model, :status, CAST(:output_json AS jsonb), :error, now())
ON CONFLICT (event_id, provider, model)
DO UPDATE SET
  status = EXCLUDED.status,
  output_json = EXCLUDED.output_json,
  error = EXCLUDED.error,
  updated_at = now();
"""

SQL_EVENT_AI_CACHE_GET = """
SELECT status, output_json, updated_at
FROM event_ai_cache
WHERE event_id = :event_id AND provider = :provider AND model = :model
ORDER BY updated_at DESC
LIMIT 1;
"""

SQL_EVENT_AI_CACHE_CLAIM = """
INSERT INTO event_ai_cache (event_id, provider, model, status, output_json, error, updated_at)
VALUES (:event_id, :provider, :model, 'PENDING', NULL, NULL, now())
ON CONFLICT (event_id, provider, model) DO NOTHING
RETURNING event_id;
"""

EVENT_TITLE_PROMPT_VERSION = "event_title_v1"
EVENT_TITLE_INPUT_HASH = "top_titles_v1"
EVENT_AI_PENDING_RETRY_SECONDS = int(os.getenv("EVENT_AI_PENDING_RETRY_SECONDS", "90"))

def _utc_now() -> datetime:
  # 统一用 UTC，避免前后端时区混乱
  return datetime.now(timezone.utc)

def get_top_events(limit: int) -> Dict[str, Any]:
  limit = max(1, min(int(limit), 20))
  as_of = _utc_now()

  with SessionLocal() as db:
    rows: Result = db.execute(
      text(SQL_TOP_EVENTS),
      {
        "as_of_ts": as_of,
        "window_hours": WINDOW_HOURS,
        "tau_hours": TAU_HOURS,
        "w_hot": WEIGHTS["hot"],
        "w_div": WEIGHTS["div"],
        "w_fresh": WEIGHTS["fresh"],
        "limit": limit,
      },
    )
    items: List[Dict[str, Any]] = []
    for r in rows.mappings():
      items.append(
        {
          "event_id": r["event_id"],
          "title": r["title"],
          "start_time": r["start_time"],
          "end_time": r["end_time"],
          "last_seen_at": r["last_seen_at"],
          "articles_count": r["articles_count"],
          "sources_count": r["sources_count"],
          "score": float(r["score"]),
          "score_components": {
            "hot": float(r["hot"]),
            "div": float(r["div"]),
            "fresh": float(r["fresh"]),
            "age_hours": float(r["age_hours"]),
          },
        }
      )

    try:
      event_ids = [int(item["event_id"]) for item in items]
      titles_map: Dict[int, List[str]] = defaultdict(list)
      if event_ids:
        title_stmt = text(SQL_EVENT_TITLES_FOR_TOP).bindparams(bindparam("event_ids", expanding=True))
        title_rows = db.execute(
          title_stmt,
          {"event_ids": event_ids},
        ).mappings()
        for tr in title_rows:
          event_id = int(tr["event_id"])
          title = (tr["title"] or "").strip()
          if title:
            titles_map[event_id].append(title)

      for item in items:
        event_id = int(item["event_id"])
        article_titles = titles_map.get(event_id, [])
        if not article_titles:
          continue

        settings = current_deepseek_settings()
        model = settings["model"]
        cached = db.execute(
          text(SQL_EVENT_AI_CACHE_GET),
          {
            "event_id": event_id,
            "provider": "deepseek",
            "model": model,
          },
        ).mappings().first()
        if cached and cached.get("status") == "SUCCESS":
          output_json = cached.get("output_json") or {}
          cached_title = output_json.get("title") if isinstance(output_json, dict) else None
          if cached_title:
            log_json(
              "deepseek_call",
              event_id=event_id,
              provider="deepseek",
              model=model,
              status="SUCCESS",
              error_type=None,
              http_status=None,
              latency_ms=0,
              cache_hit=True,
            )
            item["title"] = cached_title
            continue
        if cached and cached.get("status") == "PENDING":
          updated_at = cached.get("updated_at")
          if isinstance(updated_at, datetime):
            ts = updated_at if updated_at.tzinfo else updated_at.replace(tzinfo=timezone.utc)
            if (_utc_now() - ts).total_seconds() < EVENT_AI_PENDING_RETRY_SECONDS:
              continue
        # retry stale PENDING and previous ERROR entries

        claim_row = db.execute(
          text(SQL_EVENT_AI_CACHE_CLAIM),
          {
            "event_id": event_id,
            "provider": "deepseek",
            "model": model,
          },
        ).mappings().first()
        if not claim_row:
          continue

        ai_result = summarize_event_title(article_titles, event_id=event_id)
        if ai_result.get("ok") and ai_result.get("title"):
          item["title"] = ai_result["title"]
          db.execute(
            text(SQL_EVENT_AI_CACHE_UPSERT),
            {
              "event_id": event_id,
              "provider": "deepseek",
              "model": model,
              "status": "SUCCESS",
              "output_json": json.dumps(
                {
                  "title": ai_result["title"],
                  "sampled_titles": ai_result.get("sampled_titles", []),
                  "total_article_titles": len(article_titles),
                  "input_hash": EVENT_TITLE_INPUT_HASH,
                  "prompt_version": EVENT_TITLE_PROMPT_VERSION,
                }
              ),
              "error": None,
            },
          )
        else:
          if ai_result.get("error") not in ("missing_deepseek_api_key", "empty_article_titles"):
            db.execute(
              text(SQL_EVENT_AI_CACHE_UPSERT),
              {
                "event_id": event_id,
                "provider": "deepseek",
                "model": model,
                "status": "ERROR",
                "output_json": None,
                "error": str(ai_result.get("error") or "unknown_error")[:1000],
              },
            )

      if items:
        db.commit()
    except Exception as exc:
      log_json(
        "deepseek_cache_pipeline_error",
        error_type=type(exc).__name__,
        error=str(exc),
      )
      db.rollback()

  return {
    "as_of": as_of.isoformat(),
    "window_hours": WINDOW_HOURS,
    "tau_hours": TAU_HOURS,
    "weights": WEIGHTS,
    "items": items,
  }

def get_event_detail(event_id: int, diversity: int = 0, debug: bool = False) -> Dict[str, Any]:
  event_id = int(event_id)
  with SessionLocal() as db:
    base_row = db.execute(text(SQL_EVENT_DETAIL), {"event_id": event_id}).mappings().first()
    if not base_row:
      return {"event": None, "coverage": None, "gaps": None, "articles": []}

    article_rows = list(
      db.execute(text(SQL_EVENT_ARTICLES), {"event_id": event_id}).mappings()
    )

  # 直接复用你已经跑通的 2.2B 逻辑
  from app.services.coverage_matrix import get_coverage_matrix
  from app.services.gap_hints import get_gap_hints

  coverage = get_coverage_matrix(event_id)
  gaps = get_gap_hints(event_id)

  articles = [
    {
      "article_id": a["article_id"],
      "published_at": a["published_at"],
      "title": a["title"],
      "link": a["link"],
      "type": a["article_type"],
      "effective_type": effective_type(a["article_type"]),
      "type_reason": a["article_type_reason"],
      "source": {
        "source_id": a["source_id"],
        "name": a["source_name"],
        "url": a["source_url"],
        "country": a["source_country"],
        "region": a["source_region"],
        "language": a["source_language"],
        "ownership_group": a["source_ownership_group"],
      },
    }
    for a in article_rows
  ]

   # ---- Diversity Slider v0 (presentation-time only) ----
  selected_articles, diversity_dbg = _apply_diversity_v0(
    articles,
    diversity=diversity,
    k=max(12, len(articles)),
    candidate_cap=max(50, len(articles)),
    max_source_ratio=0.6,
  )
  articles = selected_articles

  resp = {
    "event": {
      "event_id": base_row["event_id"],
      "title": base_row["title"],
      "start_time": base_row["start_time"],
      "end_time": base_row["end_time"],
      "last_seen_at": base_row["last_seen_at"],
      "articles_count": base_row["articles_count"],
      "sources_count": base_row["sources_count"],
    },
    "coverage": coverage,
    "gaps": gaps,
    "articles": articles,
  }

  if debug:
    resp["debug"] = {"diversity": diversity_dbg}

  return resp


def _apply_diversity_v0(
    articles: List[Dict[str, Any]],
    diversity: int,
    k: int = 12,
    candidate_cap: int = 50,
    max_source_ratio: float = 0.6,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Deterministic diversity slider v0 for event detail articles.
    - diversity=0: baseline (time-desc) top-k
    - diversity=30: mild source/type diversification with per-source cap
    - diversity=60:暂时降级到30（下一步才做 embedding MMR）
    """
    dbg: Dict[str, Any] = {
        "diversity_level": diversity,
        "k": None,
        "candidate_cap": candidate_cap,
        "max_source_ratio": max_source_ratio,
        "notes": [],
        "distinct_sources_in_result": 0,
        "source_histogram": {},
        "type_histogram": {},
        "chosen": [],  # [{article_id, reasons, baseline_idx, source_id, type}]
    }

    if not articles:
        dbg["k"] = 0
        return [], dbg

    # baseline pool: already sorted by published_at desc
    pool = articles[:candidate_cap]
    k_eff = min(k, len(pool))
    dbg["k"] = k_eff

    if diversity == 0:
        sel = pool[:k_eff]
        # small debug stats
        cnt_source = defaultdict(int)
        cnt_type = defaultdict(int)
        for a in sel:
            sid = (a.get("source") or {}).get("source_id")
            if sid is not None:
                cnt_source[sid] += 1
            t = a.get("effective_type") or a.get("type")
            if t is not None:
                cnt_type[t] += 1
        dbg["distinct_sources_in_result"] = len(cnt_source)
        dbg["source_histogram"] = dict(cnt_source)
        dbg["type_histogram"] = dict(cnt_type)
        return sel, dbg

    if diversity == 60:
        dbg["notes"].append("diversity=60 downgraded to 30 (v0: MMR not implemented yet)")
        diversity = 30

    max_per_source = max(1, math.ceil(k_eff * max_source_ratio))

    cnt_source = defaultdict(int)
    cnt_type = defaultdict(int)

    # attach deterministic baseline idx
    for idx, a in enumerate(pool):
        a["_baseline_idx"] = idx

    remaining = pool.copy()
    chosen: List[Dict[str, Any]] = []
    chosen_meta: List[Dict[str, Any]] = []

    def source_id_of(a: Dict[str, Any]):
        s = a.get("source") or {}
        return s.get("source_id")

    def can_take(a: Dict[str, Any]) -> bool:
        sid = source_id_of(a)
        if sid is None:
            return True
        return cnt_source[sid] < max_per_source

    while len(chosen) < k_eff and remaining:
        pick = None
        reasons = None

        # Priority 1: NEW_SOURCE
        for a in remaining:
            sid = source_id_of(a)
            if sid is not None and cnt_source[sid] == 0 and can_take(a):
                pick = a
                reasons = ["NEW_SOURCE"]
                break

        # Priority 2: TYPE_COVERAGE (pick currently least represented type among remaining)
        if pick is None:
            types_present = [
                a.get("effective_type") or a.get("type")
                for a in remaining
                if (a.get("effective_type") or a.get("type")) is not None
            ]
            if types_present:
                target_type = min(set(types_present), key=lambda t: cnt_type[t])
                for a in remaining:
                    if (a.get("effective_type") or a.get("type")) == target_type and can_take(a):
                        pick = a
                        reasons = ["TYPE_COVERAGE"]
                        break

        # Priority 3: BASELINE_FILL
        if pick is None:
            for a in remaining:
                if can_take(a):
                    pick = a
                    reasons = ["BASELINE_FILL"]
                    break

        # Relax cap if needed
        if pick is None:
            dbg["notes"].append("relaxed max_per_source due to insufficient candidates")
            pick = remaining[0]
            reasons = ["CAP_RELAXED_FILL"]

        remaining.remove(pick)

        sid = source_id_of(pick)
        if sid is not None:
            cnt_source[sid] += 1
        t = pick.get("effective_type") or pick.get("type")
        if t is not None:
            cnt_type[t] += 1

        chosen.append(pick)
        chosen_meta.append({
            "article_id": pick.get("article_id"),
            "baseline_idx": pick.get("_baseline_idx"),
            "source_id": sid,
            "type": t,
            "reasons": reasons,
        })

    # cleanup helper field
    for a in chosen:
        a.pop("_baseline_idx", None)

    dbg["distinct_sources_in_result"] = len(cnt_source)
    dbg["source_histogram"] = dict(cnt_source)
    dbg["type_histogram"] = dict(cnt_type)
    dbg["chosen"] = chosen_meta
    return chosen, dbg
