"""Unit tests for `jobhunter.artifact_selector` (Story 2.8)."""

from __future__ import annotations

import pytest

from jobhunter.artifact_selector import (
    ALLOWED_ARTIFACTS,
    ArtifactSelectionInvalid,
    DEFAULT_BY_BOARD,
    select,
)


# --- AC1: per-board defaults ---------------------------------------------


def test_upwork_defaults_to_cv_and_upwork_proposal() -> None:
    assert select("upwork") == ["cv", "upwork_proposal"]


def test_linkedin_defaults_to_cv_and_cover_letter() -> None:
    assert select("linkedin") == ["cv", "cover_letter"]


def test_onlinejobs_ph_defaults_to_cv_and_cover_letter() -> None:
    assert select("onlinejobs_ph") == ["cv", "cover_letter"]


def test_other_defaults_to_cv_and_cover_letter() -> None:
    assert select("other") == ["cv", "cover_letter"]


def test_unknown_source_board_falls_back_to_other_default() -> None:
    """A misclassified board never blocks the pipeline — fall back to `other`."""
    assert select("indeed") == DEFAULT_BY_BOARD["other"]


def test_default_by_board_table_matches_spec() -> None:
    assert DEFAULT_BY_BOARD == {
        "upwork": ["cv", "upwork_proposal"],
        "linkedin": ["cv", "cover_letter"],
        "onlinejobs_ph": ["cv", "cover_letter"],
        "other": ["cv", "cover_letter"],
    }


def test_select_returns_a_fresh_list_per_call() -> None:
    """Callers must not be able to mutate the in-module default."""
    first = select("upwork")
    first.append("cover_letter")
    second = select("upwork")
    assert second == ["cv", "upwork_proposal"]


# --- AC2: explicit override bypasses defaults ----------------------------


def test_explicit_override_replaces_default() -> None:
    result = select("upwork", explicit_override=["cv", "cover_letter"])
    assert result == ["cv", "cover_letter"]


def test_explicit_override_can_request_all_three_artifacts() -> None:
    result = select(
        "linkedin",
        explicit_override=["cv", "cover_letter", "upwork_proposal"],
    )
    assert result == ["cv", "cover_letter", "upwork_proposal"]


def test_explicit_override_returns_a_copy() -> None:
    """Mutating the returned list must not feed back into the caller's input."""
    requested = ["cv", "cover_letter"]
    result = select("upwork", explicit_override=requested)
    result.append("upwork_proposal")
    assert requested == ["cv", "cover_letter"]


def test_none_override_runs_default_logic() -> None:
    assert select("upwork", explicit_override=None) == ["cv", "upwork_proposal"]


# --- AC2: invalid overrides raise ----------------------------------------


def test_empty_override_raises() -> None:
    with pytest.raises(ArtifactSelectionInvalid, match="empty"):
        select("upwork", explicit_override=[])


def test_unknown_artifact_in_override_raises() -> None:
    with pytest.raises(ArtifactSelectionInvalid, match="portfolio"):
        select("linkedin", explicit_override=["cv", "portfolio"])


def test_typo_in_artifact_name_raises() -> None:
    with pytest.raises(ArtifactSelectionInvalid, match="cover-letter"):
        select("linkedin", explicit_override=["cv", "cover-letter"])


# --- Invariant: allowed-artifact set is the source of truth ---------------


def test_allowed_artifacts_constant() -> None:
    assert ALLOWED_ARTIFACTS == frozenset(
        {"cv", "cover_letter", "upwork_proposal"}
    )


@pytest.mark.parametrize("board", sorted(DEFAULT_BY_BOARD))
def test_every_default_only_uses_allowed_artifact_names(board: str) -> None:
    for name in DEFAULT_BY_BOARD[board]:
        assert name in ALLOWED_ARTIFACTS
