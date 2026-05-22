"""Canonical-CV reader contract (FR4).

This module exposes the **only** function any other code path may use to load
the canonical CV: `read_canonical_cv`. It re-reads from disk on every call —
no in-process or on-disk caching — so that the rest of the pipeline always
sees the latest committed version.

PDF/docx rejection logic is intentionally NOT implemented here; that lands in
Story 1.3.
"""

import json
from typing import Any

from jobhunter.config import CANONICAL_CV_PATH


class CanonicalCVMissing(FileNotFoundError):
    """Raised when the canonical CV is not present at CANONICAL_CV_PATH.

    Story 1.3 will map this to a clean CLI exit code; for Story 1.1 we just
    raise so callers get a typed failure.
    """


def read_canonical_cv() -> dict[str, Any]:
    """Read CANONICAL_CV_PATH on every call and return the parsed JSON dict.

    Raises:
        CanonicalCVMissing: if the file does not exist.
    """
    try:
        with open(CANONICAL_CV_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError as exc:
        raise CanonicalCVMissing(
            f"Canonical CV not found at {CANONICAL_CV_PATH}"
        ) from exc
