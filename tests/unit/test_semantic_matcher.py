"""Unit tests for `jobhunter.semantic_matcher` (Story 3.3 AC1-AC4).

Pure-function assertions on the rule-based scorer, the quantifier guard,
and the `make_semantic_step` factory. Mirrors `test_fabrication_matcher.py`
patterns: frozen dataclasses, deterministic ids, no LLM seam to stub
(`embedding_cosine` is asserted to raise rather than mocked).
"""

from __future__ import annotations

import pytest

from jobhunter.claim_extractor import Claim
from jobhunter.fabrication_matcher import CanonicalEntry
from jobhunter.semantic_matcher import (
    SemanticMatch,
    detect_quantifier_mismatch,
    embedding_cosine_similarity,
    make_semantic_step,
    rule_based_similarity,
)

# ---- helpers --------------------------------------------------------------


def _claim(text: str, *, claim_id: str = "cv:1:abc12345") -> Claim:
    return Claim(
        claim_id=claim_id,
        claim_type="accomplishment",
        claim_text=text,
        source_artifact="cv",
        line_number=1,
    )


def _entry(text: str, *, section: str = "work[0].highlights[0]") -> CanonicalEntry:
    return CanonicalEntry(entry_id=f"{section}:deadbeef", section=section, text=text)


# ---- AC1: rule_based_similarity ------------------------------------------


def test_rule_based_similarity_identical_text_scores_one() -> None:
    assert rule_based_similarity("led the team", "led the team") == 1.0


def test_rule_based_similarity_disjoint_text_scores_zero() -> None:
    assert rule_based_similarity("Python", "FastAPI") == 0.0


def test_rule_based_similarity_empty_inputs_scores_zero() -> None:
    """Empty / stopword-only inputs short-circuit to 0 (no spurious 1.0)."""
    assert rule_based_similarity("", "led the team") == 0.0
    assert rule_based_similarity("a the", "and or") == 0.0


def test_rule_based_similarity_honest_paraphrase_passes_default_threshold() -> None:
    """Spec fixture pair: "led the engineering team" -> "led the team"
    scores above the 0.65 default rule_based threshold (honest paraphrase)."""
    score = rule_based_similarity("led the engineering team", "led the team")
    assert score >= 0.65


def test_rule_based_similarity_embellishment_above_threshold() -> None:
    """Spec fixture pair: "led a 3-person engineering team" vs "led the
    engineering team" scores above threshold — the quantifier guard must
    catch this case (AC3), not the threshold (AC2)."""
    score = rule_based_similarity(
        "led a 3-person engineering team", "led the engineering team"
    )
    assert score >= 0.65


def test_rule_based_similarity_is_symmetric() -> None:
    a = rule_based_similarity("led the team", "engineering team")
    b = rule_based_similarity("engineering team", "led the team")
    assert a == b


def test_rule_based_similarity_stems_common_suffixes() -> None:
    """The in-house stemmer collapses `shipping` and `shipped` so paraphrase
    that only differs in tense still matches."""
    score = rule_based_similarity(
        "shipped a json-schema ingestion layer",
        "shipping a json-schema ingestion layer",
    )
    assert score == 1.0


# ---- AC1: embedding_cosine_similarity not wired in v1 --------------------


def test_embedding_cosine_similarity_raises_not_implemented() -> None:
    """v1 deviation: Anthropic does not expose an embeddings endpoint, so
    the configurable `embedding_cosine` path raises with a message naming
    the upgrade path."""
    with pytest.raises(NotImplementedError) as exc:
        embedding_cosine_similarity("a", "b", api_key="anything")
    msg = str(exc.value)
    assert "embedding_cosine" in msg
    assert "v1" in msg
    assert "_bmad-output/decisions/llm-provider.md" in msg


# ---- AC3: quantifier guard -----------------------------------------------


def test_detect_quantifier_mismatch_catches_team_size() -> None:
    """The spec's load-bearing case: a `3-person` quantifier in the claim
    that does not appear in the canonical text returns the offending
    token verbatim."""
    offending = detect_quantifier_mismatch(
        "led a 3-person engineering team", "led the engineering team"
    )
    assert offending == "3-person"


def test_detect_quantifier_mismatch_catches_percentage() -> None:
    assert (
        detect_quantifier_mismatch("reduced latency by 99%", "reduced latency")
        == "99%"
    )


def test_detect_quantifier_mismatch_catches_dollar_amount() -> None:
    assert (
        detect_quantifier_mismatch("saved $5000 a month", "saved money each month")
        == "$5000"
    )


def test_detect_quantifier_mismatch_catches_multiplier() -> None:
    assert (
        detect_quantifier_mismatch("delivered 10x throughput", "delivered throughput")
        == "10x"
    )


def test_detect_quantifier_mismatch_catches_years() -> None:
    assert (
        detect_quantifier_mismatch("5 years of Python", "Python experience")
        == "5 years"
    )


def test_detect_quantifier_mismatch_returns_none_when_quantifier_in_source() -> None:
    """If the quantifier appears verbatim in the canonical text, the guard
    passes — sourcing is honest, not embellished."""
    assert (
        detect_quantifier_mismatch(
            "led a 3-person team", "successfully led a 3-person team for two years"
        )
        is None
    )


def test_detect_quantifier_mismatch_returns_none_when_no_quantifier() -> None:
    """Claims with no numeric quantifier pass through unconditionally."""
    assert detect_quantifier_mismatch("led the team", "led the engineering team") is None


def test_detect_quantifier_mismatch_empty_claim_returns_none() -> None:
    assert detect_quantifier_mismatch("", "anything") is None


# ---- make_semantic_step: AC1 method selection ----------------------------


def test_make_semantic_step_unknown_method_raises_value_error() -> None:
    with pytest.raises(ValueError) as exc:
        make_semantic_step("magic", 0.65)
    assert "magic" in str(exc.value)
    assert "rule_based" in str(exc.value)


def test_make_semantic_step_embedding_cosine_method_defers_error_to_call() -> None:
    """Factory accepts `embedding_cosine` but the `NotImplementedError`
    surfaces only when the step is actually invoked (so a misconfigured
    `config.yaml` is caught at scoring time, not at startup)."""
    step = make_semantic_step("embedding_cosine", 0.82, api_key="test-key")
    with pytest.raises(NotImplementedError):
        step(_claim("any"), [_entry("any")])


# ---- make_semantic_step: AC2 above/below threshold ----------------------


def test_semantic_step_above_threshold_returns_trace_with_semantic_method() -> None:
    step = make_semantic_step("rule_based", 0.65)
    trace = step(
        _claim("led the engineering team"),
        [_entry("led the team")],
    )
    assert trace is not None
    assert trace.match_method == "semantic"
    assert trace.claim_id == "cv:1:abc12345"
    assert trace.match_score >= 0.65


def test_semantic_step_below_threshold_returns_none() -> None:
    step = make_semantic_step("rule_based", 0.65)
    trace = step(
        _claim("Python"),
        [_entry("FastAPI"), _entry("Docker")],
    )
    assert trace is None


def test_semantic_step_records_below_threshold_reason_when_collector_given() -> None:
    """AC2 reason format: `semantic_below_threshold (score=<x>, threshold=<y>)`."""
    reasons: dict[str, str] = {}
    step = make_semantic_step("rule_based", 0.65, rejection_reasons=reasons)
    step(_claim("Python"), [_entry("FastAPI")])
    assert "cv:1:abc12345" in reasons
    reason = reasons["cv:1:abc12345"]
    assert reason.startswith("semantic_below_threshold (")
    assert "score=" in reason
    assert "threshold=0.6500" in reason


def test_semantic_step_no_candidates_returns_none() -> None:
    step = make_semantic_step("rule_based", 0.65)
    assert step(_claim("anything"), []) is None


def test_semantic_step_match_score_rounded_to_four_decimals() -> None:
    step = make_semantic_step("rule_based", 0.0)
    trace = step(
        _claim("led the engineering team"),
        [_entry("led the team")],
    )
    assert trace is not None
    # `match_score` is a float rounded to 4 decimals so the drift report
    # stays diffable across runs.
    assert round(trace.match_score, 4) == trace.match_score


def test_semantic_step_picks_highest_scoring_candidate() -> None:
    step = make_semantic_step("rule_based", 0.0)
    entries = [
        _entry("FastAPI", section="skills[0].keywords[0]"),
        _entry("led the team", section="work[0].highlights[0]"),
        _entry("PostgreSQL", section="skills[0].keywords[1]"),
    ]
    trace = step(_claim("led the engineering team"), entries)
    assert trace is not None
    assert trace.matched_canonical_entry_id.startswith("work[0].highlights[0]")


# ---- make_semantic_step: AC3 quantifier guard ----------------------------


def test_semantic_step_quantifier_mismatch_overrides_match() -> None:
    """Spec fixture pair: high-similarity match is rejected when the claim
    introduces a quantifier (`3-person`) not in the canonical text."""
    reasons: dict[str, str] = {}
    step = make_semantic_step("rule_based", 0.65, rejection_reasons=reasons)
    trace = step(
        _claim("led a 3-person engineering team"),
        [_entry("led the engineering team")],
    )
    assert trace is None
    assert reasons["cv:1:abc12345"] == "quantifier_not_in_source (quantifier=3-person)"


def test_semantic_step_quantifier_in_source_does_not_trigger_guard() -> None:
    """When the canonical text already carries the quantifier, the guard
    stays silent and the semantic match goes through."""
    step = make_semantic_step("rule_based", 0.65)
    trace = step(
        _claim("led a 3-person team"),
        [_entry("led a 3-person engineering team")],
    )
    assert trace is not None
    assert trace.match_method == "semantic"


def test_semantic_step_below_threshold_does_not_run_quantifier_guard() -> None:
    """When semantic similarity is already below threshold the recorded
    reason is `semantic_below_threshold`, never `quantifier_not_in_source`
    — the threshold gate runs first (AC2 before AC3)."""
    reasons: dict[str, str] = {}
    step = make_semantic_step("rule_based", 0.65, rejection_reasons=reasons)
    step(
        _claim("a brand-new 3-person team"),
        [_entry("Python")],
    )
    assert reasons["cv:1:abc12345"].startswith("semantic_below_threshold (")


# ---- SemanticMatch dataclass --------------------------------------------


def test_semantic_match_is_frozen() -> None:
    match = SemanticMatch(canonical_entry_id="x:1", score=0.9)
    with pytest.raises(Exception):
        match.score = 0.5  # type: ignore[misc]
