"""Unit tests for `jobhunter.fabrication_matcher` (Story 3.2 AC1-AC5).

Mirrors `test_claim_extractor.py` patterns: pure-function assertions, frozen
dataclasses, deterministic ids. The matcher itself has no LLM call so there
is no test seam to stub beyond the optional `semantic_step`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jobhunter.claim_extractor import Claim
from jobhunter.fabrication_matcher import (
    CanonicalEntry,
    FabricationCheck,
    Trace,
    UnsourcedClaim,
    iter_canonical_entries,
    run_matcher,
    write_drift_report,
)


# ---- helpers --------------------------------------------------------------


def _claim(text: str, *, claim_id: str | None = None, source: str = "cv",
           line: int = 1, claim_type: str = "skill") -> Claim:
    return Claim(
        claim_id=claim_id or f"{source}:{line}:abc12345",
        claim_type=claim_type,
        claim_text=text,
        source_artifact=source,
        line_number=line,
    )


def _cv() -> dict:
    """Minimal canonical CV covering each section the matcher walks (AC5)."""
    return {
        "basics": {"name": "Dave"},
        "work": [
            {
                "name": "Acme",
                "position": "Senior Engineer",
                "highlights": [
                    "Led the engineering team",
                    "Shipped a JSON-schema-validated ingestion layer",
                ],
            }
        ],
        "skills": [
            {"name": "Backend", "keywords": ["Python", "FastAPI", "PostgreSQL"]},
            {"name": "Testing", "keywords": ["pytest"]},
        ],
        "projects": [
            {
                "name": "jobhunter",
                "highlights": ["Walking-skeleton-first delivery"],
            }
        ],
        "education": [
            {
                "institution": "University Sample",
                "area": "Computer Science",
                "studyType": "Bachelor",
            }
        ],
    }


# ---- AC5: canonical entry universe ---------------------------------------


def test_iter_canonical_entries_walks_work_highlights() -> None:
    entries = iter_canonical_entries(_cv())
    texts = [e.text for e in entries]
    assert "Led the engineering team" in texts
    assert "Shipped a JSON-schema-validated ingestion layer" in texts


def test_iter_canonical_entries_walks_skills_keywords() -> None:
    entries = iter_canonical_entries(_cv())
    texts = [e.text for e in entries]
    assert "Python" in texts
    assert "FastAPI" in texts
    assert "pytest" in texts


def test_iter_canonical_entries_walks_projects_name_and_highlights() -> None:
    entries = iter_canonical_entries(_cv())
    texts = [e.text for e in entries]
    assert "jobhunter" in texts
    assert "Walking-skeleton-first delivery" in texts


def test_iter_canonical_entries_walks_education_concatenated_label() -> None:
    entries = iter_canonical_entries(_cv())
    texts = [e.text for e in entries]
    assert "Bachelor Computer Science University Sample" in texts


def test_iter_canonical_entries_walks_work_position_plus_name_for_role_claims() -> None:
    entries = iter_canonical_entries(_cv())
    texts = [e.text for e in entries]
    # The "Senior Engineer at Acme" pattern lets exact-string matches against
    # role claims succeed without falling back to substring (AC5).
    assert "Senior Engineer at Acme" in texts


def test_iter_canonical_entries_ids_are_deterministic_across_calls() -> None:
    a = iter_canonical_entries(_cv())
    b = iter_canonical_entries(_cv())
    assert [e.entry_id for e in a] == [e.entry_id for e in b]


def test_iter_canonical_entries_id_shape_carries_section_and_hash() -> None:
    entries = iter_canonical_entries(_cv())
    entry = next(e for e in entries if e.text == "Python")
    assert entry.entry_id.startswith("skills[")
    assert entry.entry_id.endswith(entry.entry_id.split(":")[-1])
    assert len(entry.entry_id.split(":")[-1]) == 8


def test_iter_canonical_entries_skips_empty_strings_and_non_dicts() -> None:
    cv = {
        "work": [
            None,  # not a dict
            {"highlights": ["", "Real entry"]},
        ],
        "skills": [{"keywords": ["", "Go"]}],
        "projects": [{"name": "", "highlights": [""]}],
        "education": [{"area": ""}],
    }
    entries = iter_canonical_entries(cv)
    texts = [e.text for e in entries]
    assert "Real entry" in texts
    assert "Go" in texts
    assert "" not in texts


# ---- AC2.1: exact_string match -------------------------------------------


def test_exact_string_match_case_insensitive_recorded_with_score_1_0() -> None:
    check = run_matcher([_claim("python")], _cv())
    assert check.verdict == "pass"
    assert len(check.traces) == 1
    assert check.traces[0].match_method == "exact_string"
    assert check.traces[0].match_score == 1.0


def test_exact_string_match_preserves_original_claim_text() -> None:
    check = run_matcher([_claim("PYTHON")], _cv())
    assert check.traces[0].claim_text == "PYTHON"


# ---- AC2.2: substring match ----------------------------------------------


def test_substring_claim_within_canonical_entry_records_substring_match() -> None:
    # Canonical highlight: "Led the engineering team"; claim is a substring.
    check = run_matcher([_claim("engineering team")], _cv())
    assert check.verdict == "pass"
    assert check.traces[0].match_method == "substring"
    assert check.traces[0].match_score == 1.0


def test_substring_canonical_within_claim_records_substring_match() -> None:
    # Canonical keyword: "Python"; claim is the longer string that contains it.
    check = run_matcher([_claim("hands-on Python developer")], _cv())
    assert check.traces[0].match_method == "substring"


def test_substring_match_is_case_insensitive() -> None:
    check = run_matcher([_claim("ENGINEERING team")], _cv())
    assert check.traces[0].match_method == "substring"


def test_exact_wins_over_substring_for_ordering_when_both_could_match() -> None:
    """A claim equal (case-insensitive) to a canonical entry records exact,
    not substring, even though substring would also match."""
    check = run_matcher([_claim("Python")], _cv())
    assert check.traces[0].match_method == "exact_string"


# ---- AC2.3: semantic step handoff ----------------------------------------


def test_semantic_step_is_invoked_only_when_exact_and_substring_fail() -> None:
    calls: list[Claim] = []

    def fake_step(claim, candidates):
        calls.append(claim)
        return None

    check = run_matcher(
        [_claim("Python"), _claim("zebra striping in CSS")],
        _cv(),
        semantic_step=fake_step,
    )
    # "Python" matches exact; only "zebra ..." reaches the semantic step.
    assert len(calls) == 1
    assert calls[0].claim_text == "zebra striping in CSS"
    assert check.verdict == "fail"


def test_semantic_step_returning_trace_marks_claim_sourced() -> None:
    def fake_step(claim, candidates):
        return Trace(
            claim_id=claim.claim_id,
            claim_text=claim.claim_text,
            matched_canonical_entry_id="synthetic:00000000",
            match_method="semantic",
            match_score=0.91,
        )

    check = run_matcher(
        [_claim("ran a 12-person guild")],
        _cv(),
        semantic_step=fake_step,
    )
    assert check.verdict == "pass"
    assert check.traces[0].match_method == "semantic"
    assert check.traces[0].match_score == 0.91


def test_default_semantic_step_is_no_match() -> None:
    """v1 default: a claim that fails exact and substring is unsourced even
    without a semantic step injected (Story 3.3 replaces this default)."""
    check = run_matcher([_claim("invented metric: 500% growth")], _cv())
    assert check.verdict == "fail"
    assert check.unsourced_claims[0].reason == "no_canonical_match"


# ---- AC3: pass/fail logic + counts ---------------------------------------


def test_pass_when_every_claim_is_sourced() -> None:
    claims = [_claim("Python"), _claim("engineering team")]
    check = run_matcher(claims, _cv())
    assert check.verdict == "pass"
    assert check.claims_total == 2
    assert check.claims_sourced == 2
    assert check.claims_unsourced == 0
    assert check.unsourced_claims == []


def test_fail_when_any_claim_is_unsourced() -> None:
    claims = [_claim("Python"), _claim("invented metric: 500% growth")]
    check = run_matcher(claims, _cv())
    assert check.verdict == "fail"
    assert check.claims_total == 2
    assert check.claims_sourced == 1
    assert check.claims_unsourced == 1
    assert len(check.unsourced_claims) == 1


def test_empty_claims_list_is_a_pass() -> None:
    """No claims to source -> nothing fabricated -> pass."""
    check = run_matcher([], _cv())
    assert check.verdict == "pass"
    assert check.claims_total == 0


def test_unsourced_claim_carries_source_artifact_and_line_number() -> None:
    """AC3 / FR24: the unsourced entry pins the claim location."""
    claim = _claim(
        "fictional acme bullet",
        source="cover_letter",
        line=42,
        claim_type="accomplishment",
    )
    check = run_matcher([claim], _cv())
    assert check.unsourced_claims[0].source_artifact == "cover_letter"
    assert check.unsourced_claims[0].line_number == 42
    assert check.unsourced_claims[0].reason == "no_canonical_match"


# ---- AC1: drift-report shape on disk -------------------------------------


def test_write_drift_report_serializes_fabrication_check_under_top_level_key(
    tmp_path: Path,
) -> None:
    """The drift document is a top-level dict so future Epic 4/5 sibling keys
    fit without disturbing the fabrication block."""
    check = run_matcher([_claim("Python")], _cv())
    out = tmp_path / "out"
    out.mkdir()
    target = write_drift_report(out, check)

    assert target == out / "package.drift.json"
    doc = json.loads(target.read_text(encoding="utf-8"))
    assert "fabrication_check" in doc
    assert doc["fabrication_check"]["verdict"] == "pass"
    assert doc["fabrication_check"]["claims_total"] == 1
    assert isinstance(doc["fabrication_check"]["traces"], list)
    assert isinstance(doc["fabrication_check"]["unsourced_claims"], list)


def test_write_drift_report_atomic_no_tmp_after_success(tmp_path: Path) -> None:
    """Atomic write idiom: no `.package.drift.tmp` left on disk."""
    check = run_matcher([_claim("Python")], _cv())
    out = tmp_path / "out"
    out.mkdir()
    write_drift_report(out, check)
    files = {p.name for p in out.iterdir()}
    assert ".package.drift.tmp" not in files
    assert "package.drift.json" in files


def test_drift_report_trace_shape_matches_ac1(tmp_path: Path) -> None:
    """Each trace entry has the documented 6-field shape (AC1 + D2: source_text)."""
    check = run_matcher([_claim("Python")], _cv())
    out = tmp_path / "out"
    out.mkdir()
    write_drift_report(out, check)
    doc = json.loads((out / "package.drift.json").read_text(encoding="utf-8"))
    trace = doc["fabrication_check"]["traces"][0]
    # D2: source_text is the new 6th field carrying the canonical CV original.
    assert set(trace.keys()) == {
        "claim_id",
        "claim_text",
        "matched_canonical_entry_id",
        "match_method",
        "match_score",
        "source_text",
    }


def test_drift_report_unsourced_shape_matches_ac3(tmp_path: Path) -> None:
    """Each unsourced entry has the documented 6-field shape (AC3/FR24 + D2: source_text)."""
    check = run_matcher([_claim("invented acme metric: 500% growth")], _cv())
    out = tmp_path / "out"
    out.mkdir()
    write_drift_report(out, check)
    doc = json.loads((out / "package.drift.json").read_text(encoding="utf-8"))
    unsourced = doc["fabrication_check"]["unsourced_claims"][0]
    # D2: source_text is null for unsourced/fabricated claims (no canonical match).
    assert set(unsourced.keys()) == {
        "claim_id",
        "claim_text",
        "source_artifact",
        "line_number",
        "reason",
        "source_text",
    }
    assert unsourced["source_text"] is None


def test_drift_report_is_diffable_across_runs(tmp_path: Path) -> None:
    """Re-running the matcher on identical input yields byte-identical traces
    (deterministic canonical-entry ids are the load-bearing invariant)."""
    a = run_matcher([_claim("Python")], _cv())
    b = run_matcher([_claim("Python")], _cv())
    assert [t.matched_canonical_entry_id for t in a.traces] == [
        t.matched_canonical_entry_id for t in b.traces
    ]


# ---- empty / boundary inputs ---------------------------------------------


def test_matcher_with_empty_canonical_cv_fails_every_claim() -> None:
    check = run_matcher([_claim("Python")], {})
    assert check.verdict == "fail"
    assert check.claims_sourced == 0


def test_matcher_with_whitespace_only_claim_is_unsourced() -> None:
    check = run_matcher([_claim("   ")], _cv())
    assert check.verdict == "fail"
    assert check.unsourced_claims[0].reason == "no_canonical_match"


# ---- frozen dataclasses --------------------------------------------------


def test_trace_is_frozen() -> None:
    t = Trace(
        claim_id="x", claim_text="y", matched_canonical_entry_id="z",
        match_method="exact_string", match_score=1.0,
    )
    with pytest.raises(Exception):
        t.match_score = 0.5  # type: ignore[misc]


def test_unsourced_claim_is_frozen() -> None:
    u = UnsourcedClaim(
        claim_id="x", claim_text="y", source_artifact="cv",
        line_number=1, reason="r",
    )
    with pytest.raises(Exception):
        u.reason = "other"  # type: ignore[misc]


def test_fabrication_check_is_frozen() -> None:
    c = FabricationCheck(
        verdict="pass", claims_total=0, claims_sourced=0, claims_unsourced=0,
    )
    with pytest.raises(Exception):
        c.verdict = "fail"  # type: ignore[misc]


# ---- D2: source_text on traces + unsourced_claims -------------------------


def test_d2_exact_match_trace_carries_canonical_source_text() -> None:
    """D2: an exact-string matched trace carries the canonical original as source_text."""
    check = run_matcher([_claim("Python")], _cv())
    trace = check.traces[0]
    assert trace.match_method == "exact_string"
    # The canonical entry text is "Python"; source_text must equal that original.
    assert trace.source_text == "Python"


def test_d2_substring_match_trace_carries_canonical_source_text() -> None:
    """D2: a substring-matched trace carries the full canonical entry text as source_text."""
    # "engineering team" is a substring of "Led the engineering team".
    check = run_matcher([_claim("engineering team")], _cv())
    trace = check.traces[0]
    assert trace.match_method == "substring"
    assert trace.source_text == "Led the engineering team"


def test_d2_semantic_match_trace_carries_canonical_source_text() -> None:
    """D2: a semantic-step-matched trace carries the matched canonical text as source_text."""
    semantic_entry_id = "test:00000000"
    canonical_text = "Led the engineering team"

    def fake_step(claim, candidates):
        return Trace(
            claim_id=claim.claim_id,
            claim_text=claim.claim_text,
            matched_canonical_entry_id=semantic_entry_id,
            match_method="semantic",
            match_score=0.87,
            source_text=canonical_text,  # caller must populate D2 field
        )

    check = run_matcher(
        [_claim("managed the engineering pod")],
        _cv(),
        semantic_step=fake_step,
    )
    assert check.traces[0].source_text == canonical_text


def test_d2_unsourced_claim_has_source_text_null() -> None:
    """D2: unsourced (fabricated) claims carry source_text=None."""
    check = run_matcher([_claim("invented 500% growth metric")], _cv())
    assert check.unsourced_claims[0].source_text is None


def test_d2_source_text_survives_round_trip_through_drift_json(tmp_path: Path) -> None:
    """D2: source_text is preserved in package.drift.json for both traces and unsourced."""
    claims = [_claim("Python"), _claim("invented 500% growth metric")]
    check = run_matcher(claims, _cv())
    out = tmp_path / "out"
    out.mkdir()
    write_drift_report(out, check)

    doc = json.loads((out / "package.drift.json").read_text(encoding="utf-8"))
    # Sourced trace: source_text is the canonical original string.
    trace = doc["fabrication_check"]["traces"][0]
    assert trace["source_text"] == "Python"
    # Unsourced claim: source_text is null (JSON null).
    unsourced = doc["fabrication_check"]["unsourced_claims"][0]
    assert unsourced["source_text"] is None


def test_d2_source_text_default_none_on_trace_for_backward_compat() -> None:
    """D2: Trace.source_text defaults to None so callers that build Trace
    manually (e.g. fake semantic_step stubs in older tests) don't break."""
    t = Trace(
        claim_id="x",
        claim_text="y",
        matched_canonical_entry_id="z",
        match_method="exact_string",
        match_score=1.0,
    )
    # source_text defaults to None — additive, backward-compatible.
    assert t.source_text is None
