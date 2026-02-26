#!/usr/bin/env python3
# RECONSTRUCTED_FROM_PYC_SYMBOLS
# EVIDENCE: pyc symbol extraction on 2026-02-26
# Placeholder vs evidence: placeholder=all behavior/output; evidence=script/module name from pyc filename.
"""
Minimal reconstructed placeholder for gen_event_merge_candidates.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

RECONSTRUCTED_FROM_PYC_SYMBOLS = True
dataclass = dataclass
datetime = datetime
timedelta = timedelta
WORD_RE = re.compile(r"[A-Za-z0-9_]{2,}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate minimal merge candidates (reconstructed).")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Default mode; do not write to DB.")
    mode.add_argument("--write-db", action="store_true", help="Enable DB writes (requires --db-url).")
    parser.add_argument("--db-url", default="", help="DB connection string used only with --write-db.")
    parser.add_argument("--mock-llm", action="store_true", help="No-op flag for interface parity.")
    parser.add_argument("--event-ids", default="", help="Comma separated event ids, e.g. 101,102,103.")
    parser.add_argument("--no-title-jaccard", action="store_true", help="Disable title jaccard in score.")
    parser.add_argument("--since-days", type=int, default=7, help="Lookback window in days.")
    parser.add_argument("--topk", type=int, default=20, help="Maximum number of candidate pairs.")
    parser.add_argument("--window-hours", type=int, default=48, help="Temporal window for candidate pairing.")
    return parser.parse_args(argv)


def text(value: object) -> str:
    return "" if value is None else str(value)


@dataclass
class EventRow:
    event_id: int
    title: str
    event_time: str
    signature_v0: str = ""


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


def _parse_signature(signature: str) -> list[str]:
    return [t.lower() for t in WORD_RE.findall(signature)]


def _title_tokens(title: str) -> list[str]:
    return [t.lower() for t in WORD_RE.findall(title)]


def _weighted_overlap(tokens_a: list[str], tokens_b: list[str], idf: dict[str, float]) -> float:
    overlap = set(tokens_a) & set(tokens_b)
    if not overlap:
        return 0.0
    return sum(idf.get(t, 1.0) for t in overlap)


def _build_idf(rows: list[EventRow]) -> dict[str, float]:
    counts: dict[str, int] = {}
    for row in rows:
        tokens = set(_title_tokens(row.title))
        for t in tokens:
            counts[t] = counts.get(t, 0) + 1
    total = max(1, len(rows))
    return {t: math.log((total + 1) / (c + 1)) + 1.0 for t, c in counts.items()}


def _load_events(ids: list[int], since_days: int) -> list[EventRow]:
    mock = _mock_events(ids, since_days)
    return [EventRow(**row) for row in mock]


def _overlap_or_gap_ok(a: EventRow, b: EventRow, window_hours: int) -> bool:
    dt = abs(datetime.fromisoformat(a.event_time) - datetime.fromisoformat(b.event_time))
    return dt <= timedelta(hours=max(1, window_hours))


def _jaccard(a: str, b: str) -> float:
    sa = {x.lower() for x in WORD_RE.findall(a)}
    sb = {x.lower() for x in WORD_RE.findall(b)}
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _mock_events(ids: list[int], since_days: int) -> list[dict]:
    base = datetime.now(timezone.utc) - timedelta(days=max(0, since_days))
    if not ids:
        ids = [1001, 1002, 1003, 1004, 1005]
    titles = [
        "City council approves emergency housing package",
        "Emergency housing plan gets approval by city council",
        "Hospital reports increased respiratory cases",
        "Police publish update on downtown incident",
        "Court hearing scheduled for merger dispute",
    ]
    rows = []
    for i, eid in enumerate(ids):
        rows.append(
            {
                "event_id": eid,
                "title": titles[i % len(titles)],
                "event_time": (base + timedelta(hours=i * 6)).isoformat(),
            }
        )
    return rows


def _log(event: str, **fields: object) -> None:
    parts = [
        "PHASE52_LOG",
        "script=gen_event_merge_candidates",
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
    events = _mock_events(event_ids, args.since_days)
    _log(
        "start",
        mode="DRY_RUN" if dry_run else "WRITE_DB",
        mock_data=True,
        mock_llm=bool(args.mock_llm),
        db_enabled=db_enabled,
        since_days=args.since_days,
    )

    pairs = []
    for i in range(len(events)):
        for j in range(i + 1, len(events)):
            a = events[i]
            b = events[j]
            dt = abs(datetime.fromisoformat(a["event_time"]) - datetime.fromisoformat(b["event_time"]))
            if dt > timedelta(hours=max(1, args.window_hours)):
                continue
            title_jaccard = 0.0 if args.no_title_jaccard else _jaccard(a["title"], b["title"])
            time_bonus = max(0.0, 1.0 - (dt.total_seconds() / (max(1, args.window_hours) * 3600.0)))
            score = round(0.7 * title_jaccard + 0.3 * time_bonus, 4)
            evidence_tokens = ",".join(list({_ for _ in WORD_RE.findall(a["title"]) if _})[:3])
            top_overlap_weight = round(0.0 if args.no_title_jaccard else title_jaccard, 4)
            pairs.append(
                {
                    "event_id_a": a["event_id"],
                    "event_id_b": b["event_id"],
                    "title_jaccard": round(title_jaccard, 4),
                    "time_distance_hours": round(dt.total_seconds() / 3600.0, 2),
                    "score": score,
                    "evidence_tokens": evidence_tokens,
                    "top_overlap_weight": top_overlap_weight,
                    "signature_v0": f"{a['title'][:24]} | {b['title'][:24]}",
                }
            )

    pairs.sort(key=lambda x: x["score"], reverse=True)
    topk = max(1, args.topk)
    candidates = pairs[:topk]
    sys.stderr.write("event_id_a event_id_b score evidence_tokens top_overlap_weight\n")
    payload = {
        "mode": "minimal_reconstructed",
        "reconstructed": RECONSTRUCTED_FROM_PYC_SYMBOLS,
        "dry_run": dry_run,
        "write_db": bool(args.write_db),
        "db_enabled": db_enabled,
        "mock_llm": bool(args.mock_llm),
        "since_days": args.since_days,
        "window_hours": args.window_hours,
        "topk": args.topk,
        "no_title_jaccard": args.no_title_jaccard,
        "candidate_count": len(candidates),
        "candidates": candidates,
    }
    _log("complete", mode="DRY_RUN" if dry_run else "WRITE_DB", candidates=len(candidates))
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

