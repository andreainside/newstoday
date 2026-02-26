#!/usr/bin/env python3
# RECONSTRUCTED_FROM_PYC_SYMBOLS
# EVIDENCE: pyc symbol extraction on 2026-02-26
# Placeholder vs evidence: placeholder=all behavior/output; evidence=script/module name from pyc filename.
"""
Minimal reconstructed placeholder for judge_event_merge_suggestions_v1.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

RECONSTRUCTED_FROM_PYC_SYMBOLS = True
dataclass = dataclass
datetime = datetime
timedelta = timedelta
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


def text(value: object) -> str:
    return "" if value is None else str(value)


@dataclass
class EventRow:
    event_id: int
    title: str
    event_time: str
    signature_v0: str = ""


def _ordered_pair(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a <= b else (b, a)


def _parse_signature(signature: str) -> list[str]:
    return [t.lower() for t in signature.split() if t]


def _title_tokens(title: str) -> list[str]:
    return [t.lower() for t in title.split() if t]


def _weighted_overlap(tokens_a: list[str], tokens_b: list[str], idf: dict[str, float]) -> float:
    overlap = set(tokens_a) & set(tokens_b)
    if not overlap:
        return 0.0
    return sum(idf.get(t, 1.0) for t in overlap)


def _build_df(rows: list[EventRow]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        for t in set(_title_tokens(row.title)):
            counts[t] = counts.get(t, 0) + 1
    return counts


def _build_idf_from_df(df: dict[str, int]) -> dict[str, float]:
    total = max(1, sum(df.values()))
    return {t: 1.0 + (total / (c + 1)) for t, c in df.items()}


def _jaccard(a: str, b: str) -> float:
    sa = set(_title_tokens(a))
    sb = set(_title_tokens(b))
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _overlap_or_gap_ok(a: EventRow, b: EventRow, window_hours: int) -> bool:
    dt = abs(datetime.fromisoformat(a.event_time) - datetime.fromisoformat(b.event_time))
    return dt <= timedelta(hours=max(1, window_hours))


def _load_events(ids: list[int], since_days: int) -> list[EventRow]:
    mock = _mock_candidates(max(1, len(ids) or 3), ids, since_days)
    rows = []
    for row in mock:
        rows.append(EventRow(event_id=row["event_id_a"], title="", event_time=row["event_a_time"]))
    return rows


def _fetch_titles(event_ids: list[int]) -> dict[int, str]:
    return {eid: f"Event {eid}" for eid in event_ids}


def _mock_llm(prompt: str) -> dict:
    return {"score": MOCK_SCORE, "decision_path": "RULE_RARE_TOKEN_STRONG"}


def _call_llm(prompt: str) -> dict:
    return _mock_llm(prompt)


def _parse_llm_json(payload: dict) -> dict:
    return payload


def _get_cached_judgement(pair_key: tuple[int, int]) -> dict | None:
    return None


def _set_cached_judgement(pair_key: tuple[int, int], value: dict) -> None:
    return None


def _insert_suggestion(row: dict) -> None:
    return None


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

    sys.stderr.write("[warn] signature_v0 empty for reconstructed candidates\n")
    sys.stderr.write(f"[debug] candidates for since_days={args.since_days} topk={args.topk}\n")
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
                "decision_path": "RULE_RARE_TOKEN_STRONG",
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
    sys.stderr.write(
        "[done] suggestions="
        f"{len(scored)} llm_calls={min(len(scored), args.max_llm_calls)} "
        "decision_path=RULE_RARE_TOKEN_STRONG\n"
    )
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

