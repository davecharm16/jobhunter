"""Unit tests for the canonical-CV reader contract (AC #7, FR4).

The reader is the single code path other stories use to load the canonical CV.
Contract under test:
  - reads CANONICAL_CV_PATH on every invocation (no caching) — FR4
  - returns the parsed JSON as a dict
  - raises CanonicalCVMissing when the file does not exist
  - rejects PDF/docx/doc extensions before any read attempt — Story 1.3 (FR5)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jobhunter.canonical_cv import (
    CanonicalCVMissing,
    UnsupportedCanonicalCVFormat,
    read_canonical_cv,
)


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


def test_unsupported_canonical_cv_format_subclasses_value_error() -> None:
    """Binary-format rejection is a value error, not a missing-file error."""
    assert issubclass(UnsupportedCanonicalCVFormat, ValueError)


def test_pdf_path_is_rejected_before_any_read(pdf_canonical_cv: Path) -> None:
    with pytest.raises(UnsupportedCanonicalCVFormat) as excinfo:
        read_canonical_cv()

    message = str(excinfo.value)
    assert "PDF" in message
    assert str(pdf_canonical_cv) in message


def test_pdf_uppercase_path_is_rejected(pdf_canonical_cv_upper: Path) -> None:
    """`.PDF` (any case) is rejected by extension."""
    with pytest.raises(UnsupportedCanonicalCVFormat) as excinfo:
        read_canonical_cv()

    message = str(excinfo.value)
    assert "PDF" in message
    assert str(pdf_canonical_cv_upper) in message


def test_docx_path_is_rejected(docx_canonical_cv: Path) -> None:
    with pytest.raises(UnsupportedCanonicalCVFormat) as excinfo:
        read_canonical_cv()

    message = str(excinfo.value)
    assert "docx" in message
    assert "Word" in message
    assert str(docx_canonical_cv) in message


def test_docx_uppercase_path_is_rejected(docx_canonical_cv_upper: Path) -> None:
    with pytest.raises(UnsupportedCanonicalCVFormat) as excinfo:
        read_canonical_cv()

    message = str(excinfo.value)
    assert "docx" in message
    assert "Word" in message
    assert str(docx_canonical_cv_upper) in message


def test_doc_path_is_rejected(doc_canonical_cv: Path) -> None:
    with pytest.raises(UnsupportedCanonicalCVFormat) as excinfo:
        read_canonical_cv()

    message = str(excinfo.value)
    assert "docx" in message
    assert "Word" in message
    assert str(doc_canonical_cv) in message


def test_doc_uppercase_path_is_rejected(doc_canonical_cv_upper: Path) -> None:
    """`.DOC` (uppercase) is rejected by extension — closes the .DOC case-insensitivity gap."""
    with pytest.raises(UnsupportedCanonicalCVFormat) as excinfo:
        read_canonical_cv()

    message = str(excinfo.value)
    assert "docx" in message
    assert "Word" in message
    assert str(doc_canonical_cv_upper) in message


def test_mixed_case_pdf_path_is_rejected(
    pdf_canonical_cv_mixed_case: Path,
) -> None:
    """Mixed-case `.Pdf` is rejected — confirms `suffix.lower()` covers all casings."""
    with pytest.raises(UnsupportedCanonicalCVFormat) as excinfo:
        read_canonical_cv()

    message = str(excinfo.value)
    assert "PDF" in message
    assert str(pdf_canonical_cv_mixed_case) in message


def test_mixed_case_docx_path_is_rejected(
    docx_canonical_cv_mixed_case: Path,
) -> None:
    """Mixed-case `.Docx` is rejected — confirms `suffix.lower()` covers all casings."""
    with pytest.raises(UnsupportedCanonicalCVFormat) as excinfo:
        read_canonical_cv()

    message = str(excinfo.value)
    assert "docx" in message
    assert "Word" in message
    assert str(docx_canonical_cv_mixed_case) in message


def test_rejection_precedes_existence_check(
    nonexistent_pdf_canonical_cv: Path,
) -> None:
    """Extension-based rejection MUST fire before any filesystem check (AC2 safety).

    If a non-existent `.pdf` raised `CanonicalCVMissing` instead of
    `UnsupportedCanonicalCVFormat`, that would mean the reader called
    `open()` before checking the suffix — defeating the no-binary-read
    safety guarantee on FR5.
    """
    with pytest.raises(UnsupportedCanonicalCVFormat) as excinfo:
        read_canonical_cv()

    assert not nonexistent_pdf_canonical_cv.exists()
    message = str(excinfo.value)
    assert "PDF" in message
    assert str(nonexistent_pdf_canonical_cv) in message


def test_reader_does_not_validate_jsonresume_schema(
    tmp_canonical_cv: Path,
) -> None:
    """AC10: schema validation lives in scripts/validate_canonical_cv.py — NOT here.

    A JSON dict that does not conform to JSON Resume must still be returned as-is
    by the runtime reader; the reader is a thin loader, not a validator.
    """
    arbitrary = {"hello": "world", "not_jsonresume": True}
    tmp_canonical_cv.write_text(json.dumps(arbitrary), encoding="utf-8")

    result = read_canonical_cv()

    assert result == arbitrary


def test_canonical_cv_missing_chains_from_file_not_found(
    missing_canonical_cv: Path,
) -> None:
    """Exception chaining preserves the underlying FileNotFoundError for debuggers."""
    with pytest.raises(CanonicalCVMissing) as excinfo:
        read_canonical_cv()

    assert isinstance(excinfo.value.__cause__, FileNotFoundError)
