"""Shared test fixtures for the jobhunter test suite.

Story 1.1 (walking skeleton). Fixtures focus on:
- Isolating CANONICAL_CV_PATH per-test by writing to a tmp path and patching
  the constant in `jobhunter.config` + `jobhunter.canonical_cv` (the module
  imports the constant at import time, so both sites need patching).
- Providing a minimal-but-valid JSON Resume sample so tests don't depend on
  the committed `canonical-cv.json` evolving.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

MINIMAL_VALID_RESUME: dict = {
    "basics": {
        "name": "Test Author",
        "label": "Engineer",
        "email": "test@example.com",
    },
    "work": [
        {
            "name": "Acme",
            "position": "Engineer",
            "startDate": "2020-01-01",
            "highlights": ["Shipped a thing"],
        }
    ],
    "skills": [
        {"name": "Python", "keywords": ["pytest", "stdlib"]},
    ],
    "education": [
        {"institution": "University", "area": "CS", "studyType": "BSc"},
    ],
    "projects": [
        {"name": "jobhunter", "highlights": ["Walking skeleton"]},
    ],
}


@pytest.fixture
def tmp_canonical_cv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Write a minimal valid CV to tmp and point CANONICAL_CV_PATH at it.

    Patches the constant in both `jobhunter.config` and `jobhunter.canonical_cv`
    because `canonical_cv` does `from jobhunter.config import CANONICAL_CV_PATH`
    at import time, binding its own module-level reference.
    """
    cv_path = tmp_path / "canonical-cv.json"
    cv_path.write_text(json.dumps(MINIMAL_VALID_RESUME), encoding="utf-8")

    import jobhunter.canonical_cv as reader_module
    import jobhunter.config as config_module

    monkeypatch.setattr(config_module, "CANONICAL_CV_PATH", cv_path)
    monkeypatch.setattr(reader_module, "CANONICAL_CV_PATH", cv_path)
    return cv_path


@pytest.fixture
def missing_canonical_cv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point CANONICAL_CV_PATH at a path that does NOT exist."""
    missing = tmp_path / "does-not-exist.json"

    import jobhunter.canonical_cv as reader_module
    import jobhunter.config as config_module

    monkeypatch.setattr(config_module, "CANONICAL_CV_PATH", missing)
    monkeypatch.setattr(reader_module, "CANONICAL_CV_PATH", missing)
    return missing


def _point_canonical_cv_at(
    target: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Create an empty file at *target* and patch CANONICAL_CV_PATH to it.

    The file is intentionally empty (zero bytes): if the reader incorrectly
    falls through to `json.load`, an empty file raises `json.JSONDecodeError`,
    not `UnsupportedCanonicalCVFormat`, so tests fail loudly when the
    extension-based rejection regresses.
    """
    target.write_bytes(b"")

    import jobhunter.canonical_cv as reader_module
    import jobhunter.config as config_module

    monkeypatch.setattr(config_module, "CANONICAL_CV_PATH", target)
    monkeypatch.setattr(reader_module, "CANONICAL_CV_PATH", target)
    return target


@pytest.fixture
def pdf_canonical_cv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point CANONICAL_CV_PATH at a zero-byte `.pdf` file."""
    return _point_canonical_cv_at(tmp_path / "canonical-cv.pdf", monkeypatch)


@pytest.fixture
def pdf_canonical_cv_upper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Point CANONICAL_CV_PATH at a zero-byte `.PDF` file (uppercase)."""
    return _point_canonical_cv_at(tmp_path / "canonical-cv.PDF", monkeypatch)


@pytest.fixture
def docx_canonical_cv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point CANONICAL_CV_PATH at a zero-byte `.docx` file."""
    return _point_canonical_cv_at(tmp_path / "canonical-cv.docx", monkeypatch)


@pytest.fixture
def docx_canonical_cv_upper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Point CANONICAL_CV_PATH at a zero-byte `.DOCX` file (uppercase)."""
    return _point_canonical_cv_at(tmp_path / "canonical-cv.DOCX", monkeypatch)


@pytest.fixture
def doc_canonical_cv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point CANONICAL_CV_PATH at a zero-byte `.doc` file."""
    return _point_canonical_cv_at(tmp_path / "canonical-cv.doc", monkeypatch)


@pytest.fixture
def doc_canonical_cv_upper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Point CANONICAL_CV_PATH at a zero-byte `.DOC` file (uppercase)."""
    return _point_canonical_cv_at(tmp_path / "canonical-cv.DOC", monkeypatch)


@pytest.fixture
def pdf_canonical_cv_mixed_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Point CANONICAL_CV_PATH at a zero-byte `.Pdf` file (mixed case)."""
    return _point_canonical_cv_at(tmp_path / "canonical-cv.Pdf", monkeypatch)


@pytest.fixture
def docx_canonical_cv_mixed_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Point CANONICAL_CV_PATH at a zero-byte `.Docx` file (mixed case)."""
    return _point_canonical_cv_at(tmp_path / "canonical-cv.Docx", monkeypatch)


@pytest.fixture
def nonexistent_pdf_canonical_cv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Point CANONICAL_CV_PATH at a `.pdf` path that does NOT exist on disk.

    Verifies AC2 ordering: extension-based rejection happens BEFORE any
    filesystem existence check, so this should raise
    `UnsupportedCanonicalCVFormat`, NOT `CanonicalCVMissing`.
    """
    target = tmp_path / "does-not-exist.pdf"

    import jobhunter.canonical_cv as reader_module
    import jobhunter.config as config_module

    monkeypatch.setattr(config_module, "CANONICAL_CV_PATH", target)
    monkeypatch.setattr(reader_module, "CANONICAL_CV_PATH", target)
    return target


@pytest.fixture
def project_root() -> Path:
    """Absolute path to the repo root (parent of tests/)."""
    return Path(__file__).resolve().parents[1]
