#!/usr/bin/env python3
# RECONSTRUCTED_FROM_PYC_SYMBOLS
# EVIDENCE: pyc symbol extraction on 2026-02-26
# 哪些行为是占位，哪些是证据确认: 占位=所有算法与输出内容; 证据确认=脚本/模块名来自 pyc 文件名
"""
Minimal reconstructed placeholder for judge_event_merge_suggestions_v1.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

RECONSTRUCTED_FROM_PYC_SYMBOLS = True
JUDGE_VERSION = "v1-reconstructed-minimal"
MOCK_SCORE = 0.91
SUGGEST_MERGE = "SUGGEST_MERGE"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Judge merge suggestions (minimal reconstructed).")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Default mode; do not write to DB.")
    mode.add_argument("--write-db", action="store_true", help="Enable DB writes (requires --db-url).")
    parser.add_argument("--db-url", default="", help="DB connection string used only with --write-db.")
    parser.add_argument("--mock-llm", action="store_true", help="Use fixed mock judgement.")
    parser.add_argument("--event-ids", default="", help="Comma separated event ids to target.")
    parser.add_argument("--since-days", type=int, default=7, help="Lookback window in days.")
    parser.add_argument("--topk", type=int, default=20, help="Max candidate count to judge.")
    parser.add_argument("--window-hours", type=int, default=48, help="Candidate pairing window in hours.")
    parser.add_argument("--rare-df-threshold", type=float, default=2.0, help="Rare token df threshold.")
    parser.add_argument("--min-score-llm", type=float, default=0.50, help="Minimum score to keep.")
    parser.add_argument("--max-score-llm", type=float, default=0.98, help="Ceiling score for auto action.")
    parser.add_argument("--max-llm-calls", type=int, default=50, help="Max model calls allowed.")
    parser.add_argument("--auto-merge-score", type=float, default=0.90, help="Score threshold for auto merge.")
    return parser.parse_args(argv)


def _parse_event_ids(raw: str) -> list[int]:
    if not raw.strip():
        return []
    ids = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        ids.append(int(part))
    return ids


def _mock_candidates(topk: int, event_ids: list[int], since_days: int) -> list[dict]:
    if len(event_ids) >= 2:
        base_pairs = [(event_ids[i], event_ids[i + 1]) for i in range(len(event_ids) - 1)]
    else:
        base_pairs = [(2001, 2002), (2003, 2004), (2005, 2006)]
    ts = (datetime.now(timezone.utc) - timedelta(days=max(0, since_days))).isoformat()
    rows = []
    for i, (a, b) in enumerate(base_pairs[: max(1, topk)]):
        rows.append(
            {
                "event_id_a": a,
                "event_id_b": b,
                "candidate_rank": i + 1,
                "event_a_time": ts,
                "event_b_time": ts,
            }
        )
    return rows


def _log(event: str, **fields: object) -> None:
    parts = [
        "PHASE52_LOG",
        "script=judge_event_merge_suggestions_v1",
        f"event={event}",
    ]
    for key, value in fields.items():
        parts.append(f"{key}={value}")
    sys.stderr.write(" ".join(parts) + "\n")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    dry_run = True if not args.write_db else False
    if args.dry_run:
        dry_run = True
    db_enabled = bool(args.write_db and args.db_url)
    if args.write_db and not args.db_url:
        _log("warning", mode="WRITE_DB", db_enabled=False, detail="missing_db_url")

    event_ids = _parse_event_ids(args.event_ids)

    if not args.mock_llm:
        sys.stderr.write("LLM is not configured in reconstructed minimal script. Use --mock-llm.\n")
        return 2

    _log(
        "start",
        mode="DRY_RUN" if dry_run else "WRITE_DB",
        mock_llm=True,
        db_enabled=db_enabled,
        since_days=args.since_days,
    )
    candidates = _mock_candidates(args.topk, event_ids, args.since_days)
    scored = []
    for c in candidates[: max(0, args.max_llm_calls)]:
        llm_score = min(args.max_score_llm, max(args.min_score_llm, MOCK_SCORE))
        verdict = SUGGEST_MERGE if llm_score >= args.auto_merge_score else "REVIEW"
        scored.append(
            {
                **c,
                "judge_version": JUDGE_VERSION,
                "llm_mode": "mock",
                "llm_score": round(llm_score, 4),
                "verdict": verdict,
                "dry_run": args.dry_run,
            }
        )

    payload = {
        "mode": "minimal_reconstructed",
        "reconstructed": RECONSTRUCTED_FROM_PYC_SYMBOLS,
        "judge_version": JUDGE_VERSION,
        "dry_run": dry_run,
        "write_db": bool(args.write_db),
        "db_enabled": db_enabled,
        "input_event_ids": event_ids,
        "since_days": args.since_days,
        "topk": args.topk,
        "window_hours": args.window_hours,
        "rare_df_threshold": args.rare_df_threshold,
        "min_score_llm": args.min_score_llm,
        "max_score_llm": args.max_score_llm,
        "max_llm_calls": args.max_llm_calls,
        "auto_merge_score": args.auto_merge_score,
        "suggestions": scored,
    }
    _log("complete", mode="DRY_RUN" if dry_run else "WRITE_DB", suggestions=len(scored))
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

