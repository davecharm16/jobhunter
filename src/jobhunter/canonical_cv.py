"""Canonical-CV reader contract (FR4, FR5) + tagging/high-impact projection (FR2, FR3).

This module exposes the **only** function any other code path may use to load
the canonical CV: `read_canonical_cv`. It re-reads from disk on every call —
no in-process or on-disk caching — so that the rest of the pipeline always
sees the latest committed version.

Story 1.3 lands the binary-format rejection guarantee from FR5: paths ending
in `.pdf`, `.docx`, or `.doc` (any case) are rejected by extension *before*
any `open()` or `json.load()` happens.

Story 2.1 adds the JSON Resume v1.0.0 + jobhunter-extensions validation step
that runs after `json.load()` but before the dict is returned. Malformed
documents surface as `CanonicalCVMalformed` with a JSON Pointer path to the
offending node. The `high_impact_entries()` projection (FR3) returns the
flagged `work`/`projects`/`skills` entries for the Epic 4 content-loss check.
"""

import json
from typing import Any

from jsonschema import FormatChecker
from jsonschema.validators import validator_for

from jobhunter.config import CANONICAL_CV_PATH, VENDORED_JSONRESUME_SCHEMA_PATH


__all__ = [
    "CanonicalCVMalformed",
    "CanonicalCVMissing",
    "UnsupportedCanonicalCVFormat",
    "high_impact_entries",
    "read_canonical_cv",
]


class CanonicalCVMissing(FileNotFoundError):
    """Raised when the canonical CV is not present at CANONICAL_CV_PATH.

    Subclasses `FileNotFoundError` so callers may catch the broader category
    if they want; the CLI catches the concrete class to keep exit-code mapping
    explicit.
    """


class UnsupportedCanonicalCVFormat(ValueError):
    """Raised when CANONICAL_CV_PATH points at a binary (PDF/docx/doc) file.

    Rejection is by file extension — the reader never opens the file. The
    canonical CV must be a text format (JSON today; markdown or YAML if the
    DECISIONS.md §2 fall-back criterion fires in Story 2.1).
    """


class CanonicalCVMalformed(ValueError):
    """Raised when the canonical CV violates JSON Resume v1.0.0 + extensions."""


_WORD_SUFFIXES = {".docx", ".doc"}
_HIGH_IMPACT_SECTIONS = ("work", "projects", "skills")


def _json_pointer(path_parts: Any) -> str:
    """Render a jsonschema absolute_path deque as a JSON Pointer string."""
    parts = list(path_parts)
    if not parts:
        return "/"
    return "/" + "/".join(str(p) for p in parts)


def _validate_or_raise(document: dict[str, Any]) -> None:
    with open(VENDORED_JSONRESUME_SCHEMA_PATH, "r", encoding="utf-8") as fh:
        schema = json.load(fh)

    ValidatorCls = validator_for(schema)
    ValidatorCls.check_schema(schema)
    validator = ValidatorCls(schema, format_checker=FormatChecker())
    error = next(iter(validator.iter_errors(document)), None)
    if error is None:
        return

    pointer = _json_pointer(error.absolute_path)
    raise CanonicalCVMalformed(
        f"Canonical CV at {CANONICAL_CV_PATH} failed JSON Resume validation "
        f"at {pointer}: {error.message}"
    )


def read_canonical_cv() -> dict[str, Any]:
    """Read CANONICAL_CV_PATH on every call and return the parsed JSON dict.

    Raises:
        UnsupportedCanonicalCVFormat: if the path's extension is `.pdf`,
            `.docx`, or `.doc` (case-insensitive). No file read is attempted.
        CanonicalCVMissing: if the file does not exist.
        CanonicalCVMalformed: if the document fails JSON Resume v1.0.0
            validation (with the Story 2.1 tags + highImpact extensions
            layered in).
    """
    suffix = CANONICAL_CV_PATH.suffix.lower()

    if suffix == ".pdf":
        raise UnsupportedCanonicalCVFormat(
            f"PDF canonical CV at {CANONICAL_CV_PATH} is not supported; "
            "the canonical CV must be a text format (JSON, markdown, or YAML), not PDF."
        )

    if suffix in _WORD_SUFFIXES:
        raise UnsupportedCanonicalCVFormat(
            f"Word/docx canonical CV at {CANONICAL_CV_PATH} is not supported; "
            "the canonical CV must be a text format (JSON, markdown, or YAML), not Word/docx."
        )

    try:
        with open(CANONICAL_CV_PATH, "r", encoding="utf-8") as fh:
            document = json.load(fh)
    except FileNotFoundError as exc:
        raise CanonicalCVMissing(
            f"Canonical CV not found at {CANONICAL_CV_PATH}"
        ) from exc

    _validate_or_raise(document)
    return document


def high_impact_entries(canonical_cv: dict[str, Any]) -> list[dict[str, Any]]:
    """Return entries flagged `highImpact: true` across work/projects/skills (FR3)."""
    flagged: list[dict[str, Any]] = []
    for section in _HIGH_IMPACT_SECTIONS:
        for entry in canonical_cv.get(section, []):
            if entry.get("highImpact") is True:
                flagged.append({"_section": section, **entry})
    return flagged
