#!/usr/bin/env python3
# RECONSTRUCTED_FROM_PYC_SYMBOLS
# EVIDENCE: pyc symbol extraction on 2026-02-26
# 哪些行为是占位，哪些是证据确认: 占位=所有算法与输出内容; 证据确认=脚本/模块名来自 pyc 文件名
"""
Minimal reconstructed placeholder for build_event_signatures_v0.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Iterable

RECONSTRUCTED_FROM_PYC_SYMBOLS = True
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
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Default mode; do not write to DB.")
    mode.add_argument("--write-db", action="store_true", help="Enable DB writes (requires --db-url).")
    parser.add_argument("--db-url", default="", help="DB connection string used only with --write-db.")
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


def _log(event: str, **fields: object) -> None:
    parts = [
        "PHASE52_LOG",
        "script=build_event_signatures_v0",
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

    since_ts = (datetime.now(timezone.utc) - timedelta(days=max(0, args.since_days))).isoformat()
    _log(
        "start",
        mode="DRY_RUN" if dry_run else "WRITE_DB",
        mock_data=True,
        db_enabled=db_enabled,
        since_days=args.since_days,
    )

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
        "reconstructed": RECONSTRUCTED_FROM_PYC_SYMBOLS,
        "dry_run": dry_run,
        "write_db": bool(args.write_db),
        "db_enabled": db_enabled,
        "since_days": args.since_days,
        "since_ts": since_ts,
        "limit_events": args.limit_events,
        "top_n": args.top_n,
        "nonempty_signature_count": sum(1 for r in rows if r["signature_v0"]),
        "events": rows,
    }
    _log("complete", mode="DRY_RUN" if dry_run else "WRITE_DB", rows=len(rows))
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

