"""Unit tests for `jobhunter.signals_onlinejobs_ph` (Story 2.6).

Heuristic-only extractor — no LLM call, no I/O. Tests cover:
- AC1 rate-range detection (USD range, USD single, PHP range, PHP single,
  `monthly rate:` label variants).
- AC1 role-type detection (full-time / part-time / gig synonyms,
  case-insensitive).
- AC1 missing fields surface as `None`, never fabricated.
- Frozen-dataclass invariant.
"""

from __future__ import annotations

import pytest

from jobhunter.signals_onlinejobs_ph import (
    OnlineJobsPhSignals,
    RateRange,
    extract,
)

# --- AC1: USD rate-range detection ----------------------------------------


@pytest.mark.parametrize(
    "jd_text,expected_min,expected_max",
    [
        ("Pay is $800-1200/month for the right person.\n", 800, 1200),
        ("Pay is $800 - $1200 / month.\n", 800, 1200),
        ("Budget: $1,000-$2,000 per month.\n", 1000, 2000),
        ("monthly rate: $800-1200.\n", 800, 1200),
    ],
)
def test_extract_usd_rate_range(
    jd_text: str, expected_min: int, expected_max: int
) -> None:
    result = extract(jd_text)
    assert result.rate_range == RateRange(
        min=expected_min,
        max=expected_max,
        currency="USD",
        period="monthly",
    )


@pytest.mark.parametrize(
    "jd_text,expected_value",
    [
        ("Pay is $1000/month.\n", 1000),
        ("monthly rate: $750.\n", 750),
    ],
)
def test_extract_usd_single_rate(jd_text: str, expected_value: int) -> None:
    result = extract(jd_text)
    assert result.rate_range == RateRange(
        min=expected_value,
        max=expected_value,
        currency="USD",
        period="monthly",
    )


# --- AC1: PHP rate-range detection ----------------------------------------


@pytest.mark.parametrize(
    "jd_text,expected_min,expected_max",
    [
        ("Pay PHP 40,000-60,000 monthly.\n", 40000, 60000),
        ("PHP 40k-60k monthly.\n", 40000, 60000),
        ("php 40000-60000 per month.\n", 40000, 60000),
        ("PHP 30,000 - 50,000 /month.\n", 30000, 50000),
    ],
)
def test_extract_php_rate_range(
    jd_text: str, expected_min: int, expected_max: int
) -> None:
    result = extract(jd_text)
    assert result.rate_range == RateRange(
        min=expected_min,
        max=expected_max,
        currency="PHP",
        period="monthly",
    )


def test_extract_php_single_rate_with_k_suffix() -> None:
    result = extract("Pay PHP 45k monthly.\n")
    assert result.rate_range == RateRange(
        min=45000, max=45000, currency="PHP", period="monthly"
    )


def test_extract_php_single_rate_without_k_suffix() -> None:
    result = extract("Pay PHP 45,000 monthly.\n")
    assert result.rate_range == RateRange(
        min=45000, max=45000, currency="PHP", period="monthly"
    )


# --- AC1: role-type detection --------------------------------------------


@pytest.mark.parametrize(
    "jd_text",
    [
        "This is a full-time role.\n",
        "This is a full time role.\n",
        "FT role only.\n",
        "We are hiring FULL-TIME staff.\n",
    ],
)
def test_extract_role_type_full_time(jd_text: str) -> None:
    result = extract(jd_text)
    assert result.role_type == "full_time"


@pytest.mark.parametrize(
    "jd_text",
    [
        "This is a part-time role.\n",
        "This is a part time role.\n",
        "PT role only.\n",
    ],
)
def test_extract_role_type_part_time(jd_text: str) -> None:
    result = extract(jd_text)
    assert result.role_type == "part_time"


@pytest.mark.parametrize(
    "jd_text",
    [
        "This is a gig.\n",
        "One-off project.\n",
        "Hiring on a project basis.\n",
    ],
)
def test_extract_role_type_gig(jd_text: str) -> None:
    result = extract(jd_text)
    assert result.role_type == "gig"


# --- AC1: missing fields surface as None ---------------------------------


def test_extract_with_no_signals_returns_all_none() -> None:
    result = extract("Senior Python role at Acme.\n")
    assert result == OnlineJobsPhSignals(rate_range=None, role_type=None)


def test_extract_with_rate_only_leaves_role_type_none() -> None:
    result = extract("Pay is $800/month.\n")
    assert result.rate_range is not None
    assert result.role_type is None


def test_extract_with_role_type_only_leaves_rate_none() -> None:
    result = extract("Full-time only.\n")
    assert result.rate_range is None
    assert result.role_type == "full_time"


def test_extract_empty_string_returns_all_none() -> None:
    result = extract("")
    assert result == OnlineJobsPhSignals(rate_range=None, role_type=None)


# --- AC1: precedence — full_time wins over part_time when both present ----


def test_full_time_wins_over_part_time_when_both_match() -> None:
    """A JD that mentions both surfaces the stronger signal (full_time)."""
    result = extract("Hiring full-time, with part-time options.\n")
    assert result.role_type == "full_time"


# --- Frozen-dataclass invariants ------------------------------------------


def test_rate_range_is_frozen_dataclass() -> None:
    rate = RateRange(min=800, max=1200, currency="USD", period="monthly")
    with pytest.raises(Exception):
        rate.min = 0  # type: ignore[misc]


def test_signals_is_frozen_dataclass() -> None:
    signals = OnlineJobsPhSignals(rate_range=None, role_type=None)
    with pytest.raises(Exception):
        signals.role_type = "full_time"  # type: ignore[misc]
