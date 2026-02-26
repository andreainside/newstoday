#!/usr/bin/env python3
"""
RECONSTRUCTED_FROM_PYC_CLUES
Minimal reconstructed version from pyc symbol/flag clues.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Iterable

RECONSTRUCTED_FROM_PYC_CLUES = True
ORG_EVENT_KEYWORDS = {
    "police",
    "court",
    "hospital",
    "government",
    "ministry",
    "company",
    "agency",
}
SINGLE_WORD_STOP = {"the", "a", "an", "to", "for", "of", "in", "on", "and", "or", "with"}
WORD_RE = re.compile(r"[A-Za-z0-9_]{2,}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build simple event signatures (v0, reconstructed).")
    parser.add_argument("--since-days", type=int, default=7, help="Lookback window in days.")
    parser.add_argument("--limit-events", type=int, default=200, help="Maximum events to process.")
    parser.add_argument("--top-n", type=int, default=8, help="Top N tokens kept in signature.")
    return parser.parse_args(argv)


def _tokenize(text: str) -> list[str]:
    tokens = [t.lower() for t in WORD_RE.findall(text)]
    return [t for t in tokens if t not in SINGLE_WORD_STOP]


def _build_signature(title: str, top_n: int) -> str:
    counts = Counter(_tokenize(title))
    ranked = [w for w, _ in counts.most_common(max(1, top_n))]
    return " ".join(ranked)


def _mock_events(limit_events: int) -> Iterable[dict]:
    sample = [
        "City council approves emergency housing package",
        "Hospital reports increased respiratory cases",
        "Court hearing scheduled for merger dispute",
        "Police publish update on downtown incident",
        "Agency releases guidance for flood preparation",
    ]
    now = datetime.now(timezone.utc)
    for idx in range(1, max(1, limit_events) + 1):
        yield {
            "event_id": idx,
            "title": sample[(idx - 1) % len(sample)],
            "updated_at": (now - timedelta(hours=idx)).isoformat(),
        }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    since_ts = (datetime.now(timezone.utc) - timedelta(days=max(0, args.since_days))).isoformat()

    rows = []
    for event in _mock_events(args.limit_events):
        signature_v0 = _build_signature(event["title"], args.top_n)
        rows.append(
            {
                "event_id": event["event_id"],
                "signature_v0": signature_v0,
                "keywords_hit": sorted(ORG_EVENT_KEYWORDS.intersection(signature_v0.split())),
                "updated_at": event["updated_at"],
            }
        )

    payload = {
        "mode": "minimal_reconstructed",
        "reconstructed": RECONSTRUCTED_FROM_PYC_CLUES,
        "since_days": args.since_days,
        "since_ts": since_ts,
        "limit_events": args.limit_events,
        "top_n": args.top_n,
        "nonempty_signature_count": sum(1 for r in rows if r["signature_v0"]),
        "events": rows,
    }
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

