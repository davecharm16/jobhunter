"""Shared subprocess helpers for `jobhunter` CLI integration tests.

Lives outside the `test_*` discovery prefix so pytest does not collect it as a
test module. Both `test_cli_entry.py` and `test_paste_jd_ingest.py` import the
same primitives from here, so an env-shape change (e.g. adding a new required
env var) lands in one place instead of two.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from jobhunter.config import PROJECT_ROOT


def _pythonpath_with_src(
    env: dict[str, str],
    src_path: Path | None = None,
) -> dict[str, str]:
    src_path_text = str(PROJECT_ROOT / "src" if src_path is None else src_path)
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        src_path_text
        if not existing_pythonpath
        else os.pathsep.join([src_path_text, existing_pythonpath])
    )
    return env


def _cli_env(src_path: Path | None = None, **overrides: str) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"LLM_API_KEY", "MONTHLY_SPEND_CAP_USD"}
    }
    env.update(overrides)
    return _pythonpath_with_src(env, src_path)


def _isolated_cli_env(tmp_path: Path, **overrides: str) -> dict[str, str]:
    src_path = tmp_path / "src"
    shutil.copytree(
        PROJECT_ROOT / "src" / "jobhunter",
        src_path / "jobhunter",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    # Mirror the committed canonical CV into the isolated tree so the Story 1.3
    # reader contract resolves cleanly when env-valid tests reach `read_canonical_cv()`.
    canonical_src = PROJECT_ROOT / "canonical-cv.json"
    if canonical_src.is_file():
        shutil.copyfile(canonical_src, tmp_path / "canonical-cv.json")
    return _cli_env(src_path, **overrides)


def _run_module_cli(
    *args: str,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "jobhunter.cli", *args],
        capture_output=True,
        text=True,
        env=_cli_env() if env is None else env,
        cwd=PROJECT_ROOT if cwd is None else cwd,
        input=input_text,
        timeout=5,
    )
