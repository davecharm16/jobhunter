"""OJ.ph-specific signal extractor (Story 2.6).

Pulls a stated rate range and a role-type tag out of raw JD text using
heuristic regexes — no LLM call. The orchestrator runs this only when the
source-board classifier (Story 2.4) tags the JD as `onlinejobs_ph`, so the
patterns can be specific to OJ.ph posting conventions (USD-monthly rate
phrasing, PHP rate phrasing, full-time/part-time/gig keywords).

Missing fields surface as `None` — never fabricated (AC1). Currency
conversion for the rate-below-floor check happens in the orchestrator, not
here; this module only reports what the JD literally states.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


__all__ = [
    "OnlineJobsPhSignals",
    "RateRange",
    "extract",
]


@dataclass(frozen=True)
class RateRange:
    min: int | None
    max: int | None
    currency: str
    period: str


@dataclass(frozen=True)
class OnlineJobsPhSignals:
    rate_range: RateRange | None
    role_type: str | None


# --- Rate-range patterns -------------------------------------------------
#
# USD: `$800-1200/month`, `$800 - $1,200 / month`, `$800/month`,
#      `monthly rate: $800`, `monthly rate: $800-1200`.
# PHP: `PHP 40,000-60,000 monthly`, `PHP 40k-60k monthly`, `PHP 40k monthly`.
#
# The patterns deliberately do not try to handle every phrasing — they cover
# the OJ.ph postings the author has seen. Unmatched JDs return `None` so the
# downstream red-flag check skips silently.

_USD_RANGE_PATTERN = re.compile(
    r"\$\s*(?P<min>\d{1,3}(?:,\d{3})+|\d+)"
    r"\s*-\s*\$?\s*(?P<max>\d{1,3}(?:,\d{3})+|\d+)"
    r"\s*/?\s*(?:per\s+)?month",
    re.IGNORECASE,
)

_USD_SINGLE_PATTERN = re.compile(
    r"\$\s*(?P<value>\d{1,3}(?:,\d{3})+|\d+)\s*/?\s*(?:per\s+)?month",
    re.IGNORECASE,
)

_USD_MONTHLY_RATE_LABEL_RANGE = re.compile(
    r"monthly\s+rate\s*:\s*\$\s*(?P<min>\d{1,3}(?:,\d{3})+|\d+)"
    r"\s*-\s*\$?\s*(?P<max>\d{1,3}(?:,\d{3})+|\d+)",
    re.IGNORECASE,
)

_USD_MONTHLY_RATE_LABEL_SINGLE = re.compile(
    r"monthly\s+rate\s*:\s*\$\s*(?P<value>\d{1,3}(?:,\d{3})+|\d+)",
    re.IGNORECASE,
)

_PHP_RANGE_PATTERN = re.compile(
    r"\bphp\s*(?P<min>\d{1,3}(?:,\d{3})+|\d+)(?P<min_k>k)?"
    r"\s*-\s*(?P<max>\d{1,3}(?:,\d{3})+|\d+)(?P<max_k>k)?"
    r"\s*(?:per\s+month|monthly|/\s*month)",
    re.IGNORECASE,
)

_PHP_SINGLE_PATTERN = re.compile(
    r"\bphp\s*(?P<value>\d{1,3}(?:,\d{3})+|\d+)(?P<k>k)?"
    r"\s*(?:per\s+month|monthly|/\s*month)",
    re.IGNORECASE,
)

# --- Role-type patterns --------------------------------------------------

_FULL_TIME_PATTERN = re.compile(
    r"\b(?:full[\s-]?time|FT)\b",
    re.IGNORECASE,
)

_PART_TIME_PATTERN = re.compile(
    r"\b(?:part[\s-]?time|PT)\b",
    re.IGNORECASE,
)

_GIG_PATTERN = re.compile(
    r"\b(?:gig|one[\s-]?off|project\s+basis)\b",
    re.IGNORECASE,
)


def extract(jd_text: str) -> OnlineJobsPhSignals:
    """Extract OJ.ph-specific signals from *jd_text* via regex heuristics."""
    return OnlineJobsPhSignals(
        rate_range=_extract_rate_range(jd_text),
        role_type=_extract_role_type(jd_text),
    )


def _extract_rate_range(jd_text: str) -> RateRange | None:
    label_range = _USD_MONTHLY_RATE_LABEL_RANGE.search(jd_text)
    if label_range is not None:
        return RateRange(
            min=_to_int(label_range.group("min")),
            max=_to_int(label_range.group("max")),
            currency="USD",
            period="monthly",
        )

    label_single = _USD_MONTHLY_RATE_LABEL_SINGLE.search(jd_text)
    if label_single is not None:
        value = _to_int(label_single.group("value"))
        return RateRange(min=value, max=value, currency="USD", period="monthly")

    usd_range = _USD_RANGE_PATTERN.search(jd_text)
    if usd_range is not None:
        return RateRange(
            min=_to_int(usd_range.group("min")),
            max=_to_int(usd_range.group("max")),
            currency="USD",
            period="monthly",
        )

    usd_single = _USD_SINGLE_PATTERN.search(jd_text)
    if usd_single is not None:
        value = _to_int(usd_single.group("value"))
        return RateRange(min=value, max=value, currency="USD", period="monthly")

    php_range = _PHP_RANGE_PATTERN.search(jd_text)
    if php_range is not None:
        return RateRange(
            min=_php_amount(php_range.group("min"), php_range.group("min_k")),
            max=_php_amount(php_range.group("max"), php_range.group("max_k")),
            currency="PHP",
            period="monthly",
        )

    php_single = _PHP_SINGLE_PATTERN.search(jd_text)
    if php_single is not None:
        value = _php_amount(php_single.group("value"), php_single.group("k"))
        return RateRange(min=value, max=value, currency="PHP", period="monthly")

    return None


def _extract_role_type(jd_text: str) -> str | None:
    if _FULL_TIME_PATTERN.search(jd_text):
        return "full_time"
    if _PART_TIME_PATTERN.search(jd_text):
        return "part_time"
    if _GIG_PATTERN.search(jd_text):
        return "gig"
    return None


def _to_int(raw: str) -> int:
    return int(raw.replace(",", ""))


def _php_amount(raw: str, k_suffix: str | None) -> int:
    base = _to_int(raw)
    return base * 1000 if k_suffix else base
