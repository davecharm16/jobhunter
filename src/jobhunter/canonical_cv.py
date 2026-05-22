"""Canonical-CV reader contract (FR4, FR5).

This module exposes the **only** function any other code path may use to load
the canonical CV: `read_canonical_cv`. It re-reads from disk on every call —
no in-process or on-disk caching — so that the rest of the pipeline always
sees the latest committed version.

Story 1.3 also lands the binary-format rejection guarantee from FR5: paths
ending in `.pdf`, `.docx`, or `.doc` (any case) are rejected by extension
*before* any `open()` or `json.load()` happens, so the reader can never be
tricked into streaming a binary file off disk.
"""

import json
from typing import Any

from jobhunter.config import CANONICAL_CV_PATH


__all__ = [
    "CanonicalCVMissing",
    "UnsupportedCanonicalCVFormat",
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


_WORD_SUFFIXES = {".docx", ".doc"}


def read_canonical_cv() -> dict[str, Any]:
    """Read CANONICAL_CV_PATH on every call and return the parsed JSON dict.

    Raises:
        UnsupportedCanonicalCVFormat: if the path's extension is `.pdf`,
            `.docx`, or `.doc` (case-insensitive). No file read is attempted.
        CanonicalCVMissing: if the file does not exist.
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
            return json.load(fh)
    except FileNotFoundError as exc:
        raise CanonicalCVMissing(
            f"Canonical CV not found at {CANONICAL_CV_PATH}"
        ) from exc
