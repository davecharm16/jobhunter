"""Unit tests for `jobhunter.board_classifier` (Story 2.4)."""

from __future__ import annotations

import pytest

from jobhunter.board_classifier import (
    ALLOWED_SOURCE_BOARDS,
    Classification,
    InvalidSourceBoard,
    classify_board,
)
from jobhunter.jd_parser import ParsedJD


def _parsed(raw_text_length: int = 50) -> ParsedJD:
    return ParsedJD(
        must_haves=["Python"],
        nice_to_haves=["Docker"],
        tone="neutral",
        seniority="senior",
        red_flags=[],
        raw_text_length=raw_text_length,
    )


# --- AC1: Upwork heuristics ----------------------------------------------


@pytest.mark.parametrize(
    "jd_text",
    [
        "We posted this on https://www.upwork.com/jobs/12345\n",
        "Find me on Upwork.com/freelancer/abc",
        "Apply via the Project Catalog on our profile.",
        "Talent Marketplace — we hire senior Python folks.",
        "Connects required: 4. Submit your proposal below.",
    ],
)
def test_classifies_upwork_via_heuristic(jd_text: str) -> None:
    result = classify_board(jd_text, _parsed())
    assert result == Classification(source_board="upwork", method="heuristic")


# --- AC1: OnlineJobs.ph heuristics ---------------------------------------


@pytest.mark.parametrize(
    "jd_text",
    [
        "Posted on onlinejobs.ph — Filipino VAs only.\n",
        "Apply at https://www.onlinejobs.ph/jobseekers/job/12345",
        "PHP/USD rate: 800 USD monthly.",
    ],
)
def test_classifies_onlinejobs_ph_via_heuristic(jd_text: str) -> None:
    result = classify_board(jd_text, _parsed())
    assert result == Classification(source_board="onlinejobs_ph", method="heuristic")


# --- AC1: LinkedIn heuristics --------------------------------------------


@pytest.mark.parametrize(
    "jd_text",
    [
        "Apply via https://www.linkedin.com/jobs/view/12345",
        "LinkedIn Easy Apply available.",
        "Sourced via LinkedIn — please apply directly.",
    ],
)
def test_classifies_linkedin_via_heuristic(jd_text: str) -> None:
    result = classify_board(jd_text, _parsed())
    assert result == Classification(source_board="linkedin", method="heuristic")


# --- AC3: unmatched JD resolves to "other" -------------------------------


def test_unmatched_jd_resolves_to_other() -> None:
    result = classify_board(
        "We are hiring a senior Python developer. Email careers@acme.com.\n",
        _parsed(),
    )
    assert result == Classification(source_board="other", method="heuristic")


def test_empty_text_resolves_to_other() -> None:
    result = classify_board("", _parsed(raw_text_length=0))
    assert result == Classification(source_board="other", method="heuristic")


# --- AC1: heuristics are case-insensitive --------------------------------


def test_upwork_heuristic_is_case_insensitive() -> None:
    result = classify_board("Find us on UPWORK.COM today.", _parsed())
    assert result.source_board == "upwork"


# --- AC2: explicit override bypasses heuristics --------------------------


@pytest.mark.parametrize(
    "override", ["upwork", "onlinejobs_ph", "linkedin", "other"]
)
def test_explicit_override_bypasses_heuristics(override: str) -> None:
    # JD text screams Upwork — override must win regardless.
    jd_text = "Posted on upwork.com — Connects required.\n"
    result = classify_board(jd_text, _parsed(), explicit_override=override)
    assert result == Classification(source_board=override, method="explicit_override")


def test_explicit_override_outside_allowed_set_raises() -> None:
    with pytest.raises(InvalidSourceBoard, match="indeed"):
        classify_board("JD", _parsed(), explicit_override="indeed")


def test_none_override_runs_heuristics() -> None:
    result = classify_board("upwork.com", _parsed(), explicit_override=None)
    assert result.method == "heuristic"


# --- Invariant: classification value is always in the allowed set --------


def test_allowed_source_boards_constant() -> None:
    assert ALLOWED_SOURCE_BOARDS == frozenset(
        {"upwork", "onlinejobs_ph", "linkedin", "other"}
    )


def test_classification_is_frozen_dataclass() -> None:
    result = classify_board("upwork.com", _parsed())
    with pytest.raises(Exception):
        result.source_board = "linkedin"  # type: ignore[misc]


# --- Heuristic priority: Upwork > OJ.ph > LinkedIn when multiple match ---


def test_upwork_wins_over_linkedin_when_both_present() -> None:
    jd_text = (
        "Cross-posted on upwork.com and linkedin.com/jobs/view/123.\n"
    )
    result = classify_board(jd_text, _parsed())
    assert result.source_board == "upwork"
