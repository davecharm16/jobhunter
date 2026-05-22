"""Unit tests for the canonical-CV reader contract (AC #7, FR4).

The reader is the single code path other stories use to load the canonical CV.
Contract under test:
  - reads CANONICAL_CV_PATH on every invocation (no caching) — FR4
  - returns the parsed JSON as a dict
  - raises CanonicalCVMissing when the file does not exist
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jobhunter.canonical_cv import CanonicalCVMissing, read_canonical_cv


def test_reads_and_returns_parsed_dict(tmp_canonical_cv: Path) -> None:
    result = read_canonical_cv()

    assert isinstance(result, dict)
    assert result["basics"]["name"] == "Test Author"
    assert result["work"][0]["name"] == "Acme"


def test_no_caching_fresh_read_each_call(tmp_canonical_cv: Path) -> None:
    """FR4: every call must re-read from disk; mutations between calls must be visible."""
    first = read_canonical_cv()
    assert first["basics"]["name"] == "Test Author"

    mutated = json.loads(tmp_canonical_cv.read_text(encoding="utf-8"))
    mutated["basics"]["name"] = "Mutated Author"
    tmp_canonical_cv.write_text(json.dumps(mutated), encoding="utf-8")

    second = read_canonical_cv()
    assert second["basics"]["name"] == "Mutated Author"


def test_missing_file_raises_canonical_cv_missing(missing_canonical_cv: Path) -> None:
    with pytest.raises(CanonicalCVMissing) as excinfo:
        read_canonical_cv()

    assert str(missing_canonical_cv) in str(excinfo.value)


def test_canonical_cv_missing_subclasses_file_not_found() -> None:
    """Allows callers to catch the broader FileNotFoundError when convenient."""
    assert issubclass(CanonicalCVMissing, FileNotFoundError)


def test_invalid_json_propagates_as_decode_error(
    tmp_canonical_cv: Path,
) -> None:
    """Story 1.1 reader is a stub — invalid JSON should surface, not be swallowed."""
    tmp_canonical_cv.write_text("{ not json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        read_canonical_cv()
