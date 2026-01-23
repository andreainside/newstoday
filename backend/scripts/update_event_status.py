# backend/scripts/update_event_status.py
import os
from sqlalchemy import create_engine, text

SQL_COUNT = """
SELECT status, COUNT(*)
FROM events
GROUP BY status
ORDER BY status;
"""

SQL_UPDATE = """
WITH cutoff AS (
  SELECT
    now() AS now_ts,
    now() - (:active_hours || ' hours')::interval  AS t_active,
    now() - (:closing_hours || ' hours')::interval AS t_closing
)
UPDATE events e
SET status = CASE
  WHEN e.last_updated_at >= (SELECT t_active FROM cutoff) THEN 'active'
  WHEN e.last_updated_at >= (SELECT t_closing FROM cutoff) THEN 'closing'
  ELSE 'closed'
END;
"""

def main():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise SystemExit("ERROR: DATABASE_URL not set")

    active_hours = int(os.environ.get("EVENT_ACTIVE_HOURS", "96"))
    closing_hours = int(os.environ.get("EVENT_CLOSING_HOURS", "240"))
    if closing_hours <= active_hours:
        raise SystemExit("ERROR: EVENT_CLOSING_HOURS must be > EVENT_ACTIVE_HOURS")

    engine = create_engine(db_url)

    with engine.begin() as conn:
        before = conn.execute(text(SQL_COUNT)).fetchall()
        print("Before:", before)
        print(f"Using EVENT_ACTIVE_HOURS={active_hours}, EVENT_CLOSING_HOURS={closing_hours}")

        res = conn.execute(
            text(SQL_UPDATE),
            {"active_hours": active_hours, "closing_hours": closing_hours},
        )
        print("Updated rows:", res.rowcount)

        after = conn.execute(text(SQL_COUNT)).fetchall()
        print("After:", after)

if __name__ == "__main__":
    main()
