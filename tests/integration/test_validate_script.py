"""Integration tests for `scripts/validate_canonical_cv.py` (AC #5).

These tests invoke the script via subprocess to exercise it end-to-end (CLI
contract — the way Story 1.1's README smoke test runs it). Each test runs
against a fully isolated working tree (copied canonical-cv.json + vendored
schema), so the committed sample is never mutated and tests are independent.

Exit-code contract under test:
  - 0  → sample validates clean
  - 1  → sample is structurally invalid
  - 2  → schema or CV file is missing
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_REL_PATH = Path("scripts") / "validate_canonical_cv.py"
SCHEMA_REL_PATH = Path("schemas") / "jsonresume-v1.0.0.json"
CV_REL_PATH = Path("canonical-cv.json")


def _run_validator(workdir: Path) -> subprocess.CompletedProcess:
    """Invoke the validator with workdir as the project root.

    We set PYTHONPATH so `jobhunter.config` (which computes PROJECT_ROOT from
    the script's own file location) and our isolated workdir are both wired:
    the script resolves paths from its own location, so we must run the copied
    script — not the in-repo one.
    """
    return subprocess.run(
        [sys.executable, str(workdir / SCRIPT_REL_PATH)],
        capture_output=True,
        text=True,
        cwd=str(workdir),
    )


@pytest.fixture
def isolated_workspace(tmp_path: Path, project_root: Path) -> Path:
    """Copy the script, schema, src package, and CV into a tmp workspace.

    Because `jobhunter.config.PROJECT_ROOT` derives from the package file
    location (`Path(__file__).resolve().parents[2]`), copying `src/jobhunter`
    into `tmp_path/src/jobhunter` makes that package see `tmp_path` as its
    project root — letting us swap canonical-cv.json and schemas/ per test
    without touching the committed files.
    """
    (tmp_path / "scripts").mkdir()
    shutil.copy2(project_root / SCRIPT_REL_PATH, tmp_path / SCRIPT_REL_PATH)

    (tmp_path / "schemas").mkdir()
    shutil.copy2(project_root / SCHEMA_REL_PATH, tmp_path / SCHEMA_REL_PATH)

    shutil.copy2(project_root / CV_REL_PATH, tmp_path / CV_REL_PATH)

    shutil.copytree(
        project_root / "src" / "jobhunter",
        tmp_path / "src" / "jobhunter",
    )

    return tmp_path


def _run_isolated(workspace: Path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(workspace / "src")
    return subprocess.run(
        [sys.executable, str(workspace / SCRIPT_REL_PATH)],
        capture_output=True,
        text=True,
        cwd=str(workspace),
        env=env,
    )


def test_validator_exits_zero_on_valid_sample(isolated_workspace: Path) -> None:
    result = _run_isolated(isolated_workspace)
    assert result.returncode == 0, (
        f"expected exit 0, got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "ok" in result.stdout.lower()


def test_validator_exits_two_when_cv_missing(isolated_workspace: Path) -> None:
    (isolated_workspace / CV_REL_PATH).unlink()
    result = _run_isolated(isolated_workspace)
    assert result.returncode == 2
    assert "not found" in result.stderr.lower()


def test_validator_exits_two_when_schema_missing(isolated_workspace: Path) -> None:
    (isolated_workspace / SCHEMA_REL_PATH).unlink()
    result = _run_isolated(isolated_workspace)
    assert result.returncode == 2
    assert "schema" in result.stderr.lower()


def test_validator_exits_one_on_invalid_email(isolated_workspace: Path) -> None:
    """AC #5: validator must catch format violations (FormatChecker wired)."""
    import json

    cv_path = isolated_workspace / CV_REL_PATH
    data = json.loads(cv_path.read_text(encoding="utf-8"))
    data["basics"]["email"] = "not-an-email"
    cv_path.write_text(json.dumps(data), encoding="utf-8")

    result = _run_isolated(isolated_workspace)
    assert result.returncode == 1
    assert "email" in result.stderr.lower()


def test_validator_exits_one_on_structural_violation(isolated_workspace: Path) -> None:
    """basics.name must be a string per JSON Resume v1.0.0."""
    import json

    cv_path = isolated_workspace / CV_REL_PATH
    data = json.loads(cv_path.read_text(encoding="utf-8"))
    data["basics"]["name"] = 42
    cv_path.write_text(json.dumps(data), encoding="utf-8")

    result = _run_isolated(isolated_workspace)
    assert result.returncode == 1
    # Path locator in the error must point at basics/name specifically — the
    # generic word "name" appears in many JSON Resume sections, so don't fall
    # back to it.
    assert "basics/name" in result.stderr
