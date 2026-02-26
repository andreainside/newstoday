#!/usr/bin/env python3
"""
RECONSTRUCTED_FROM_PYC_CLUES
Minimal reconstructed version from pyc symbol/flag clues.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

RECONSTRUCTED_FROM_PYC_CLUES = True
JUDGE_VERSION = "v1-reconstructed-minimal"
MOCK_SCORE = 0.91
SUGGEST_MERGE = "SUGGEST_MERGE"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Judge merge suggestions (minimal reconstructed).")
    parser.add_argument("--dry-run", action="store_true", help="Do not persist suggestions.")
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


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    event_ids = _parse_event_ids(args.event_ids)

    if not args.mock_llm:
        sys.stderr.write("LLM is not configured in reconstructed minimal script. Use --mock-llm.\n")
        return 2

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
        "reconstructed": RECONSTRUCTED_FROM_PYC_CLUES,
        "judge_version": JUDGE_VERSION,
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
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

