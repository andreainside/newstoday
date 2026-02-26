#!/usr/bin/env python3
"""
Smoke runner for Phase 52 reconstructed scripts.
"""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ScriptSpec:
    module: str
    name: str
    args: list[str]
    required_keywords: list[str]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _run_script(spec: ScriptSpec) -> tuple[int, str]:
    repo_root = _repo_root()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "backend")

    cmd = [sys.executable, "-m", spec.module] + spec.args
    proc = subprocess.run(
        cmd,
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
    )
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    return proc.returncode, combined


def _require_keywords(output: str, keywords: list[str]) -> list[str]:
    missing = []
    for kw in keywords:
        if kw not in output:
            missing.append(kw)
    return missing


def main() -> int:
    specs = [
        ScriptSpec(
            module="scripts.build_event_signatures_v0",
            name="build_event_signatures_v0",
            args=["--dry-run", "--mock-llm"],
            required_keywords=[
                "PHASE52_LOG",
                "script=build_event_signatures_v0",
                "mode=DRY_RUN",
            ],
        ),
        ScriptSpec(
            module="scripts.gen_event_merge_candidates",
            name="gen_event_merge_candidates",
            args=["--dry-run", "--mock-llm"],
            required_keywords=[
                "PHASE52_LOG",
                "script=gen_event_merge_candidates",
                "mode=DRY_RUN",
            ],
        ),
        ScriptSpec(
            module="scripts.judge_event_merge_suggestions_v1",
            name="judge_event_merge_suggestions_v1",
            args=["--dry-run", "--mock-llm"],
            required_keywords=[
                "PHASE52_LOG",
                "script=judge_event_merge_suggestions_v1",
                "mode=DRY_RUN",
            ],
        ),
    ]

    failures: list[str] = []
    for spec in specs:
        code, output = _run_script(spec)
        missing = _require_keywords(output, spec.required_keywords)
        if code != 0:
            failures.append(f"{spec.name}: nonzero_exit={code}")
        if missing:
            failures.append(f"{spec.name}: missing_keywords={','.join(missing)}")

    if failures:
        sys.stderr.write("SMOKE_PHASE52_FAIL\n")
        for item in failures:
            sys.stderr.write(item + "\n")
        return 2

    sys.stdout.write("SMOKE_PHASE52_OK\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
