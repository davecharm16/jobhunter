"""Upwork-specific signal extraction (Story 2.5).

Pure-heuristic extractor — no LLM call. Runs only when the source-board
classifier (Story 2.4) tags a JD as `upwork`. Surfaces three structured
signals (budget band, pricing type, screening questions) and two red flags
(`budget_below_floor`, `vague_scope`) that the downstream Upwork-proposal
template (Story 2.7) and the staged-package summary (FR16) consume.

Missing fields return `None` / `"unknown"` / `[]` — never fabricated.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


__all__ = [
    "PRICING_HOURLY",
    "PRICING_FIXED",
    "PRICING_UNKNOWN",
    "RED_FLAG_BUDGET_BELOW_FLOOR",
    "RED_FLAG_VAGUE_SCOPE",
    "UpworkSignals",
    "detect_budget_below_floor",
    "detect_vague_scope",
    "extract",
]


PRICING_HOURLY = "hourly"
PRICING_FIXED = "fixed"
PRICING_UNKNOWN = "unknown"

RED_FLAG_BUDGET_BELOW_FLOOR = "budget_below_floor"
RED_FLAG_VAGUE_SCOPE = "vague_scope"


# v1: intentionally narrow phrase list. Move to config.yaml in a follow-up
# story if the heuristic needs tuning across more JD copy variants.
_VAGUE_SCOPE_PHRASES: tuple[str, ...] = (
    "please make it amazing",
    "looking for someone awesome",
    "need a rockstar",
    "be your own boss",
    "exciting opportunity",
)

_VAGUE_SCOPE_PATTERN: re.Pattern[str] = re.compile(
    "|".join(re.escape(phrase) for phrase in _VAGUE_SCOPE_PHRASES),
    re.IGNORECASE,
)

# Hourly band: "$25-50/hr", "$25 - $50 / hour", "$25 to $50 per hour".
_HOURLY_BAND_PATTERN = re.compile(
    r"\$\s*(\d+(?:\.\d+)?)\s*(?:-|to|–)\s*\$?\s*(\d+(?:\.\d+)?)"
    r"\s*(?:/|per\s+)?\s*(?:hr|hour)\b",
    re.IGNORECASE,
)

# Single hourly rate: "$25/hr", "$25 per hour".
_HOURLY_SINGLE_PATTERN = re.compile(
    r"\$\s*(\d+(?:\.\d+)?)\s*(?:/|per\s+)\s*(?:hr|hour)\b",
    re.IGNORECASE,
)

# Fixed budget: "Budget: $500", "Project budget: $1500", "fixed price $500",
# "$500 fixed".
_FIXED_BUDGET_PATTERN = re.compile(
    r"(?:(?:project\s+)?budget\s*:?\s*\$\s*(\d+(?:\.\d+)?))"
    r"|(?:fixed(?:\s*-?\s*price)?\s*:?\s*\$\s*(\d+(?:\.\d+)?))"
    r"|(?:\$\s*(\d+(?:\.\d+)?)\s*(?:fixed|flat))",
    re.IGNORECASE,
)

# Pricing-type hints when no number is present.
_HOURLY_HINT_PATTERN = re.compile(r"\bhourly\b", re.IGNORECASE)
_FIXED_HINT_PATTERN = re.compile(r"\bfixed[\s-]?price\b", re.IGNORECASE)

# Screening Questions header followed by bullet/numbered list lines.
_SCREENING_HEADER_PATTERN = re.compile(
    r"screening\s+questions?\s*:?\s*\n",
    re.IGNORECASE,
)
_BULLET_PATTERN = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(.+?)\s*$")


@dataclass(frozen=True)
class UpworkSignals:
    """Structured Upwork signals extracted from a JD's raw text."""

    budget_band: str | None = None
    pricing_type: str = PRICING_UNKNOWN
    screening_questions: list[str] = field(default_factory=list)


def extract(jd_text: str) -> UpworkSignals:
    """Extract Upwork signals from *jd_text* via plain-string heuristics."""
    pricing_type, _budget_value, budget_band = _extract_budget(jd_text)
    screening_questions = _extract_screening_questions(jd_text)
    return UpworkSignals(
        budget_band=budget_band,
        pricing_type=pricing_type,
        screening_questions=screening_questions,
    )


def detect_budget_below_floor(
    jd_text: str,
    *,
    hourly_floor: int,
    fixed_floor: int,
) -> bool:
    """Return True when *jd_text*'s parsed budget is below the matching floor."""
    pricing_type, budget_value, _band = _extract_budget(jd_text)
    if budget_value is None:
        return False
    if pricing_type == PRICING_HOURLY:
        return budget_value < hourly_floor
    if pricing_type == PRICING_FIXED:
        return budget_value < fixed_floor
    return False


def detect_vague_scope(jd_text: str) -> bool:
    """Return True when *jd_text* matches any vague-scope signal phrase."""
    return bool(_VAGUE_SCOPE_PATTERN.search(jd_text))


def _extract_budget(jd_text: str) -> tuple[str, float | None, str | None]:
    band_match = _HOURLY_BAND_PATTERN.search(jd_text)
    if band_match:
        low = float(band_match.group(1))
        high = float(band_match.group(2))
        return PRICING_HOURLY, low, f"${_fmt(low)}-{_fmt(high)}/hr"

    single_match = _HOURLY_SINGLE_PATTERN.search(jd_text)
    if single_match:
        rate = float(single_match.group(1))
        return PRICING_HOURLY, rate, f"${_fmt(rate)}/hr"

    fixed_match = _FIXED_BUDGET_PATTERN.search(jd_text)
    if fixed_match:
        amount_str = next(
            (g for g in fixed_match.groups() if g is not None), None
        )
        if amount_str is not None:
            amount = float(amount_str)
            return PRICING_FIXED, amount, f"${_fmt(amount)} fixed"

    if _FIXED_HINT_PATTERN.search(jd_text):
        return PRICING_FIXED, None, None
    if _HOURLY_HINT_PATTERN.search(jd_text):
        return PRICING_HOURLY, None, None

    return PRICING_UNKNOWN, None, None


def _extract_screening_questions(jd_text: str) -> list[str]:
    header_match = _SCREENING_HEADER_PATTERN.search(jd_text)
    if header_match is None:
        return []
    tail = jd_text[header_match.end():]
    questions: list[str] = []
    for line in tail.splitlines():
        stripped = line.strip()
        if not stripped:
            if questions:
                break
            continue
        bullet = _BULLET_PATTERN.match(line)
        if bullet:
            questions.append(bullet.group(1).strip())
            continue
        if questions:
            break
    return questions


def _fmt(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return f"{value:g}"
