#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

try:
    import psycopg
except ModuleNotFoundError:  # pragma: no cover
    psycopg = None

from app.services.eval_logger import log_eval_run


def _normalize_db_url(db_url: str) -> str:
    if db_url.startswith("postgresql+psycopg://"):
        return "postgresql://" + db_url[len("postgresql+psycopg://") :]
    return db_url


def _fetch_view(conn: "psycopg.Connection", view_name: str, days: int) -> List[Dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT *
            FROM {view_name}
            WHERE day >= (now() - (%s || ' days')::interval)
            ORDER BY day DESC;
            """,
            (max(1, int(days)),),
        )
        cols = [d.name for d in cur.description]
        rows = cur.fetchall()
    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append({cols[i]: r[i] for i in range(len(cols))})
    return out


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Daily eval dashboard summary")
    parser.add_argument("--db-url", default=os.getenv("DATABASE_URL", ""))
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--write-params", action="store_true")
    parser.add_argument("--window-hours", type=int, default=72)
    parser.add_argument("--tau-hours", type=int, default=24)
    parser.add_argument("--w-hot", type=float, default=0.45)
    parser.add_argument("--w-div", type=float, default=0.35)
    parser.add_argument("--w-fresh", type=float, default=0.20)
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv)
    db_url = _normalize_db_url(args.db_url)
    if not db_url:
        raise SystemExit("ERROR: DATABASE_URL is missing.")
    if psycopg is None:
        raise SystemExit("ERROR: psycopg is not installed in current Python env.")

    if args.write_params:
        log_eval_run(
            run_id=f"top_events_params_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
            eval_type="top_events_params",
            algorithm_name="top_events_v0",
            algorithm_version="v0",
            baseline_name=None,
            baseline_version=None,
            sample_window_hours=args.window_hours,
            sample_event_ids=[],
            algo_topk=[],
            baseline_topk=[],
            metrics={},
            params={
                "window_hours": args.window_hours,
                "tau_hours": args.tau_hours,
                "weights": {"hot": args.w_hot, "div": args.w_div, "fresh": args.w_fresh},
            },
            notes="auto logged by dashboard_eval_daily.py",
        )

    with psycopg.connect(db_url) as conn:
        out = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "vw_top_events_params_daily": _fetch_view(conn, "vw_top_events_params_daily", args.days),
            "vw_gap_hints_daily": _fetch_view(conn, "vw_gap_hints_daily", args.days),
        }

    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
