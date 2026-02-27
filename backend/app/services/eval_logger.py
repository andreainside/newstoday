from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Iterable

try:
    import psycopg
except ModuleNotFoundError:  # pragma: no cover
    psycopg = None


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS algorithm_eval_logs (
  id bigserial PRIMARY KEY,
  run_id text NOT NULL,
  eval_type text NOT NULL,
  algorithm_name text NOT NULL,
  algorithm_version text,
  baseline_name text,
  baseline_version text,
  sample_window_hours integer,
  sample_event_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  algo_topk jsonb,
  baseline_topk jsonb,
  metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
  params jsonb NOT NULL DEFAULT '{}'::jsonb,
  notes text,
  created_at timestamptz NOT NULL DEFAULT now()
);
"""


def _normalize_db_url(db_url: str) -> str:
    if db_url.startswith("postgresql+psycopg://"):
        return "postgresql://" + db_url[len("postgresql+psycopg://") :]
    return db_url


def _ensure_schema(conn: "psycopg.Connection") -> None:
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)
    conn.commit()


def log_eval_run(
    *,
    db_url: str | None = None,
    run_id: str,
    eval_type: str,
    algorithm_name: str,
    algorithm_version: str | None = None,
    baseline_name: str | None = None,
    baseline_version: str | None = None,
    sample_window_hours: int | None = None,
    sample_event_ids: Iterable[int] | None = None,
    algo_topk: Iterable[int] | None = None,
    baseline_topk: Iterable[int] | None = None,
    metrics: Dict[str, Any] | None = None,
    params: Dict[str, Any] | None = None,
    notes: str | None = None,
) -> None:
    if psycopg is None:
        raise RuntimeError("psycopg is not installed; cannot write eval logs.")

    db_url = _normalize_db_url(db_url or os.getenv("DATABASE_URL", ""))
    if not db_url:
        raise RuntimeError("DATABASE_URL is missing; cannot write eval logs.")

    payload_metrics = metrics or {}
    payload_params = params or {}

    with psycopg.connect(db_url) as conn:
        _ensure_schema(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO algorithm_eval_logs (
                  run_id,
                  eval_type,
                  algorithm_name,
                  algorithm_version,
                  baseline_name,
                  baseline_version,
                  sample_window_hours,
                  sample_event_ids,
                  algo_topk,
                  baseline_topk,
                  metrics,
                  params,
                  notes,
                  created_at
                ) VALUES (
                  %(run_id)s,
                  %(eval_type)s,
                  %(algorithm_name)s,
                  %(algorithm_version)s,
                  %(baseline_name)s,
                  %(baseline_version)s,
                  %(sample_window_hours)s,
                  CAST(%(sample_event_ids)s AS jsonb),
                  CAST(%(algo_topk)s AS jsonb),
                  CAST(%(baseline_topk)s AS jsonb),
                  CAST(%(metrics)s AS jsonb),
                  CAST(%(params)s AS jsonb),
                  %(notes)s,
                  %(created_at)s
                );
                """,
                {
                    "run_id": run_id,
                    "eval_type": eval_type,
                    "algorithm_name": algorithm_name,
                    "algorithm_version": algorithm_version,
                    "baseline_name": baseline_name,
                    "baseline_version": baseline_version,
                    "sample_window_hours": sample_window_hours,
                    "sample_event_ids": json.dumps(list(sample_event_ids or []), ensure_ascii=False),
                    "algo_topk": json.dumps(list(algo_topk or []), ensure_ascii=False),
                    "baseline_topk": json.dumps(list(baseline_topk or []), ensure_ascii=False),
                    "metrics": json.dumps(payload_metrics, ensure_ascii=False),
                    "params": json.dumps(payload_params, ensure_ascii=False),
                    "notes": notes,
                    "created_at": datetime.now(timezone.utc),
                },
            )
        conn.commit()
