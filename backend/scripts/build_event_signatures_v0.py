#!/usr/bin/env python3
# RECONSTRUCTED_FROM_PYC_SYMBOLS
# EVIDENCE: pyc symbol extraction on 2026-02-26
# Placeholder vs evidence: placeholder=all behavior/output; evidence=script/module name from pyc filename.
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
Counter = Counter
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
    parser.add_argument("--mock-llm", action="store_true", help="No-op flag for interface parity.")
    parser.add_argument("--since-days", type=int, default=7, help="Lookback window in days.")
    parser.add_argument("--limit-events", type=int, default=200, help="Maximum events to process.")
    parser.add_argument("--top-n", type=int, default=8, help="Top N tokens kept in signature.")
    return parser.parse_args(argv)


def text(value: object) -> str:
    return "" if value is None else str(value)


def _clean_token(token: str) -> str:
    return token.strip().lower()


def _allow_token(token: str) -> bool:
    return bool(token) and token not in SINGLE_WORD_STOP


def _tokenize(text: str) -> list[str]:
    tokens = [_clean_token(t) for t in WORD_RE.findall(text)]
    return [t for t in tokens if _allow_token(t)]


def _extract_from_title(title: str) -> list[str]:
    return _tokenize(title)


def _extract_from_text(body: str) -> list[str]:
    return _tokenize(body)


def _add_keywords(tokens: list[str], keywords: Iterable[str]) -> list[str]:
    merged = list(tokens)
    for kw in keywords:
        clean = _clean_token(kw)
        if _allow_token(clean):
            merged.append(clean)
    return merged


def _build_signature(title: str, top_n: int) -> str:
    counts = Counter(_extract_from_title(title))
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
        mock_llm=bool(args.mock_llm),
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
    empty_count = sum(1 for r in rows if not r["signature_v0"])
    nonempty_count = sum(1 for r in rows if r["signature_v0"])
    sys.stderr.write(
        "[done] build_event_signatures_v0 scanned="
        f"{len(rows)} updated={len(rows)} empty_signature_count={empty_count} "
        f"nonempty_signature_count={nonempty_count}\n"
    )

    payload = {
        "mode": "minimal_reconstructed",
        "reconstructed": RECONSTRUCTED_FROM_PYC_SYMBOLS,
        "dry_run": dry_run,
        "write_db": bool(args.write_db),
        "db_enabled": db_enabled,
        "mock_llm": bool(args.mock_llm),
        "since_days": args.since_days,
        "since_ts": since_ts,
        "limit_events": args.limit_events,
        "top_n": args.top_n,
        "nonempty_signature_count": nonempty_count,
        "events": rows,
    }
    _log("complete", mode="DRY_RUN" if dry_run else "WRITE_DB", rows=len(rows))
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

