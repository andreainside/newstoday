from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.database import SessionLocal
from app.observability import log_json
from app.services.event_title_ai import translate_title_to_zh

PROMPT_VERSION = "title_zh_v1"
PENDING_RETRY_SECONDS = int(os.getenv("EVENT_TITLE_ZH_PENDING_RETRY_SECONDS", "90"))
AUTO_CREATE_TABLE = os.getenv("EVENT_TITLE_ZH_AUTO_CREATE_TABLE", "1") == "1"

SQL_ENSURE_TABLE = """
CREATE TABLE IF NOT EXISTS event_title_i18n_cache (
  event_id bigint NOT NULL,
  lang text NOT NULL,
  source_title text NOT NULL,
  translated_title text,
  provider text,
  model text,
  status text NOT NULL DEFAULT 'PENDING',
  error text,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (event_id, lang)
);
"""

FALLBACK_SQL_ENSURE_TABLE = """
CREATE TABLE IF NOT EXISTS event_title_i18n_cache (
  event_id bigint NOT NULL,
  lang text NOT NULL,
  source_title text NOT NULL,
  translated_title text,
  provider text,
  model text,
  status text NOT NULL DEFAULT 'PENDING',
  error text,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (event_id, lang)
);
"""

SQL_GET_EVENT_TITLE = """
SELECT COALESCE(e.representative_title, e.title) AS title
FROM events e
WHERE e.id = :event_id
LIMIT 1;
"""

SQL_GET_CACHE = """
SELECT source_title, translated_title, status, error, updated_at
FROM event_title_i18n_cache
WHERE event_id = :event_id AND lang = 'zh'
LIMIT 1;
"""

SQL_GET_AI_SUMMARY_TITLE = """
SELECT output_json->>'title' AS title
FROM event_ai_cache
WHERE event_id = :event_id
  AND provider = 'deepseek'
  AND status = 'SUCCESS'
ORDER BY updated_at DESC
LIMIT 1;
"""

SQL_CLAIM_PENDING = """
INSERT INTO event_title_i18n_cache (
  event_id, lang, source_title, translated_title, provider, model, status, error, updated_at
)
VALUES (
  :event_id, 'zh', :source_title, NULL, NULL, NULL, 'PENDING', NULL, now()
)
ON CONFLICT (event_id, lang) DO NOTHING
RETURNING event_id;
"""

SQL_UPSERT_CACHE = """
INSERT INTO event_title_i18n_cache (
  event_id, lang, source_title, translated_title, provider, model, status, error, updated_at
)
VALUES (
  :event_id, 'zh', :source_title, :translated_title, :provider, :model, :status, :error, now()
)
ON CONFLICT (event_id, lang)
DO UPDATE SET
  source_title = EXCLUDED.source_title,
  translated_title = EXCLUDED.translated_title,
  provider = EXCLUDED.provider,
  model = EXCLUDED.model,
  status = EXCLUDED.status,
  error = EXCLUDED.error,
  updated_at = now();
"""


def _log_cache_event(event_id: int, model: str | None, status: str, error: str | None, cache_hit: bool) -> None:
    log_json(
        "deepseek_call",
        event_id=event_id,
        provider="deepseek",
        model=model,
        status=status,
        error_type=error,
        http_status=None,
        latency_ms=0,
        cache_hit=cache_hit,
    )


def _is_pending_fresh(updated_at: object) -> bool:
    if not isinstance(updated_at, datetime):
        return False
    ts = updated_at if updated_at.tzinfo else updated_at.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - ts) < timedelta(seconds=PENDING_RETRY_SECONDS)


def _bootstrap_cache_table(db) -> None:
    # Keep local-like behavior by default; can be disabled in strict production via env.
    # Defensive fallback: if conflict resolution accidentally drops SQL_ENSURE_TABLE,
    # keep runtime behavior functional instead of crashing with NameError.
    if AUTO_CREATE_TABLE:
        ddl = globals().get("SQL_ENSURE_TABLE") or FALLBACK_SQL_ENSURE_TABLE
        db.execute(text(ddl))


def _pick_translation_source_title(db, event_id: int, fallback_title: str) -> str:
    # Prefer the generated English summary when available, so zh translation tracks
    # the same content shown in /en.
    try:
        row = db.execute(text(SQL_GET_AI_SUMMARY_TITLE), {"event_id": event_id}).mappings().first()
        ai_title = ((row or {}).get("title") or "").strip()
        if ai_title:
            return ai_title
    except Exception as exc:
        log_json("deepseek_translate_source_fallback", event_id=event_id, error_type=type(exc).__name__)
    return fallback_title


def get_event_title_zh(event_id: int) -> dict:
    event_id = int(event_id)
    with SessionLocal() as db:
        _bootstrap_cache_table(db)

        row = db.execute(text(SQL_GET_EVENT_TITLE), {"event_id": event_id}).mappings().first()
        if not row:
            return {
                "event_id": event_id,
                "lang": "zh",
                "status": "MISSING_EVENT",
                "title": None,
                "source_title": None,
                "prompt_version": PROMPT_VERSION,
                "cache_hit": False,
            }

        source_title = _pick_translation_source_title(
            db,
            event_id=event_id,
            fallback_title=(row["title"] or "").strip(),
        )
        if not source_title:
            return {
                "event_id": event_id,
                "lang": "zh",
                "status": "EMPTY_SOURCE_TITLE",
                "title": None,
                "source_title": source_title,
                "prompt_version": PROMPT_VERSION,
                "cache_hit": False,
            }

        cached = db.execute(text(SQL_GET_CACHE), {"event_id": event_id}).mappings().first()
        if (
            cached
            and cached.get("status") == "SUCCESS"
            and (cached.get("source_title") or "").strip() == source_title
            and (cached.get("translated_title") or "").strip()
        ):
            _log_cache_event(event_id, None, "SUCCESS", None, cache_hit=True)
            return {
                "event_id": event_id,
                "lang": "zh",
                "status": "SUCCESS",
                "title": cached["translated_title"],
                "source_title": source_title,
                "prompt_version": PROMPT_VERSION,
                "cache_hit": True,
            }

        if cached and (cached.get("source_title") or "").strip() == source_title:
            status = str(cached.get("status") or "")

            # Core behavior from commit 5de0446:
            # - fresh PENDING: avoid duplicate token usage
            # - stale PENDING / ERROR: retry to self-heal after transient failures
            if status == "PENDING" and _is_pending_fresh(cached.get("updated_at")):
                _log_cache_event(event_id, None, "PENDING", "pending_in_progress", cache_hit=True)
                return {
                    "event_id": event_id,
                    "lang": "zh",
                    "status": "PENDING",
                    "title": source_title,
                    "source_title": source_title,
                    "prompt_version": PROMPT_VERSION,
                    "cache_hit": True,
                }

            if status in ("PENDING", "ERROR"):
                _log_cache_event(event_id, None, "RETRY", status.lower(), cache_hit=False)

        claimed = False
        if cached is None:
            claim_row = db.execute(
                text(SQL_CLAIM_PENDING),
                {
                    "event_id": event_id,
                    "source_title": source_title,
                },
            ).mappings().first()
            claimed = bool(claim_row)
            db.commit()
        else:
            db.execute(
                text(SQL_UPSERT_CACHE),
                {
                    "event_id": event_id,
                    "source_title": source_title,
                    "translated_title": None,
                    "provider": None,
                    "model": None,
                    "status": "PENDING",
                    "error": None,
                },
            )
            db.commit()
            claimed = True

        if not claimed:
            _log_cache_event(event_id, None, "PENDING", "cache_claim_failed", cache_hit=True)
            return {
                "event_id": event_id,
                "lang": "zh",
                "status": "PENDING",
                "title": source_title,
                "source_title": source_title,
                "prompt_version": PROMPT_VERSION,
                "cache_hit": True,
            }

        result = translate_title_to_zh(source_title, event_id=event_id)
        if result.get("ok") and result.get("translated_title"):
            db.execute(
                text(SQL_UPSERT_CACHE),
                {
                    "event_id": event_id,
                    "source_title": source_title,
                    "translated_title": result["translated_title"],
                    "provider": result.get("provider"),
                    "model": result.get("model"),
                    "status": "SUCCESS",
                    "error": None,
                },
            )
            db.commit()
            return {
                "event_id": event_id,
                "lang": "zh",
                "status": "SUCCESS",
                "title": result["translated_title"],
                "source_title": source_title,
                "prompt_version": PROMPT_VERSION,
                "cache_hit": False,
            }

        db.execute(
            text(SQL_UPSERT_CACHE),
            {
                "event_id": event_id,
                "source_title": source_title,
                "translated_title": None,
                "provider": result.get("provider"),
                "model": result.get("model"),
                "status": "ERROR",
                "error": str(result.get("error") or "unknown_error")[:1000],
            },
        )
        db.commit()
        return {
            "event_id": event_id,
            "lang": "zh",
            "status": "ERROR",
            "title": source_title,
            "source_title": source_title,
            "prompt_version": PROMPT_VERSION,
            "error": result.get("error"),
            "cache_hit": False,
        }
