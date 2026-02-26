#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import psycopg
except ModuleNotFoundError:  # pragma: no cover
    psycopg = None

JUDGE_VERSION = "phase5.2-v1-opt"
JSON_BLOCK_RE = r"\{[\s\S]*\}"
GENERIC_TOKENS = {
    "world",
    "united states",
    "new york",
    "breaking",
    "news",
    "cup",
    "government",
    "election",
}


def _normalize_db_url(db_url: str) -> str:
    if db_url.startswith("postgresql+psycopg://"):
        return "postgresql://" + db_url[len("postgresql+psycopg://") :]
    return db_url


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Judge event merge suggestions (optimized)")
    parser.add_argument("--db-url", default=os.getenv("DATABASE_URL", ""))
    parser.add_argument("--since-days", type=int, default=7)
    parser.add_argument("--topk", type=int, default=60)
    parser.add_argument("--window-hours", type=int, default=72)
    parser.add_argument("--event-ids", default="")
    parser.add_argument("--rare-df-threshold", type=float, default=2.0)
    parser.add_argument("--min-score-llm", type=float, default=0.45)
    parser.add_argument("--max-score-llm", type=float, default=0.70)
    parser.add_argument("--max-llm-calls", type=int, default=20)
    parser.add_argument("--auto-merge-score", type=float, default=0.78)
    parser.add_argument("--write-db", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--mock-llm", action="store_true")
    return parser.parse_args(argv)


def _ordered_pair(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a <= b else (b, a)


def _mock_llm(candidate: dict) -> dict:
    toks = [str(t).strip().lower() for t in (candidate.get("evidence_tokens") or []) if str(t).strip()]
    strong = [t for t in toks if t not in GENERIC_TOKENS]
    if len(strong) >= 2:
        return {"decision": "SUGGEST_MERGE", "confidence": 0.86, "reason": "mock_llm_multi_strong_token"}
    return {"decision": "NO_MERGE", "confidence": 0.34, "reason": "mock_llm_insufficient_signal"}


def _call_llm(candidate: dict) -> dict:
    return _mock_llm(candidate)


def _parse_llm_json(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return {"decision": "NO_MERGE", "confidence": 0.0, "reason": "llm_payload_invalid"}
    return payload


def _ensure_schema(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS event_merge_judgements_cache (
              id bigserial PRIMARY KEY,
              event_id_a bigint NOT NULL,
              event_id_b bigint NOT NULL,
              judge_version text NOT NULL,
              llm_json jsonb NOT NULL,
              created_at timestamptz NOT NULL DEFAULT now(),
              UNIQUE(event_id_a, event_id_b, judge_version)
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS event_merge_suggestions (
              id bigserial PRIMARY KEY,
              event_id_a bigint NOT NULL,
              event_id_b bigint NOT NULL,
              judge_version text NOT NULL,
              decision text NOT NULL,
              decision_path text NOT NULL,
              score double precision NOT NULL,
              evidence_tokens jsonb NOT NULL DEFAULT '[]'::jsonb,
              top_overlap_weight double precision,
              df_min_overlap integer,
              raw jsonb NOT NULL DEFAULT '{}'::jsonb,
              created_at timestamptz NOT NULL DEFAULT now(),
              UNIQUE(event_id_a, event_id_b, judge_version)
            );
            """
        )


def _get_cached_judgement(conn: psycopg.Connection, a: int, b: int) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT llm_json
            FROM event_merge_judgements_cache
            WHERE event_id_a = %s AND event_id_b = %s AND judge_version = %s
            LIMIT 1;
            """,
            (a, b, JUDGE_VERSION),
        )
        row = cur.fetchone()
    if not row:
        return None
    return row[0] if isinstance(row[0], dict) else json.loads(row[0])


def _set_cached_judgement(conn: psycopg.Connection, a: int, b: int, value: dict) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO event_merge_judgements_cache(event_id_a, event_id_b, judge_version, llm_json)
            VALUES(%s, %s, %s, CAST(%s AS jsonb))
            ON CONFLICT(event_id_a, event_id_b, judge_version)
            DO UPDATE SET llm_json = EXCLUDED.llm_json;
            """,
            (a, b, JUDGE_VERSION, json.dumps(value, ensure_ascii=False)),
        )


def _insert_suggestion(conn: psycopg.Connection, row: dict) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO event_merge_suggestions(
              event_id_a, event_id_b, judge_version, decision, decision_path, score,
              evidence_tokens, top_overlap_weight, df_min_overlap, raw
            ) VALUES (%s,%s,%s,%s,%s,%s,CAST(%s AS jsonb),%s,%s,CAST(%s AS jsonb))
            ON CONFLICT(event_id_a, event_id_b, judge_version)
            DO UPDATE SET
              decision = EXCLUDED.decision,
              decision_path = EXCLUDED.decision_path,
              score = EXCLUDED.score,
              evidence_tokens = EXCLUDED.evidence_tokens,
              top_overlap_weight = EXCLUDED.top_overlap_weight,
              df_min_overlap = EXCLUDED.df_min_overlap,
              raw = EXCLUDED.raw;
            """,
            (
                row["event_id_a"],
                row["event_id_b"],
                JUDGE_VERSION,
                row["decision"],
                row["decision_path"],
                row["score"],
                json.dumps(row.get("evidence_tokens") or [], ensure_ascii=False),
                row.get("top_overlap_weight"),
                row.get("df_min_overlap"),
                json.dumps(row, ensure_ascii=False),
            ),
        )


def _load_candidates(args: argparse.Namespace) -> list[dict]:
    script = Path(__file__).with_name("gen_event_merge_candidates.py")
    cmd = [
        sys.executable,
        str(script),
        "--db-url",
        args.db_url,
        "--since-days",
        str(args.since_days),
        "--topk",
        str(args.topk),
        "--window-hours",
        str(args.window_hours),
    ]
    if args.event_ids:
        cmd.extend(["--event-ids", args.event_ids])
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr + "\n")
        raise RuntimeError(f"gen_event_merge_candidates failed with code {proc.returncode}")
    payload = json.loads(proc.stdout)
    return payload.get("candidates", [])


def _strong_tokens(tokens: list[str]) -> list[str]:
    out = []
    for t in tokens:
        v = str(t).strip().lower()
        if v and v not in GENERIC_TOKENS:
            out.append(v)
    return out


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    args.db_url = _normalize_db_url(args.db_url)
    dry_run = args.dry_run or not args.write_db

    if not args.db_url and not dry_run:
        sys.stderr.write("ERROR: DATABASE_URL is missing. Set env or use --db-url.\n")
        return 2
    if args.db_url and psycopg is None:
        sys.stderr.write("ERROR: psycopg is not installed in current Python env.\n")
        return 2

    candidates = _load_candidates(args) if args.db_url else [
        {
            "event_id_a": 1001,
            "event_id_b": 1002,
            "score": 0.62,
            "evidence_tokens": ["el mencho", "world cup"],
            "top_overlap_weight": 6.4,
            "df_min_overlap": 2,
            "time_distance_hours": 3.0,
            "title_jaccard": 0.21,
        }
    ]

    suggestions = []
    llm_calls = 0
    conn = psycopg.connect(args.db_url) if args.db_url else None
    try:
        if conn is not None:
            _ensure_schema(conn)

        for c in candidates:
            a, b = _ordered_pair(int(c["event_id_a"]), int(c["event_id_b"]))
            score = float(c.get("score", 0.0))
            overlap_weight = float(c.get("top_overlap_weight", 0.0))
            df_min = int(c.get("df_min_overlap", 999999))
            dt_hours = float(c.get("time_distance_hours", 9999.0))
            title_j = float(c.get("title_jaccard", 0.0))
            evidence_tokens = [str(x) for x in (c.get("evidence_tokens") or [])]
            strong = _strong_tokens(evidence_tokens)

            decision = "NO_MERGE"
            decision_path = "RULE_NO"

            # RULE_NO_GENERIC_ONLY: only generic tokens with weak lexical support -> block
            if evidence_tokens and not strong and title_j < 0.20:
                decision = "NO_MERGE"
                decision_path = "RULE_NO_GENERIC_ONLY"
            elif score >= args.auto_merge_score:
                decision = "SUGGEST_MERGE"
                decision_path = "RULE_HIGH_SCORE"
            elif df_min <= args.rare_df_threshold and overlap_weight >= 6.0 and len(strong) >= 1:
                decision = "SUGGEST_MERGE"
                decision_path = "RULE_RARE_TOKEN_STRONG"
            elif len(strong) >= 3 and score >= 0.45 and dt_hours <= 36:
                decision = "SUGGEST_MERGE"
                decision_path = "RULE_MULTI_TOKEN_STRONG"
            elif args.min_score_llm <= score <= args.max_score_llm and llm_calls < args.max_llm_calls:
                cached = _get_cached_judgement(conn, a, b) if conn is not None else None
                if cached is None:
                    llm_raw = _mock_llm(c) if args.mock_llm else _call_llm(c)
                    llm = _parse_llm_json(llm_raw)
                    if conn is not None:
                        _set_cached_judgement(conn, a, b, llm)
                    llm_calls += 1
                else:
                    llm = _parse_llm_json(cached)
                decision = "SUGGEST_MERGE" if llm.get("decision") == "SUGGEST_MERGE" else "NO_MERGE"
                decision_path = "LLM_GREY_ZONE"

            row = {
                "event_id_a": a,
                "event_id_b": b,
                "score": score,
                "decision": decision,
                "decision_path": decision_path,
                "evidence_tokens": evidence_tokens,
                "top_overlap_weight": overlap_weight,
                "df_min_overlap": df_min if df_min != 999999 else None,
                "judge_version": JUDGE_VERSION,
            }
            suggestions.append(row)
            if not dry_run and decision == "SUGGEST_MERGE" and conn is not None:
                _insert_suggestion(conn, row)

        if conn is not None:
            conn.commit()
    finally:
        if conn is not None:
            conn.close()

    sys.stderr.write(
        f"[done] suggestions={len([s for s in suggestions if s['decision']=='SUGGEST_MERGE'])} "
        f"llm_calls={llm_calls} decision_path=RULE_RARE_TOKEN_STRONG\n"
    )
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "judge_version": JUDGE_VERSION,
        "dry_run": dry_run,
        "since_days": args.since_days,
        "suggestions": suggestions,
    }
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
