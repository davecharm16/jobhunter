"""Unit tests for `jobhunter.claim_extractor` (Story 3.1 AC2-AC4).

Mirrors `test_llm_client.py` and `test_jd_parser.py` patterns: in-memory
stubs for the LLM call, deterministic assertions on the parsed output,
exception-class hierarchy checks so the orchestrator's `except` clauses
fire in the right order.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

pytest.importorskip("anthropic")

from jobhunter.claim_extractor import (  # noqa: E402
    ALLOWED_CLAIM_TYPES,
    Claim,
    ClaimExtractionInvalid,
    ClaimExtractionResult,
    ClaimExtractionTimedOut,
    _make_claim_id,
    extract_claims_from_markdown,
)
from jobhunter.llm_client import (  # noqa: E402
    ExtractClaimsResult,
    LLMCallFailed,
    LLMCallTimedOut,
    LLMResponseInvalid,
)
from jobhunter.prompts import PromptTemplate  # noqa: E402


# ---- helpers -------------------------------------------------------------


def _prompt() -> PromptTemplate:
    return PromptTemplate(
        name="claims_extract",
        version="v1",
        content="extract atomic claims\n",
        path=type("P", (), {"__fspath__": lambda self: "<test>"})(),  # type: ignore[arg-type]
    )


def _make_llm_extract(raw_claims, *, cost=Decimal("0.000420")):
    def fake(
        markdown_text, source_artifact, *, api_key, timeout_seconds, prompt,
    ):
        return ExtractClaimsResult(
            claims=list(raw_claims),
            cost_usd=cost,
            input_tokens=42,
            output_tokens=21,
        )

    return fake


# ---- claim_id determinism ------------------------------------------------


def test_claim_id_is_deterministic_for_same_inputs() -> None:
    a = _make_claim_id("cv", 7, "Led the team")
    b = _make_claim_id("cv", 7, "Led the team")
    assert a == b


def test_claim_id_distinguishes_artifact_and_line() -> None:
    base = _make_claim_id("cv", 1, "Led the team")
    assert _make_claim_id("cover_letter", 1, "Led the team") != base
    assert _make_claim_id("cv", 2, "Led the team") != base
    assert _make_claim_id("cv", 1, "Led the team!") != base


def test_claim_id_has_documented_shape() -> None:
    """source_artifact:line_number:<8-char hex>."""
    cid = _make_claim_id("cv", 7, "Led the team")
    parts = cid.split(":")
    assert parts[0] == "cv"
    assert parts[1] == "7"
    assert len(parts[2]) == 8


# ---- happy-path extraction ------------------------------------------------


def test_extract_returns_claims_with_required_fields() -> None:
    raw = [
        {"claim_type": "role", "claim_text": "Senior Engineer at Acme", "line_number": 3},
        {"claim_type": "skill", "claim_text": "Python", "line_number": 7},
        {"claim_type": "metric", "claim_text": "40% faster", "line_number": 7},
    ]
    result = extract_claims_from_markdown(
        "# CV\n\n## Roles\nSenior Engineer at Acme\n\n## Skills\nPython, 40% faster delivery\n",
        "cv",
        api_key="k",
        timeout_seconds=10.0,
        prompt=_prompt(),
        llm_extract=_make_llm_extract(raw),
    )
    assert isinstance(result, ClaimExtractionResult)
    assert len(result.claims) == 3
    for claim in result.claims:
        assert isinstance(claim, Claim)
        assert claim.source_artifact == "cv"
        assert claim.claim_type in ALLOWED_CLAIM_TYPES
        assert claim.claim_text
        assert claim.line_number >= 1
        assert claim.claim_id.startswith("cv:")


def test_extract_passes_cost_usage_through() -> None:
    raw = [{"claim_type": "skill", "claim_text": "Python", "line_number": 1}]
    result = extract_claims_from_markdown(
        "Python\n",
        "cv",
        api_key="k",
        timeout_seconds=10.0,
        prompt=_prompt(),
        llm_extract=_make_llm_extract(raw, cost=Decimal("0.001500")),
    )
    assert result.cost_usd == Decimal("0.001500")
    assert result.input_tokens == 42
    assert result.output_tokens == 21


def test_extract_with_empty_claims_returns_empty_list() -> None:
    """A cover letter that is purely greetings/closings produces no claims."""
    result = extract_claims_from_markdown(
        "Dear hiring manager,\n\nBest regards,\nDave\n",
        "cover_letter",
        api_key="k",
        timeout_seconds=10.0,
        prompt=_prompt(),
        llm_extract=_make_llm_extract([]),
    )
    assert result.claims == []


# ---- determinism: same input -> same claim_ids ---------------------------


def test_extract_produces_diffable_claim_ids_across_runs() -> None:
    """Re-running on the same markdown produces byte-identical claim_ids
    (the hash digest seed is the claim text, so identical input == identical
    output)."""
    raw = [
        {"claim_type": "skill", "claim_text": "Postgres", "line_number": 2},
        {"claim_type": "tool", "claim_text": "FastAPI", "line_number": 3},
    ]
    result_a = extract_claims_from_markdown(
        "X\n",
        "cv",
        api_key="k",
        timeout_seconds=10.0,
        prompt=_prompt(),
        llm_extract=_make_llm_extract(raw),
    )
    result_b = extract_claims_from_markdown(
        "X\n",
        "cv",
        api_key="k",
        timeout_seconds=10.0,
        prompt=_prompt(),
        llm_extract=_make_llm_extract(raw),
    )
    ids_a = [c.claim_id for c in result_a.claims]
    ids_b = [c.claim_id for c in result_b.claims]
    assert ids_a == ids_b


# ---- validation errors ---------------------------------------------------


def test_extract_rejects_unknown_claim_type() -> None:
    raw = [{"claim_type": "vibes", "claim_text": "feels relevant", "line_number": 1}]
    with pytest.raises(ClaimExtractionInvalid, match="claim_type"):
        extract_claims_from_markdown(
            "X\n",
            "cv",
            api_key="k",
            timeout_seconds=10.0,
            prompt=_prompt(),
            llm_extract=_make_llm_extract(raw),
        )


def test_extract_rejects_empty_claim_text() -> None:
    raw = [{"claim_type": "skill", "claim_text": "   ", "line_number": 1}]
    with pytest.raises(ClaimExtractionInvalid, match="claim_text"):
        extract_claims_from_markdown(
            "X\n",
            "cv",
            api_key="k",
            timeout_seconds=10.0,
            prompt=_prompt(),
            llm_extract=_make_llm_extract(raw),
        )


def test_extract_rejects_missing_line_number() -> None:
    raw = [{"claim_type": "skill", "claim_text": "Python"}]
    with pytest.raises(ClaimExtractionInvalid, match="line_number"):
        extract_claims_from_markdown(
            "X\n",
            "cv",
            api_key="k",
            timeout_seconds=10.0,
            prompt=_prompt(),
            llm_extract=_make_llm_extract(raw),
        )


def test_extract_rejects_zero_or_negative_line_number() -> None:
    raw = [{"claim_type": "skill", "claim_text": "Python", "line_number": 0}]
    with pytest.raises(ClaimExtractionInvalid, match="line_number"):
        extract_claims_from_markdown(
            "X\n",
            "cv",
            api_key="k",
            timeout_seconds=10.0,
            prompt=_prompt(),
            llm_extract=_make_llm_extract(raw),
        )


def test_extract_rejects_non_dict_claim_entry() -> None:
    raw = ["not a dict"]
    with pytest.raises(ClaimExtractionInvalid, match="must be an object"):
        extract_claims_from_markdown(
            "X\n",
            "cv",
            api_key="k",
            timeout_seconds=10.0,
            prompt=_prompt(),
            llm_extract=_make_llm_extract(raw),
        )


def test_extract_translates_llm_response_invalid() -> None:
    def boom(*args, **kwargs):
        raise LLMResponseInvalid("usage missing")

    with pytest.raises(ClaimExtractionInvalid, match="usage"):
        extract_claims_from_markdown(
            "X\n",
            "cv",
            api_key="k",
            timeout_seconds=10.0,
            prompt=_prompt(),
            llm_extract=boom,
        )


# ---- timeout class hierarchy ---------------------------------------------


def test_extract_translates_llm_timeout_to_extraction_timeout() -> None:
    def boom(*args, **kwargs):
        raise LLMCallTimedOut("timeout after 60s")

    with pytest.raises(ClaimExtractionTimedOut, match="timeout"):
        extract_claims_from_markdown(
            "X\n",
            "cv",
            api_key="k",
            timeout_seconds=10.0,
            prompt=_prompt(),
            llm_extract=boom,
        )


def test_extraction_timeout_inherits_llm_call_failed() -> None:
    """`ClaimExtractionTimedOut` -> `LLMCallTimedOut` -> `LLMCallFailed` so
    the FastAPI 502 handler in `web/api.py` catches it via the same path
    `ParseTimedOut` uses (Story 2.3 precedent). This is the load-bearing
    wire: without it, the route returns 500 instead of 502."""
    assert issubclass(ClaimExtractionTimedOut, LLMCallTimedOut)
    assert issubclass(ClaimExtractionTimedOut, LLMCallFailed)


# ---- cover-letter atomicity fixture (AC3) --------------------------------


def test_cover_letter_extraction_only_includes_assertions() -> None:
    """AC3 fixture: a cover letter with mixed prose has exactly the
    documented number of atomic claims +/- 1 tolerance. The LLM is stubbed
    here so the test pins the extractor's pass-through contract, not the
    real LLM's classification of non-assertive prose (that lives in
    `tests/integration/test_claims_json_in_pipeline.py` as an end-to-end
    smoke check)."""
    # 4 expected claims (1 role, 2 skills, 1 accomplishment); greetings,
    # closings, and JD restatements are skipped by the prompt.
    raw = [
        {"claim_type": "role", "claim_text": "Senior Engineer at Acme", "line_number": 3},
        {"claim_type": "skill", "claim_text": "Python", "line_number": 5},
        {"claim_type": "skill", "claim_text": "FastAPI", "line_number": 5},
        {"claim_type": "accomplishment", "claim_text": "shipped the v2 API", "line_number": 7},
    ]
    cover_letter = (
        "Dear hiring manager,\n"
        "\n"
        "I am the Senior Engineer at Acme you are looking for.\n"
        "As your posting mentions, you need Python expertise.\n"
        "I work with Python and FastAPI day-to-day.\n"
        "\n"
        "I shipped the v2 API last year.\n"
        "\n"
        "Best regards,\n"
        "Dave\n"
    )
    result = extract_claims_from_markdown(
        cover_letter,
        "cover_letter",
        api_key="k",
        timeout_seconds=10.0,
        prompt=_prompt(),
        llm_extract=_make_llm_extract(raw),
    )
    assert len(result.claims) == 4
    for claim in result.claims:
        assert claim.source_artifact == "cover_letter"


# ---- llm_client.extract_claims wiring ------------------------------------


def test_llm_client_extract_claims_uses_correct_tool() -> None:
    """End-to-end through `llm_client.extract_claims` with a fake SDK client
    confirming the tool-use API shape, model pin, and tool_choice match the
    Story-3.1 contract."""
    import anthropic  # noqa: F401  — pytest.importorskip already gated
    from typing import Any

    from jobhunter.llm_client import (
        CLAIMS_EXTRACT_SYSTEM_PROMPT,
        CLAIMS_EXTRACT_TOOL,
        MODEL_NAME,
        extract_claims,
    )

    class _ToolUse:
        type = "tool_use"

        def __init__(self, payload: dict[str, Any]) -> None:
            self.input = payload

    class _Usage:
        def __init__(self, i: int, o: int) -> None:
            self.input_tokens = i
            self.output_tokens = o

    class _Response:
        def __init__(self) -> None:
            self.content = [
                _ToolUse(
                    {
                        "claims": [
                            {"claim_type": "skill", "claim_text": "Python", "line_number": 1},
                        ]
                    }
                )
            ]
            self.usage = _Usage(100, 50)

    captured: dict[str, Any] = {}

    class _Messages:
        def create(self, **kwargs: Any) -> Any:
            captured["create_kwargs"] = kwargs
            return _Response()

    class _Client:
        def __init__(self, **kwargs: Any) -> None:
            self.messages = _Messages()

    result = extract_claims(
        "# CV\nPython\n",
        "cv",
        api_key="k",
        timeout_seconds=12.0,
        client_factory=_Client,
    )
    assert result.claims == [
        {"claim_type": "skill", "claim_text": "Python", "line_number": 1}
    ]
    assert captured["create_kwargs"]["model"] == MODEL_NAME
    assert captured["create_kwargs"]["system"] == CLAIMS_EXTRACT_SYSTEM_PROMPT
    assert captured["create_kwargs"]["tools"] == [CLAIMS_EXTRACT_TOOL]
    assert captured["create_kwargs"]["tool_choice"] == {
        "type": "tool",
        "name": "emit_claims",
    }


def test_llm_client_extract_claims_costs_match_pricing_constants() -> None:
    """100 input + 50 output tokens => 100/1e6 + 50*5/1e6 = 0.000350."""
    from typing import Any

    from jobhunter.llm_client import extract_claims

    class _ToolUse:
        type = "tool_use"

        def __init__(self, payload: dict[str, Any]) -> None:
            self.input = payload

    class _Usage:
        input_tokens = 100
        output_tokens = 50

    class _Response:
        content = [
            _ToolUse({"claims": [{"claim_type": "skill", "claim_text": "X", "line_number": 1}]})
        ]
        usage = _Usage()

    class _Client:
        def __init__(self, **_: Any) -> None:
            self.messages = type("M", (), {"create": lambda self, **__: _Response()})()

    result = extract_claims(
        "X\n", "cv", api_key="k", timeout_seconds=10.0, client_factory=_Client,
    )
    assert result.cost_usd == Decimal("0.000350")


def test_llm_client_extract_claims_rejects_non_list_claims_field() -> None:
    from typing import Any

    from jobhunter.llm_client import extract_claims

    class _ToolUse:
        type = "tool_use"
        input = {"claims": "not a list"}

    class _Usage:
        input_tokens = 1
        output_tokens = 1

    class _Response:
        content = [_ToolUse()]
        usage = _Usage()

    class _Client:
        def __init__(self, **_: Any) -> None:
            self.messages = type("M", (), {"create": lambda self, **__: _Response()})()

    with pytest.raises(LLMResponseInvalid, match="claims"):
        extract_claims(
            "X\n", "cv", api_key="k", timeout_seconds=10.0, client_factory=_Client,
        )
