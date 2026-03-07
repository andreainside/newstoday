from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class Step:
    name: str
    cmd: list[str]
    supports_dry_run: bool
    incremental_safe: bool
    parse_counts: callable


def _utc_now_iso() -> str:
    return datetime.utcnow().isoformat()


def _print_kv(**kwargs) -> None:
    parts = [f"{k}={v}" for k, v in kwargs.items()]
    print(" ".join(parts))


def _env_int(name: str, default: int, *, min_value: int = 1, max_value: int = 20000) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        v = int(str(raw).strip())
    except Exception:
        return default
    if v < min_value:
        return min_value
    if v > max_value:
        return max_value
    return v


def _parse_fetch_rss(text: str) -> dict:
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        parsed = {
            "articles_inserted": int(payload.get("articles_inserted", 0)),
            "articles_duplicate": int(payload.get("articles_duplicate", 0)),
            "sources_ok": int(payload.get("sources_ok", 0)),
            "sources_failed": int(payload.get("sources_failed", 0)),
        }
        return parsed

    m = re.search(r"Total inserted\s*=\s*(\d+)", text)
    if m:
        return {"articles_inserted": int(m.group(1))}
    if "No sources found" in text:
        return {"articles_inserted": 0}
    return {"articles_inserted": "unknown"}


def _parse_seed_sources(text: str) -> dict:
    m = re.search(r"Inserted\s+(\d+)\s+new\s+sources", text)
    if m:
        return {"sources_inserted": int(m.group(1))}
    return {"sources_inserted": "unknown"}


def _parse_backfill_embeddings(text: str) -> dict:
    m = re.search(r"updated\s+(\d+)\s+rows", text)
    if m:
        return {"embeddings_updated": int(m.group(1))}
    if "nothing to backfill" in text:
        return {"embeddings_updated": 0}
    return {"embeddings_updated": "unknown"}


def _parse_cluster_events(text: str) -> dict:
    m = re.search(r"articles since .* = (\d+)", text)
    if m:
        return {"articles_considered": int(m.group(1))}
    return {"articles_considered": "unknown"}


def _parse_backfill_article_types(text: str) -> dict:
    m = re.search(r"Updated\s+(\d+)\s+articles", text)
    if m:
        return {"article_types_updated": int(m.group(1))}
    return {"article_types_updated": "unknown"}


def _print_pipeline_probe(*, backend_dir: Path) -> None:
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        _print_kv(step="pipeline_probe", status="skipped", reason="missing_DATABASE_URL")
        return

    probe_sql = """
    WITH latest_article AS (
      SELECT published_at
      FROM articles
      ORDER BY published_at DESC NULLS LAST
      LIMIT 1
    ),
    latest_event AS (
      SELECT COALESCE(last_updated_at, end_time, created_at) AS ts
      FROM events
      ORDER BY COALESCE(last_updated_at, end_time, created_at) DESC NULLS LAST
      LIMIT 1
    )
    SELECT
      (SELECT published_at FROM latest_article) AS latest_article_ts,
      (SELECT ts FROM latest_event) AS latest_event_ts,
      (
        SELECT COUNT(*)
        FROM articles a
        LEFT JOIN event_articles ea ON ea.article_id = a.id
        WHERE a.published_at >= (NOW() - INTERVAL '24 hours')
          AND a.embedding IS NOT NULL
          AND ea.article_id IS NULL
      ) AS unlinked_articles_24h;
    """

    cmd = [
        sys.executable,
        "-c",
        (
            "import os, json\n"
            "from sqlalchemy import create_engine, text\n"
            "db_url = os.environ['DATABASE_URL']\n"
            "engine = create_engine(db_url)\n"
            f"sql = '''{probe_sql}'''\n"
            "with engine.begin() as conn:\n"
            "    row = conn.execute(text(sql)).mappings().first()\n"
            "print(json.dumps({k: (v.isoformat() if hasattr(v, 'isoformat') and v is not None else v) for k, v in dict(row).items()}, ensure_ascii=False))\n"
        ),
    ]

    result = subprocess.run(
        cmd,
        cwd=str(backend_dir),
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        _print_kv(step="pipeline_probe", status="error", returncode=result.returncode)
        if result.stderr:
            print(result.stderr.rstrip(), file=sys.stderr)
        return

    payload = result.stdout.strip()
    _print_kv(step="pipeline_probe", status="ok", metrics=payload)


def _run_step(step: Step, *, backend_dir: Path, dry_run: bool) -> int:
    if not step.incremental_safe:
        _print_kv(error_step=step.name, error="incremental_safety_check_failed")
        return 2

    if dry_run and not step.supports_dry_run:
        _print_kv(step=step.name, status="skipped", reason="no_dry_run_support")
        return 0

    _print_kv(step=step.name, status="start", ts=_utc_now_iso())
    t0 = time.perf_counter()

    result = subprocess.run(
        step.cmd,
        cwd=str(backend_dir),
        text=True,
        capture_output=True,
    )

    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip(), file=sys.stderr)

    elapsed = time.perf_counter() - t0

    if result.returncode != 0:
        _print_kv(
            error_step=step.name,
            returncode=result.returncode,
            elapsed_s=f"{elapsed:.2f}",
        )
        return result.returncode or 1

    counts = step.parse_counts(result.stdout + "\n" + result.stderr)
    _print_kv(
        step=step.name,
        status="end",
        elapsed_s=f"{elapsed:.2f}",
        **counts,
    )
    return 0


def _build_steps(*, backend_dir: Path, do_write: bool) -> list[Step]:
    scripts_dir = backend_dir / "scripts"

    fetch_rss_path = backend_dir / "fetch_rss.py"
    seed_sources_path = backend_dir / "seed_sources.py"
    backfill_embeddings_path = scripts_dir / "backfill_embeddings_live.py"
    backfill_article_types_path = scripts_dir / "backfill_article_types.py"
    cluster_live_path = scripts_dir / "cluster_events_live.py"
    cluster_fallback_path = scripts_dir / "cluster_events.py"

    if not fetch_rss_path.exists():
        raise FileNotFoundError("fetch_rss.py not found")
    if not seed_sources_path.exists():
        raise FileNotFoundError("seed_sources.py not found")
    if not backfill_embeddings_path.exists():
        raise FileNotFoundError("backfill_embeddings_live.py not found")
    if not backfill_article_types_path.exists():
        raise FileNotFoundError("backfill_article_types.py not found")

    if cluster_live_path.exists():
        cluster_module = "scripts.cluster_events_live"
    elif cluster_fallback_path.exists():
        cluster_module = "scripts.cluster_events"
    else:
        raise FileNotFoundError("cluster_events_live.py not found (and no fallback)")

    embed_limit = _env_int("BACKFILL_EMBED_LIMIT", 2000, min_value=100, max_value=20000)
    cluster_rounds = _env_int("CLUSTER_MAX_ROUNDS", 6, min_value=1, max_value=30)

    steps: list[Step] = [
        Step(
            name="seed_sources",
            cmd=[sys.executable, "-m", "seed_sources"],
            supports_dry_run=False,
            incremental_safe=True,
            parse_counts=_parse_seed_sources,
        ),
        Step(
            name="fetch_rss",
            cmd=[sys.executable, "-m", "fetch_rss"],
            supports_dry_run=False,
            incremental_safe=True,
            parse_counts=_parse_fetch_rss,
        ),
        Step(
            name="backfill_embeddings_live",
            cmd=[
                sys.executable,
                "-m",
                "scripts.backfill_embeddings_live",
                "--since_days",
                "7",
                "--limit",
                str(embed_limit),
            ],
            supports_dry_run=False,
            incremental_safe=True,
            parse_counts=_parse_backfill_embeddings,
        ),
    ]

    for idx in range(cluster_rounds):
        steps.append(
            Step(
                name=f"cluster_events_live_round_{idx + 1}",
                cmd=[
                    sys.executable,
                    "-m",
                    cluster_module,
                ]
                + (["--write"] if do_write else []),
                supports_dry_run=True,
                incremental_safe=True,
                parse_counts=_parse_cluster_events,
            )
        )

    steps += [
        Step(
            name="backfill_article_types",
            cmd=[
                sys.executable,
                "-m",
                "scripts.backfill_article_types",
                "--days",
                "7",
                "--limit",
                "1000",
            ],
            supports_dry_run=False,
            incremental_safe=True,
            parse_counts=_parse_backfill_article_types,
        ),
    ]

    return steps


def main() -> int:
    parser = argparse.ArgumentParser(description="Cross-platform live update orchestrator")
    parser.add_argument("--write", action="store_true", help="execute write steps")
    parser.add_argument("--dry-run", action="store_true", help="avoid write steps")
    args = parser.parse_args()

    if args.write and args.dry_run:
        _print_kv(error_step="argument", error="use_only_one_of_write_or_dry_run")
        return 2

    do_write = args.write
    dry_run = args.dry_run or not args.write

    repo_root = Path(__file__).resolve().parents[2]
    backend_dir = repo_root / "backend"

    _print_kv(mode="WRITE" if do_write else "DRY_RUN", ts=_utc_now_iso())
    _print_kv(env_DATABASE_URL="present" if "DATABASE_URL" in os.environ else "missing")

    try:
        steps = _build_steps(backend_dir=backend_dir, do_write=do_write)
    except Exception as exc:
        _print_kv(error_step="init", error=str(exc))
        return 2

    for step in steps:
        code = _run_step(step, backend_dir=backend_dir, dry_run=dry_run)
        if code != 0:
            return code

    _print_pipeline_probe(backend_dir=backend_dir)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
