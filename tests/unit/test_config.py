"""Unit tests for `jobhunter.config` (AC #4).

Story 1.1 requires `CANONICAL_CV_PATH` exists as a single source of truth
constant. These tests pin its name, type, and that the resolved project root
actually points at the repo root.
"""

from __future__ import annotations

from pathlib import Path

import jobhunter.config as config_module
from jobhunter.config import (
    CANONICAL_CV_PATH,
    PROJECT_ROOT,
    VENDORED_JSONRESUME_SCHEMA_PATH,
)


def test_canonical_cv_path_is_pathlib_path() -> None:
    assert isinstance(CANONICAL_CV_PATH, Path)


def test_canonical_cv_path_points_at_repo_root_json() -> None:
    assert CANONICAL_CV_PATH.name == "canonical-cv.json"
    assert CANONICAL_CV_PATH.parent == PROJECT_ROOT


def test_vendored_schema_path_is_under_schemas_dir() -> None:
    assert VENDORED_JSONRESUME_SCHEMA_PATH.parent == PROJECT_ROOT / "schemas"
    assert VENDORED_JSONRESUME_SCHEMA_PATH.name == "jsonresume-v1.0.0.json"


def test_project_root_contains_pyproject() -> None:
    """If PROJECT_ROOT is wrong, the entire reader contract breaks."""
    assert (PROJECT_ROOT / "pyproject.toml").is_file()


def test_committed_canonical_cv_exists_at_configured_path() -> None:
    """The committed sample (Task 3 of story 1.1) must live at the configured path."""
    assert CANONICAL_CV_PATH.is_file(), (
        f"canonical CV sample missing at {CANONICAL_CV_PATH}"
    )


def test_committed_vendored_schema_exists() -> None:
    assert VENDORED_JSONRESUME_SCHEMA_PATH.is_file(), (
        f"vendored schema missing at {VENDORED_JSONRESUME_SCHEMA_PATH}"
    )


def test_module_exports_expected_constants() -> None:
    assert hasattr(config_module, "CANONICAL_CV_PATH")
    assert hasattr(config_module, "VENDORED_JSONRESUME_SCHEMA_PATH")
    assert hasattr(config_module, "PROJECT_ROOT")
