from __future__ import annotations

from sqlalchemy import text

from app.database import SessionLocal


def get_event_ai(event_id: int) -> dict:
    with SessionLocal() as db:
        row = db.execute(
            text(
                """
                SELECT event_id, provider, model, status, output_json, error, updated_at
                FROM event_ai_cache
                WHERE event_id = :event_id
                ORDER BY updated_at DESC
                LIMIT 1;
                """
            ),
            {"event_id": int(event_id)},
        ).mappings().first()

    if not row:
        return {
            "event_id": int(event_id),
            "status": "MISSING",
            "provider": None,
            "model": None,
            "output": None,
            "error": None,
            "updated_at": None,
        }

    return {
        "event_id": row["event_id"],
        "status": row["status"],
        "provider": row["provider"],
        "model": row["model"],
        "output": row["output_json"],
        "error": row["error"],
        "updated_at": row["updated_at"],
    }
