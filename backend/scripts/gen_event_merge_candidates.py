#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

try:
    import psycopg
except ModuleNotFoundError:  # pragma: no cover
    psycopg = None

WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9\-]{1,}")


@dataclass
class EventRow:
    event_id: int
    title: str
    event_time: datetime | None
    signature_v0: list[str]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate event merge candidates (optimized)")
    parser.add_argument("--db-url", default=os.getenv("DATABASE_URL", ""))
    parser.add_argument("--since-days", type=int, default=7)
    parser.add_argument("--window-hours", type=int, default=72)
    parser.add_argument("--topk", type=int, default=60)
    parser.add_argument("--event-ids", default="")
    parser.add_argument("--no-title-jaccard", action="store_true")
    parser.add_argument("--max-df-ratio", type=float, default=0.35, help="ignore tokens appearing in too many events")
    parser.add_argument("--min-overlap-tokens", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--write-db", action="store_true", help="accepted for CLI parity")
    parser.add_argument("--mock-llm", action="store_true", help="accepted for CLI parity")
    return parser.parse_args(argv)


def _parse_event_ids(raw: str) -> list[int]:
    if not raw.strip():
        return []
    return [int(p.strip()) for p in raw.split(",") if p.strip()]


def _normalize_db_url(db_url: str) -> str:
    if db_url.startswith("postgresql+psycopg://"):
        return "postgresql://" + db_url[len("postgresql+psycopg://") :]
    return db_url


def _title_tokens(title: str) -> list[str]:
    return [t.lower() for t in WORD_RE.findall(title or "")]


def _parse_signature(v: object) -> list[str]:
    if isinstance(v, list):
        return [str(x).strip().lower() for x in v if str(x).strip()]
    if isinstance(v, str):
        try:
            j = json.loads(v)
            if isinstance(j, list):
                return [str(x).strip().lower() for x in j if str(x).strip()]
        except Exception:
            return [t.lower() for t in WORD_RE.findall(v)]
    return []


def _jaccard(a: str, b: str) -> float:
    sa = set(_title_tokens(a))
    sb = set(_title_tokens(b))
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _load_events(conn: psycopg.Connection, since_days: int, event_ids: list[int]) -> list[EventRow]:
    with conn.cursor() as cur:
        if event_ids:
            cur.execute(
                """
                SELECT id, COALESCE(representative_title, title, ''), COALESCE(last_updated_at, end_time, created_at), signature_v0
                FROM events
                WHERE id = ANY(%s)
                ORDER BY id ASC;
                """,
                (event_ids,),
            )
        else:
            cur.execute(
                """
                SELECT id, COALESCE(representative_title, title, ''), COALESCE(last_updated_at, end_time, created_at), signature_v0
                FROM events
                WHERE COALESCE(last_updated_at, end_time, created_at) >= (now() - (%s || ' days')::interval)
                ORDER BY COALESCE(last_updated_at, end_time, created_at) DESC, id DESC;
                """,
                (max(0, since_days),),
            )
        raw = cur.fetchall()
    return [EventRow(event_id=r[0], title=r[1] or "", event_time=r[2], signature_v0=_parse_signature(r[3])) for r in raw]


def _build_df(rows: list[EventRow]) -> dict[str, int]:
    df: dict[str, int] = {}
    for r in rows:
        for t in set(r.signature_v0):
            df[t] = df.get(t, 0) + 1
    return df


def _build_idf(df: dict[str, int], n_events: int) -> dict[str, float]:
    n = max(1, n_events)
    return {t: math.log((n + 1) / (c + 1)) + 1.0 for t, c in df.items()}


def _candidate_pairs_by_inverted_index(
    rows: list[EventRow],
    df: dict[str, int],
    idf: dict[str, float],
    *,
    max_df_ratio: float,
) -> dict[tuple[int, int], dict]:
    # token -> event indices
    inv: dict[str, list[int]] = defaultdict(list)
    n = max(1, len(rows))
    df_cap = max(2, int(n * max(0.01, min(1.0, max_df_ratio))))

    for idx, r in enumerate(rows):
        for t in set(r.signature_v0):
            if df.get(t, 0) <= df_cap:
                inv[t].append(idx)

    stats: dict[tuple[int, int], dict] = {}
    for token, postings in inv.items():
        if len(postings) < 2:
            continue
        for i_pos in range(len(postings)):
            for j_pos in range(i_pos + 1, len(postings)):
                i = postings[i_pos]
                j = postings[j_pos]
                key = (i, j) if i < j else (j, i)
                s = stats.setdefault(key, {"weight": 0.0, "tokens": [], "df_min": 10**9})
                s["weight"] += idf.get(token, 1.0)
                s["tokens"].append(token)
                s["df_min"] = min(s["df_min"], df.get(token, 10**9))
    return stats


def _fallback_pairs(rows: list[EventRow], window_hours: int) -> dict[tuple[int, int], dict]:
    # If signatures are sparse, fallback to lexical+time near pairs.
    out: dict[tuple[int, int], dict] = {}
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            a = rows[i]
            b = rows[j]
            dt_hours = abs((a.event_time - b.event_time).total_seconds()) / 3600.0 if (a.event_time and b.event_time) else 10**6
            if dt_hours > max(1, window_hours):
                continue
            jacc = _jaccard(a.title, b.title)
            if jacc >= 0.2:
                out[(i, j)] = {"weight": jacc, "tokens": [], "df_min": 999999}
    return out


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    args.db_url = _normalize_db_url(args.db_url)
    event_ids = _parse_event_ids(args.event_ids)

    if not args.db_url:
        if not args.dry_run:
            sys.stderr.write("ERROR: DATABASE_URL is missing. Set env or use --db-url.\n")
            return 2
        base = datetime.now(timezone.utc)
        rows = [
            EventRow(event_id=1001, title="Mock Mexico El Mencho update", event_time=base, signature_v0=["el mencho", "world cup"]),
            EventRow(event_id=1002, title="Mock world cup Mexico story", event_time=base, signature_v0=["el mencho", "world cup"]),
            EventRow(event_id=1003, title="Mock unrelated finance story", event_time=base, signature_v0=["market", "rate"]),
        ]
    else:
        if psycopg is None:
            sys.stderr.write("ERROR: psycopg is not installed in current Python env.\n")
            return 2
        with psycopg.connect(args.db_url) as conn:
            rows = _load_events(conn, args.since_days, event_ids)

    if not rows:
        json.dump({"candidate_count": 0, "candidates": []}, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0

    df = _build_df(rows)
    idf = _build_idf(df, len(rows))
    pair_stats = _candidate_pairs_by_inverted_index(rows, df, idf, max_df_ratio=args.max_df_ratio)
    if not pair_stats:
        pair_stats = _fallback_pairs(rows, args.window_hours)

    max_overlap = max((v["weight"] for v in pair_stats.values()), default=1.0)
    candidates: list[dict] = []

    for (i, j), st in pair_stats.items():
        a = rows[i]
        b = rows[j]
        dt_hours = abs((a.event_time - b.event_time).total_seconds()) / 3600.0 if (a.event_time and b.event_time) else 9999.0
        if dt_hours > max(1, args.window_hours):
            continue

        overlap_tokens = sorted(set(st["tokens"]))
        if len(overlap_tokens) < max(1, args.min_overlap_tokens) and st["tokens"]:
            continue

        title_j = 0.0 if args.no_title_jaccard else _jaccard(a.title, b.title)
        overlap_norm = min(1.0, st["weight"] / max(1e-6, max_overlap))
        time_bonus = max(0.0, 1.0 - dt_hours / max(1.0, float(args.window_hours)))
        score = round(0.70 * overlap_norm + 0.20 * title_j + 0.10 * time_bonus, 4)

        # low precision noise gate
        if score < 0.10 and st["weight"] < 1.5:
            continue

        candidates.append(
            {
                "event_id_a": a.event_id,
                "event_id_b": b.event_id,
                "score": score,
                "title_jaccard": round(title_j, 4),
                "time_distance_hours": round(dt_hours, 2),
                "evidence_tokens": overlap_tokens[:8],
                "top_overlap_weight": round(st["weight"], 4),
                "df_min_overlap": int(st["df_min"] if st["df_min"] < 10**9 else 0),
                "signature_v0": sorted(list(set(a.signature_v0 + b.signature_v0)))[:12],
            }
        )

    candidates.sort(key=lambda x: (x["score"], x["top_overlap_weight"]), reverse=True)
    candidates = candidates[: max(1, args.topk)]

    sys.stderr.write("event_id_a event_id_b score evidence_tokens top_overlap_weight\n")
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "since_days": args.since_days,
        "window_hours": args.window_hours,
        "topk": args.topk,
        "candidate_count": len(candidates),
        "candidates": candidates,
    }
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
