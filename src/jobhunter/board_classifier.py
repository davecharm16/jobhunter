"""Source-board classifier (Story 2.4).

Tags every parsed JD with one of `upwork`, `onlinejobs_ph`, `linkedin`, or
`other` so downstream board-specific signal extractors (Stories 2.5, 2.6)
and the artifact-set selector (Story 2.8) know what kind of posting they
are looking at.

v1 is heuristic-only — no LLM call. Heuristics inspect the raw JD text for
URL hints and characteristic phrases. Anything that does not match a known
board resolves to `"other"` (AC3: the pipeline still runs end-to-end).
An explicit override (from the request body) bypasses heuristics entirely
and is recorded with `method="explicit_override"`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from jobhunter.jd_parser import ParsedJD


__all__ = [
    "ALLOWED_SOURCE_BOARDS",
    "Classification",
    "InvalidSourceBoard",
    "classify_board",
]


ALLOWED_SOURCE_BOARDS: frozenset[str] = frozenset(
    {"upwork", "onlinejobs_ph", "linkedin", "other"}
)


class InvalidSourceBoard(ValueError):
    """An explicit override or heuristic produced a value outside the allowed set."""


@dataclass(frozen=True)
class Classification:
    source_board: str
    method: str


# Compiled once at import time. Case-insensitive so JD copy/paste variants
# (mixed-case headers, marketing copy) match the same patterns.
_UPWORK_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"upwork\.com", re.IGNORECASE),
    re.compile(r"\bproject catalog\b", re.IGNORECASE),
    re.compile(r"\btalent marketplace\b", re.IGNORECASE),
    re.compile(r"\bconnects required\b", re.IGNORECASE),
)

_ONLINEJOBS_PH_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"onlinejobs\.ph", re.IGNORECASE),
    # "PHP/USD rate" is an OJ.ph-specific phrasing — Upwork postings say "$/hr".
    re.compile(r"\bphp\s*/\s*usd\s+rate\b", re.IGNORECASE),
)

_LINKEDIN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"linkedin\.com/jobs", re.IGNORECASE),
    re.compile(r"\blinkedin\s+easy\s+apply\b", re.IGNORECASE),
    re.compile(r"\bvia\s+linkedin\b", re.IGNORECASE),
)


def classify_board(
    jd_text: str,
    parsed_jd: ParsedJD,
    *,
    explicit_override: str | None = None,
) -> Classification:
    """Classify *jd_text* into one of the allowed `source_board` values."""
    if explicit_override is not None:
        if explicit_override not in ALLOWED_SOURCE_BOARDS:
            raise InvalidSourceBoard(
                f"source_board={explicit_override!r} is not in {sorted(ALLOWED_SOURCE_BOARDS)}"
            )
        return Classification(source_board=explicit_override, method="explicit_override")

    if _any_match(jd_text, _UPWORK_PATTERNS):
        return Classification(source_board="upwork", method="heuristic")
    if _any_match(jd_text, _ONLINEJOBS_PH_PATTERNS):
        return Classification(source_board="onlinejobs_ph", method="heuristic")
    if _any_match(jd_text, _LINKEDIN_PATTERNS):
        return Classification(source_board="linkedin", method="heuristic")
    return Classification(source_board="other", method="heuristic")


def _any_match(text: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    return any(pattern.search(text) for pattern in patterns)
