"""Unit tests for `jobhunter.content_loss_matcher` (Story 4.1 AC1-AC5).

Mirrors `test_fabrication_matcher.py` patterns: pure-function assertions,
frozen dataclasses, deterministic ids, no LLM stubs (AC5 is "no LLM call").
The matcher is rule-based and consumes only:

* canonical CV dict (already validated by `canonical_cv.read_canonical_cv`)
* parsed JD dict (the `dataclasses.asdict(ParsedJD)` shape from
  `tailoring.py`'s orchestration)
* on-disk artifact paths
* parsed `tailoring.trace.json` dropped_entries list
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest

from jobhunter.content_loss_matcher import (
    ContentLossCheck,
    DroppedEntry,
    HighImpactEntry,
    PreservedEntry,
    iter_high_impact_relevant,
    run_check,
)


# ---- helpers --------------------------------------------------------------


def _expected_entry_id(section: str, index: int, primary_text: str) -> str:
    """Mirror `content_loss_matcher._entry_id`; pinned here to lock the contract."""
    digest = hashlib.sha1(primary_text.encode("utf-8")).hexdigest()[:8]
    return f"{section}[{index}]:{digest}"


def _write_artifact(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def _cv_with_flagged_work() -> dict[str, Any]:
    """A canonical CV with one high-impact work entry tagged for relevance tests."""
    return {
        "basics": {"name": "Dave"},
        "work": [
            {
                "name": "Acme",
                "position": "Senior Engineer",
                "tags": ["typescript", "node", "fintech"],
                "highImpact": True,
                "highlights": [
                    "Shipped a TypeScript ingestion service",
                    "Led the on-call rotation",
                ],
            },
            {
                "name": "Other Corp",
                "position": "Junior Engineer",
                "tags": ["go"],
                "highlights": ["Helped out"],
            },
        ],
    }


# ---- AC1: tag-overlap relevance anchoring ---------------------------------


class TestRelevanceAnchoring:
    """AC1 — deterministic tag overlap; no LLM call."""

    def test_work_entry_with_must_have_tag_is_relevant(self) -> None:
        cv = _cv_with_flagged_work()
        parsed_jd = {"must_haves": ["TypeScript"], "nice_to_haves": []}

        result = iter_high_impact_relevant(cv, parsed_jd)

        assert len(result) == 1
        assert result[0].section == "work"
        assert "typescript" in result[0].jd_requirements_matched

    def test_work_entry_with_nice_to_have_tag_is_relevant(self) -> None:
        cv = _cv_with_flagged_work()
        parsed_jd = {"must_haves": ["Rust"], "nice_to_haves": ["node"]}

        result = iter_high_impact_relevant(cv, parsed_jd)

        assert len(result) == 1
        assert "node" in result[0].jd_requirements_matched

    def test_match_is_case_insensitive(self) -> None:
        cv = _cv_with_flagged_work()
        parsed_jd = {"must_haves": ["TYPESCRIPT"], "nice_to_haves": []}

        result = iter_high_impact_relevant(cv, parsed_jd)

        assert len(result) == 1

    def test_non_high_impact_entry_is_excluded(self) -> None:
        """The second work entry has tag 'go' but `highImpact` is absent."""
        cv = _cv_with_flagged_work()
        parsed_jd = {"must_haves": ["Go"], "nice_to_haves": []}

        result = iter_high_impact_relevant(cv, parsed_jd)

        assert result == []

    def test_high_impact_but_no_tag_overlap_is_excluded(self) -> None:
        cv = _cv_with_flagged_work()
        parsed_jd = {"must_haves": ["Rust"], "nice_to_haves": ["Haskell"]}

        result = iter_high_impact_relevant(cv, parsed_jd)

        assert result == []

    def test_entry_id_is_deterministic_across_calls(self) -> None:
        cv = _cv_with_flagged_work()
        parsed_jd = {"must_haves": ["typescript"], "nice_to_haves": []}

        first = iter_high_impact_relevant(cv, parsed_jd)
        second = iter_high_impact_relevant(cv, parsed_jd)

        assert first[0].entry_id == second[0].entry_id
        # The id pins to the section[index] + primary_text hash idiom from
        # Story 3.2 — the contract Story 4.2 will rely on for diff stability.
        expected = _expected_entry_id("work", 0, first[0].primary_text)
        assert first[0].entry_id == expected

    def test_walks_work_projects_skills_in_documented_order(self) -> None:
        cv = {
            "work": [
                {
                    "name": "W",
                    "position": "Eng",
                    "tags": ["x"],
                    "highImpact": True,
                    "highlights": [],
                }
            ],
            "projects": [
                {
                    "name": "P",
                    "tags": ["x"],
                    "highImpact": True,
                    "highlights": [],
                }
            ],
            "skills": [
                {
                    "name": "S",
                    "tags": ["x"],
                    "highImpact": True,
                    "keywords": ["foo"],
                }
            ],
        }
        parsed_jd = {"must_haves": ["x"], "nice_to_haves": []}

        result = iter_high_impact_relevant(cv, parsed_jd)

        assert [e.section for e in result] == ["work", "projects", "skills"]

    def test_empty_jd_requirements_yields_empty_must_appear_set(self) -> None:
        cv = _cv_with_flagged_work()
        parsed_jd: dict[str, Any] = {"must_haves": [], "nice_to_haves": []}

        result = iter_high_impact_relevant(cv, parsed_jd)

        assert result == []


# ---- AC1: primary-text projection per section -----------------------------


class TestPrimaryTextProjection:
    """The primary text drives AC2 substring matching — its shape per section
    is part of the matcher's contract."""

    def test_work_section_uses_position_at_name_plus_highlights(self) -> None:
        cv = _cv_with_flagged_work()
        parsed_jd = {"must_haves": ["typescript"], "nice_to_haves": []}

        result = iter_high_impact_relevant(cv, parsed_jd)

        assert "Senior Engineer at Acme" in result[0].primary_text
        assert "Shipped a TypeScript ingestion service" in result[0].primary_text

    def test_projects_section_uses_name_plus_highlights(self) -> None:
        cv = {
            "projects": [
                {
                    "name": "jobhunter",
                    "tags": ["llm"],
                    "highImpact": True,
                    "highlights": ["walking skeleton first"],
                }
            ]
        }
        parsed_jd = {"must_haves": ["llm"], "nice_to_haves": []}

        result = iter_high_impact_relevant(cv, parsed_jd)

        assert "jobhunter" in result[0].primary_text
        assert "walking skeleton first" in result[0].primary_text

    def test_skills_section_uses_name_plus_keywords(self) -> None:
        cv = {
            "skills": [
                {
                    "name": "Backend",
                    "tags": ["api"],
                    "highImpact": True,
                    "keywords": ["FastAPI", "Postgres"],
                }
            ]
        }
        parsed_jd = {"must_haves": ["api"], "nice_to_haves": []}

        result = iter_high_impact_relevant(cv, parsed_jd)

        assert "Backend" in result[0].primary_text
        assert "FastAPI" in result[0].primary_text
        assert "Postgres" in result[0].primary_text

    def test_work_with_no_highlights_falls_back_to_role_string(self) -> None:
        cv = {
            "work": [
                {
                    "name": "Acme",
                    "position": "Engineer",
                    "tags": ["x"],
                    "highImpact": True,
                }
            ]
        }
        parsed_jd = {"must_haves": ["x"], "nice_to_haves": []}

        result = iter_high_impact_relevant(cv, parsed_jd)

        assert result[0].primary_text == "Engineer at Acme"


# ---- AC2: substring presence in tailored artifacts ------------------------


class TestPresenceVerification:
    """AC2 — case-insensitive substring match of any chunk of primary_text."""

    def _entry(self, primary_text: str) -> HighImpactEntry:
        return HighImpactEntry(
            entry_id="work[0]:abc12345",
            section="work",
            primary_text=primary_text,
            tags=["typescript"],
            jd_requirements_matched=["typescript"],
        )

    def test_chunk_present_in_cv_marks_preserved(self, tmp_path: Path) -> None:
        cv_path = _write_artifact(
            tmp_path, "cv.md", "Senior Engineer at Acme — ships TypeScript\n"
        )
        entry = self._entry(
            "Senior Engineer at Acme | Shipped a TypeScript ingestion service"
        )

        result = run_check([entry], {"cv.md": cv_path}, [])

        assert result.verdict == "pass"
        assert len(result.preserved_entries) == 1
        assert result.preserved_entries[0].matched_in == ["cv.md"]
        assert result.preserved_entries[0].match_type == "substring"

    def test_match_is_case_insensitive(self, tmp_path: Path) -> None:
        cv_path = _write_artifact(
            tmp_path, "cv.md", "SENIOR ENGINEER AT ACME\n"
        )
        entry = self._entry("Senior Engineer at Acme | other stuff")

        result = run_check([entry], {"cv.md": cv_path}, [])

        assert result.verdict == "pass"

    def test_chunk_in_cover_letter_only_still_preserves(self, tmp_path: Path) -> None:
        """AC2: chunk-match in ANY artifact counts as preserved."""
        cv_path = _write_artifact(tmp_path, "cv.md", "unrelated text\n")
        cover_path = _write_artifact(
            tmp_path, "cover-letter.md", "Shipped a TypeScript ingestion service\n"
        )
        entry = self._entry(
            "Senior Engineer at Acme | Shipped a TypeScript ingestion service"
        )

        result = run_check(
            [entry],
            {"cv.md": cv_path, "cover-letter.md": cover_path},
            [],
        )

        assert result.verdict == "pass"
        assert result.preserved_entries[0].matched_in == ["cover-letter.md"]

    def test_chunk_in_multiple_artifacts_reports_each(self, tmp_path: Path) -> None:
        cv_path = _write_artifact(tmp_path, "cv.md", "Senior Engineer at Acme\n")
        cover_path = _write_artifact(
            tmp_path, "cover-letter.md", "Senior Engineer at Acme\n"
        )
        entry = self._entry("Senior Engineer at Acme")

        result = run_check(
            [entry],
            {"cv.md": cv_path, "cover-letter.md": cover_path},
            [],
        )

        assert result.preserved_entries[0].matched_in == ["cv.md", "cover-letter.md"]

    def test_missing_artifact_file_is_tolerated(self, tmp_path: Path) -> None:
        """AC2: a missing file silently drops out — the entry can still match
        elsewhere."""
        cv_path = _write_artifact(tmp_path, "cv.md", "Senior Engineer at Acme\n")
        missing = tmp_path / "upwork-proposal.md"  # never created
        entry = self._entry("Senior Engineer at Acme")

        result = run_check(
            [entry],
            {"cv.md": cv_path, "upwork-proposal.md": missing},
            [],
        )

        assert result.verdict == "pass"
        assert result.preserved_entries[0].matched_in == ["cv.md"]

    def test_no_chunk_match_anywhere_lands_in_dropped(self, tmp_path: Path) -> None:
        cv_path = _write_artifact(tmp_path, "cv.md", "totally unrelated text\n")
        entry = self._entry("Senior Engineer at Acme")

        result = run_check([entry], {"cv.md": cv_path}, [])

        assert result.verdict == "fail"
        assert len(result.dropped_entries) == 1
        assert result.dropped_entries[0].reason == "silently_lost"


# ---- AC3: explicit omission rationale via tailoring.trace.json ------------


class TestExplicitOmissionRationale:
    """AC3 — `dropped_entries[].reason == 'irrelevant_to_jd'` exempts from fail."""

    def _missing_entry(self) -> HighImpactEntry:
        return HighImpactEntry(
            entry_id="work[0]:deadbeef",
            section="work",
            primary_text="Senior Engineer at Acme",
            tags=["typescript"],
            jd_requirements_matched=["typescript"],
        )

    def test_logged_irrelevant_drop_does_not_fail(self, tmp_path: Path) -> None:
        cv_path = _write_artifact(tmp_path, "cv.md", "completely different\n")
        trace = [{"entry_id": "work[0]:deadbeef", "reason": "irrelevant_to_jd"}]

        result = run_check([self._missing_entry()], {"cv.md": cv_path}, trace)

        assert result.verdict == "pass"
        # The entry still appears in dropped_entries — with the logged reason.
        assert len(result.dropped_entries) == 1
        assert result.dropped_entries[0].reason == "irrelevant_to_jd"

    def test_unknown_reason_code_is_silently_lost(self, tmp_path: Path) -> None:
        cv_path = _write_artifact(tmp_path, "cv.md", "completely different\n")
        trace = [{"entry_id": "work[0]:deadbeef", "reason": "looked_weird"}]

        result = run_check([self._missing_entry()], {"cv.md": cv_path}, trace)

        assert result.verdict == "fail"
        assert result.dropped_entries[0].reason == "silently_lost"

    def test_missing_reason_field_is_silently_lost(self, tmp_path: Path) -> None:
        cv_path = _write_artifact(tmp_path, "cv.md", "completely different\n")
        trace = [{"entry_id": "work[0]:deadbeef"}]

        result = run_check([self._missing_entry()], {"cv.md": cv_path}, trace)

        assert result.verdict == "fail"
        assert result.dropped_entries[0].reason == "silently_lost"

    def test_empty_trace_treats_all_missing_entries_as_silently_lost(
        self, tmp_path: Path
    ) -> None:
        cv_path = _write_artifact(tmp_path, "cv.md", "completely different\n")

        result = run_check([self._missing_entry()], {"cv.md": cv_path}, [])

        assert result.verdict == "fail"
        assert result.dropped_entries[0].reason == "silently_lost"

    def test_trace_entry_without_entry_id_is_ignored(self, tmp_path: Path) -> None:
        cv_path = _write_artifact(tmp_path, "cv.md", "completely different\n")
        # Trace entry missing the entry_id key cannot be paired with any
        # high-impact entry — the matcher should ignore it (not crash).
        trace = [{"reason": "irrelevant_to_jd"}]

        result = run_check([self._missing_entry()], {"cv.md": cv_path}, trace)

        assert result.verdict == "fail"
        assert result.dropped_entries[0].reason == "silently_lost"

    def test_jd_requirements_addressed_is_captured_on_drop(
        self, tmp_path: Path
    ) -> None:
        """AC3 surface — `jd_requirements_addressed` lists the must-have/
        nice-to-have strings the dropped entry would have answered (FR27)."""
        cv_path = _write_artifact(tmp_path, "cv.md", "completely different\n")

        result = run_check([self._missing_entry()], {"cv.md": cv_path}, [])

        assert result.dropped_entries[0].jd_requirements_addressed == ["typescript"]


# ---- AC4: verdict reaching the metadata sidecar (logic-only assertion) ----


class TestVerdictAggregation:
    """AC4 logic half — at least one silent loss flips the verdict to fail.

    The Story 3.4 held-package wiring is an integration concern; Story 4.2
    persists the verdict to `package.drift.json`. The unit-level contract is:
    one silent loss is enough to fail, mixed pass+logged-drop stays pass.
    """

    def _entries_pair(self) -> list[HighImpactEntry]:
        return [
            HighImpactEntry(
                entry_id="work[0]:00000001",
                section="work",
                primary_text="Engineer at Acme",
                tags=["x"],
                jd_requirements_matched=["x"],
            ),
            HighImpactEntry(
                entry_id="work[1]:00000002",
                section="work",
                primary_text="Engineer at Beta",
                tags=["x"],
                jd_requirements_matched=["x"],
            ),
        ]

    def test_one_silent_loss_among_preserved_still_fails(
        self, tmp_path: Path
    ) -> None:
        cv_path = _write_artifact(tmp_path, "cv.md", "Engineer at Acme\n")

        result = run_check(self._entries_pair(), {"cv.md": cv_path}, [])

        assert result.verdict == "fail"
        assert len(result.preserved_entries) == 1
        assert len(result.dropped_entries) == 1
        assert result.dropped_entries[0].reason == "silently_lost"

    def test_logged_drop_mixed_with_preserved_passes(self, tmp_path: Path) -> None:
        cv_path = _write_artifact(tmp_path, "cv.md", "Engineer at Acme\n")
        trace = [{"entry_id": "work[1]:00000002", "reason": "irrelevant_to_jd"}]

        result = run_check(self._entries_pair(), {"cv.md": cv_path}, trace)

        assert result.verdict == "pass"
        assert len(result.preserved_entries) == 1
        assert len(result.dropped_entries) == 1

    def test_empty_must_appear_set_passes(self, tmp_path: Path) -> None:
        cv_path = _write_artifact(tmp_path, "cv.md", "anything\n")

        result = run_check([], {"cv.md": cv_path}, [])

        assert result.verdict == "pass"
        assert result.preserved_entries == []
        assert result.dropped_entries == []


# ---- AC5: zero LLM calls --------------------------------------------------


class TestNoLLMCalls:
    """AC5 — the matcher imports and invokes zero LLM client surfaces.

    Structural guarantee: `content_loss_matcher` does not import
    `jobhunter.llm_client`, `claim_extractor`, `semantic_matcher`, or
    `prompts`. Functional guarantee: monkeypatching the LLM call sites to
    raise verifies they are never invoked during a content-loss check.
    """

    def test_module_does_not_import_llm_client(self) -> None:
        import jobhunter.content_loss_matcher as module

        # The matcher reaches `llm_client` neither directly nor through a
        # tailoring-style re-export. Walk the module's name table.
        assert "llm_client" not in module.__dict__
        assert "semantic_matcher" not in module.__dict__
        assert "claim_extractor" not in module.__dict__

    def test_run_check_does_not_invoke_llm_client_tailor(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Trip any LLM call site to raise; the check must complete cleanly."""
        import jobhunter.llm_client as llm_module

        def must_not_run(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("content-loss check made an LLM call")

        monkeypatch.setattr(llm_module, "tailor", must_not_run, raising=False)
        monkeypatch.setattr(llm_module, "parse_jd", must_not_run, raising=False)
        monkeypatch.setattr(
            llm_module, "tailor_upwork_proposal", must_not_run, raising=False
        )
        cv_path = _write_artifact(tmp_path, "cv.md", "Engineer at Acme\n")
        entry = HighImpactEntry(
            entry_id="work[0]:abc12345",
            section="work",
            primary_text="Engineer at Acme",
            tags=["x"],
            jd_requirements_matched=["x"],
        )

        result = run_check([entry], {"cv.md": cv_path}, [])

        assert result.verdict == "pass"

    def test_iter_high_impact_relevant_makes_no_llm_call(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import jobhunter.llm_client as llm_module

        def must_not_run(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError(
                "iter_high_impact_relevant made an LLM call"
            )

        monkeypatch.setattr(llm_module, "tailor", must_not_run, raising=False)
        monkeypatch.setattr(llm_module, "parse_jd", must_not_run, raising=False)

        cv = _cv_with_flagged_work()
        parsed_jd = {"must_haves": ["typescript"], "nice_to_haves": []}

        result = iter_high_impact_relevant(cv, parsed_jd)

        assert len(result) == 1


# ---- frozen-dataclass invariants ------------------------------------------


class TestDataclassInvariants:
    """The four dataclasses are frozen — pinning the contract for Story 4.2."""

    def test_high_impact_entry_is_frozen(self) -> None:
        entry = HighImpactEntry(
            entry_id="x",
            section="work",
            primary_text="text",
        )
        with pytest.raises(Exception):
            entry.entry_id = "y"  # type: ignore[misc]

    def test_preserved_entry_is_frozen(self) -> None:
        preserved = PreservedEntry(
            entry_id="x",
            section="work",
            matched_in=["cv.md"],
            match_type="substring",
        )
        with pytest.raises(Exception):
            preserved.entry_id = "y"  # type: ignore[misc]

    def test_dropped_entry_is_frozen(self) -> None:
        dropped = DroppedEntry(
            entry_id="x",
            section="work",
            primary_text="text",
            jd_requirements_addressed=["typescript"],
            reason="silently_lost",
        )
        with pytest.raises(Exception):
            dropped.entry_id = "y"  # type: ignore[misc]

    def test_content_loss_check_is_frozen(self) -> None:
        check = ContentLossCheck(verdict="pass")
        with pytest.raises(Exception):
            check.verdict = "fail"  # type: ignore[misc]
