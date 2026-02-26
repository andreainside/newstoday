#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def run_step(cmd: list[str], cwd: Path) -> int:
    print(f"$ {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=str(cwd))
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 5.2 merge pipeline on live DB.")
    parser.add_argument("--since-days", type=int, default=7)
    parser.add_argument("--write-db", action="store_true")
    parser.add_argument("--mock-llm", action="store_true")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    scripts_dir = repo_root / "backend" / "scripts"
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        print("ERROR: DATABASE_URL is missing.")
        return 2

    mode_flag = "--write-db" if args.write_db else "--dry-run"
    mock_flag = ["--mock-llm"] if args.mock_llm else []

    steps = [
        [
            sys.executable,
            str(scripts_dir / "build_event_signatures_v0.py"),
            "--db-url",
            db_url,
            "--since-days",
            str(args.since_days),
            mode_flag,
        ]
        + mock_flag,
        [
            sys.executable,
            str(scripts_dir / "gen_event_merge_candidates.py"),
            "--db-url",
            db_url,
            "--since-days",
            str(args.since_days),
            mode_flag,
        ]
        + mock_flag,
        [
            sys.executable,
            str(scripts_dir / "judge_event_merge_suggestions_v1.py"),
            "--db-url",
            db_url,
            "--since-days",
            str(args.since_days),
            mode_flag,
        ]
        + mock_flag,
    ]

    for step in steps:
        rc = run_step(step, repo_root)
        if rc != 0:
            return rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
