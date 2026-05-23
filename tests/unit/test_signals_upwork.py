"""Unit tests for `jobhunter.signals_upwork` (Story 2.5)."""

from __future__ import annotations

import pytest

from jobhunter.signals_upwork import (
    PRICING_FIXED,
    PRICING_HOURLY,
    PRICING_UNKNOWN,
    UpworkSignals,
    detect_budget_below_floor,
    detect_vague_scope,
    extract,
)


# --- AC1: signals populated when present ---------------------------------


def test_extracts_hourly_band() -> None:
    jd = "Senior Python role on Upwork. Budget $25-50/hr depending on skill.\n"
    signals = extract(jd)
    assert signals.pricing_type == PRICING_HOURLY
    assert signals.budget_band == "$25-50/hr"


def test_extracts_hourly_band_with_per_hour() -> None:
    jd = "Rate range: $30 to $60 per hour.\n"
    signals = extract(jd)
    assert signals.pricing_type == PRICING_HOURLY
    assert signals.budget_band == "$30-60/hr"


def test_extracts_single_hourly_rate() -> None:
    jd = "We pay $40/hr for the right candidate.\n"
    signals = extract(jd)
    assert signals.pricing_type == PRICING_HOURLY
    assert signals.budget_band == "$40/hr"


def test_extracts_fixed_budget() -> None:
    jd = "Project budget: $1500 for a one-shot delivery.\n"
    signals = extract(jd)
    assert signals.pricing_type == PRICING_FIXED
    assert signals.budget_band == "$1500 fixed"


def test_extracts_fixed_price_phrasing() -> None:
    jd = "Fixed-price: $800. Two-week delivery.\n"
    signals = extract(jd)
    assert signals.pricing_type == PRICING_FIXED
    assert signals.budget_band == "$800 fixed"


def test_extracts_fixed_inline_phrasing() -> None:
    jd = "We will pay $2000 fixed for this engagement.\n"
    signals = extract(jd)
    assert signals.pricing_type == PRICING_FIXED
    assert signals.budget_band == "$2000 fixed"


def test_hourly_hint_without_amount_marks_pricing_only() -> None:
    jd = "We pay hourly — rate negotiable.\n"
    signals = extract(jd)
    assert signals.pricing_type == PRICING_HOURLY
    assert signals.budget_band is None


def test_fixed_hint_without_amount_marks_pricing_only() -> None:
    jd = "This is a fixed-price gig — scope to be agreed.\n"
    signals = extract(jd)
    assert signals.pricing_type == PRICING_FIXED
    assert signals.budget_band is None


def test_unknown_when_no_budget_signal() -> None:
    jd = "Senior Python role. Apply with your portfolio.\n"
    signals = extract(jd)
    assert signals.pricing_type == PRICING_UNKNOWN
    assert signals.budget_band is None


def test_missing_fields_are_none_or_empty() -> None:
    signals = extract("")
    assert signals.budget_band is None
    assert signals.pricing_type == PRICING_UNKNOWN
    assert signals.screening_questions == []


# --- AC1: screening-question extraction ----------------------------------


def test_extracts_screening_questions_block() -> None:
    jd = (
        "About the role…\n\n"
        "Screening Questions:\n"
        "- Why are you a good fit?\n"
        "- What is your experience with FastAPI?\n"
        "- Are you available 20+ hours/week?\n"
        "\n"
        "Apply now.\n"
    )
    signals = extract(jd)
    assert signals.screening_questions == [
        "Why are you a good fit?",
        "What is your experience with FastAPI?",
        "Are you available 20+ hours/week?",
    ]


def test_screening_questions_supports_numbered_lists() -> None:
    jd = (
        "Screening Questions\n"
        "1. Why this role?\n"
        "2. Earliest start date?\n"
    )
    signals = extract(jd)
    assert signals.screening_questions == [
        "Why this role?",
        "Earliest start date?",
    ]


def test_screening_questions_is_empty_when_absent() -> None:
    jd = "Senior role on upwork.com.\n"
    signals = extract(jd)
    assert signals.screening_questions == []


# --- AC2: budget-below-floor detection -----------------------------------


def test_hourly_budget_below_floor_triggers() -> None:
    jd = "Budget $15/hr — must be a Python ninja.\n"
    assert detect_budget_below_floor(jd, hourly_floor=25, fixed_floor=500) is True


def test_hourly_budget_at_floor_does_not_trigger() -> None:
    jd = "Budget $25/hr.\n"
    assert detect_budget_below_floor(jd, hourly_floor=25, fixed_floor=500) is False


def test_hourly_budget_above_floor_does_not_trigger() -> None:
    jd = "Budget $40/hr.\n"
    assert detect_budget_below_floor(jd, hourly_floor=25, fixed_floor=500) is False


def test_hourly_band_uses_low_end_for_floor_check() -> None:
    jd = "Budget $15-30/hr.\n"
    assert detect_budget_below_floor(jd, hourly_floor=25, fixed_floor=500) is True


def test_fixed_budget_below_floor_triggers() -> None:
    jd = "Project budget: $250.\n"
    assert detect_budget_below_floor(jd, hourly_floor=25, fixed_floor=500) is True


def test_fixed_budget_at_floor_does_not_trigger() -> None:
    jd = "Project budget: $500.\n"
    assert detect_budget_below_floor(jd, hourly_floor=25, fixed_floor=500) is False


def test_unknown_pricing_does_not_trigger_floor_flag() -> None:
    jd = "Generic Upwork posting.\n"
    assert detect_budget_below_floor(jd, hourly_floor=25, fixed_floor=500) is False


def test_pricing_hint_without_amount_does_not_trigger() -> None:
    jd = "Fixed-price project, scope TBD.\n"
    assert detect_budget_below_floor(jd, hourly_floor=25, fixed_floor=500) is False


# --- AC3: vague-scope detection ------------------------------------------


@pytest.mark.parametrize(
    "phrase",
    [
        "please make it amazing",
        "Please Make It Amazing",
        "PLEASE MAKE IT AMAZING",
        "Looking for someone awesome",
        "we need a rockstar",
        "be your own boss",
        "an exciting opportunity",
    ],
)
def test_vague_scope_phrases_trigger(phrase: str) -> None:
    jd = f"Senior role.\n{phrase}\nApply now.\n"
    assert detect_vague_scope(jd) is True


def test_neutral_jd_does_not_trigger_vague_scope() -> None:
    jd = (
        "We are hiring a senior Python engineer with FastAPI and Postgres "
        "experience. Apply with your portfolio.\n"
    )
    assert detect_vague_scope(jd) is False


# --- Invariants: dataclass shape and immutability ------------------------


def test_upwork_signals_is_frozen() -> None:
    signals = extract("")
    with pytest.raises(Exception):
        signals.pricing_type = PRICING_HOURLY  # type: ignore[misc]


def test_upwork_signals_documented_fields() -> None:
    signals = UpworkSignals(
        budget_band="$25-50/hr",
        pricing_type=PRICING_HOURLY,
        screening_questions=["Q1?", "Q2?"],
    )
    assert signals.budget_band == "$25-50/hr"
    assert signals.pricing_type == PRICING_HOURLY
    assert signals.screening_questions == ["Q1?", "Q2?"]


def test_pricing_type_is_one_of_three_values() -> None:
    assert {PRICING_HOURLY, PRICING_FIXED, PRICING_UNKNOWN} == {
        "hourly",
        "fixed",
        "unknown",
    }
