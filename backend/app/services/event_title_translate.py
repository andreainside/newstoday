from __future__ import annotations

from sqlalchemy import text

from app.database import SessionLocal
from app.services.event_title_ai import translate_title_to_zh

PROMPT_VERSION = "title_zh_v1"

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


def get_event_title_zh(event_id: int) -> dict:
    event_id = int(event_id)
    with SessionLocal() as db:
        db.execute(text(SQL_ENSURE_TABLE))

        row = db.execute(text(SQL_GET_EVENT_TITLE), {"event_id": event_id}).mappings().first()
        if not row:
            return {
                "event_id": event_id,
                "lang": "zh",
                "status": "MISSING_EVENT",
                "title": None,
                "source_title": None,
                "prompt_version": PROMPT_VERSION,
            }

        source_title = (row["title"] or "").strip()
        if not source_title:
            return {
                "event_id": event_id,
                "lang": "zh",
                "status": "EMPTY_SOURCE_TITLE",
                "title": None,
                "source_title": source_title,
                "prompt_version": PROMPT_VERSION,
            }

        cached = db.execute(text(SQL_GET_CACHE), {"event_id": event_id}).mappings().first()
        if (
            cached
            and cached.get("status") == "SUCCESS"
            and (cached.get("source_title") or "").strip() == source_title
            and (cached.get("translated_title") or "").strip()
        ):
            return {
                "event_id": event_id,
                "lang": "zh",
                "status": "SUCCESS",
                "title": cached["translated_title"],
                "source_title": source_title,
                "prompt_version": PROMPT_VERSION,
            }

        # Avoid duplicate token usage:
        # - if another request is already processing this exact source title, do not call LLM again.
        if (
            cached
            and (cached.get("source_title") or "").strip() == source_title
            and cached.get("status") in ("PENDING", "ERROR")
        ):
            return {
                "event_id": event_id,
                "lang": "zh",
                "status": cached.get("status"),
                "title": source_title,
                "source_title": source_title,
                "prompt_version": PROMPT_VERSION,
                "error": cached.get("error"),
            }

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
            # source title changed -> refresh to pending and let current request recompute once
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
            return {
                "event_id": event_id,
                "lang": "zh",
                "status": "PENDING",
                "title": source_title,
                "source_title": source_title,
                "prompt_version": PROMPT_VERSION,
            }

        result = translate_title_to_zh(source_title)
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
        }
