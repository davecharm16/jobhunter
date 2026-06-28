"""Unit tests for `jobhunter.llm_client`.

The `anthropic` SDK is required to import the module under test. The
suite-wide convention (see test_runtime_config.py for the python-dotenv
parallel) is `pytest.importorskip` so a venv without the SDK still produces
exactly one clear skip per module rather than a wall of import errors.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

pytest.importorskip("anthropic")

import anthropic  # noqa: E402

from jobhunter.llm_client import (  # noqa: E402
    DEFAULT_TIMEOUT_SECONDS,
    INPUT_PRICE_PER_MTOK,
    MODEL_NAME,
    OUTPUT_PRICE_PER_MTOK,
    SYSTEM_PROMPT,
    TAILORING_TOOL,
    LLMCallFailed,
    LLMResponseInvalid,
    TailoringResult,
    _build_user_prompt,
    _compute_cost,
    tailor,
)


class _FakeToolUseBlock:
    type = "tool_use"

    def __init__(self, payload: dict[str, Any]) -> None:
        self.input = payload


class _FakeTextBlock:
    type = "text"

    def __init__(self, text: str) -> None:
        self.text = text


class _FakeUsage:
    def __init__(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _FakeResponse:
    def __init__(self, content: list[Any], usage: _FakeUsage) -> None:
        self.content = content
        self.usage = usage


class _FakeMessages:
    def __init__(self, response: Any, recorder: dict[str, Any]) -> None:
        self._response = response
        self._recorder = recorder

    def create(self, **kwargs: Any) -> Any:
        self._recorder["create_kwargs"] = kwargs
        if isinstance(self._response, BaseException):
            raise self._response
        return self._response


class _FakeClient:
    """Mimics the surface jobhunter.llm_client uses: `client.messages.create()`."""

    instances: list[_FakeClient] = []

    def __init__(self, *, api_key: str, timeout: float, response: Any) -> None:
        self.api_key = api_key
        self.timeout = timeout
        self.recorder: dict[str, Any] = {}
        self.messages = _FakeMessages(response, self.recorder)
        _FakeClient.instances.append(self)


def _factory(response: Any):
    def make(*, api_key: str, timeout: float) -> _FakeClient:
        return _FakeClient(api_key=api_key, timeout=timeout, response=response)

    return make


def _happy_response() -> _FakeResponse:
    return _FakeResponse(
        content=[
            _FakeToolUseBlock(
                {
                    "cv_markdown": "# CV\n",
                    "cover_letter_markdown": "Dear team,\n\nHi.\n",
                }
            )
        ],
        usage=_FakeUsage(input_tokens=1234, output_tokens=567),
    )


def test_compute_cost_matches_pricing_constants() -> None:
    # 1,000,000 input tokens @ $1 + 500,000 output tokens @ $5 = $1 + $2.50 = $3.50
    cost = _compute_cost(input_tokens=1_000_000, output_tokens=500_000)
    expected = (
        Decimal("1000000") * INPUT_PRICE_PER_MTOK / Decimal("1000000")
        + Decimal("500000") * OUTPUT_PRICE_PER_MTOK / Decimal("1000000")
    ).quantize(Decimal("0.000001"))
    assert cost == expected
    assert cost == Decimal("3.500000")


def test_compute_cost_quantizes_to_six_decimal_places() -> None:
    cost = _compute_cost(input_tokens=1234, output_tokens=567)
    # Six decimal places => exponent -6.
    assert cost.as_tuple().exponent == -6


def test_build_user_prompt_contains_canonical_cv_json_and_jd_text() -> None:
    cv = {"basics": {"name": "Test User"}}
    prompt = _build_user_prompt(cv, "Senior Python role at Acme")
    assert '"name": "Test User"' in prompt
    assert "Senior Python role at Acme" in prompt
    assert "Canonical CV" in prompt
    assert "Job Description" in prompt


def test_tailor_returns_validated_result_on_happy_path() -> None:
    cv = {"basics": {"name": "X"}}
    result = tailor(
        cv,
        "Senior Python role",
        api_key="test-key",
        timeout_seconds=12.5,
        client_factory=_factory(_happy_response()),
    )
    assert isinstance(result, TailoringResult)
    assert result.cv_markdown == "# CV\n"
    assert result.cover_letter_markdown.startswith("Dear team,")
    assert result.input_tokens == 1234
    assert result.output_tokens == 567
    # cost = 1234 * 1 / 1e6 + 567 * 5 / 1e6 = 0.001234 + 0.002835 = 0.004069
    assert result.cost_usd == Decimal("0.004069")


def test_tailor_passes_timeout_kwarg_to_client_constructor() -> None:
    _FakeClient.instances.clear()
    tailor(
        {},
        "JD",
        api_key="k",
        timeout_seconds=3.5,
        client_factory=_factory(_happy_response()),
    )
    assert _FakeClient.instances[-1].timeout == 3.5
    assert _FakeClient.instances[-1].api_key == "k"


def test_tailor_uses_default_timeout_when_not_provided() -> None:
    _FakeClient.instances.clear()
    tailor(
        {},
        "JD",
        api_key="k",
        client_factory=_factory(_happy_response()),
    )
    assert _FakeClient.instances[-1].timeout == DEFAULT_TIMEOUT_SECONDS


def test_tailor_uses_pinned_model_and_tool_choice() -> None:
    _FakeClient.instances.clear()
    tailor(
        {},
        "JD",
        api_key="k",
        client_factory=_factory(_happy_response()),
    )
    kwargs = _FakeClient.instances[-1].recorder["create_kwargs"]
    assert kwargs["model"] == MODEL_NAME
    assert kwargs["system"] == SYSTEM_PROMPT
    assert kwargs["tools"] == [TAILORING_TOOL]
    assert kwargs["tool_choice"] == {
        "type": "tool",
        "name": "emit_tailored_artifacts",
    }


def test_tailor_raises_response_invalid_when_cv_markdown_missing() -> None:
    response = _FakeResponse(
        content=[
            _FakeToolUseBlock({"cover_letter_markdown": "Hi\n"}),
        ],
        usage=_FakeUsage(10, 5),
    )
    with pytest.raises(LLMResponseInvalid, match="cv_markdown missing"):
        tailor({}, "JD", api_key="k", client_factory=_factory(response))


def test_tailor_raises_response_invalid_when_cover_letter_empty() -> None:
    response = _FakeResponse(
        content=[
            _FakeToolUseBlock(
                {"cv_markdown": "# CV\n", "cover_letter_markdown": "   "}
            ),
        ],
        usage=_FakeUsage(10, 5),
    )
    with pytest.raises(LLMResponseInvalid, match="cover_letter_markdown"):
        tailor({}, "JD", api_key="k", client_factory=_factory(response))


def test_tailor_raises_response_invalid_when_cover_letter_missing() -> None:
    """AC6: missing `cover_letter_markdown` field (not just empty) is rejected."""
    response = _FakeResponse(
        content=[_FakeToolUseBlock({"cv_markdown": "# CV\n"})],
        usage=_FakeUsage(10, 5),
    )
    with pytest.raises(LLMResponseInvalid, match="cover_letter_markdown"):
        tailor({}, "JD", api_key="k", client_factory=_factory(response))


def test_tailor_raises_response_invalid_when_cv_markdown_empty() -> None:
    """AC6: empty/whitespace `cv_markdown` (symmetric to cover_letter check)."""
    response = _FakeResponse(
        content=[
            _FakeToolUseBlock(
                {"cv_markdown": "   \n\t", "cover_letter_markdown": "Dear team\n"}
            ),
        ],
        usage=_FakeUsage(10, 5),
    )
    with pytest.raises(LLMResponseInvalid, match="cv_markdown"):
        tailor({}, "JD", api_key="k", client_factory=_factory(response))


def test_tailor_raises_response_invalid_when_cv_markdown_is_not_a_string() -> None:
    """AC6: non-string `cv_markdown` is rejected (schema requires string type)."""
    response = _FakeResponse(
        content=[
            _FakeToolUseBlock(
                {"cv_markdown": 12345, "cover_letter_markdown": "Hi\n"}
            ),
        ],
        usage=_FakeUsage(10, 5),
    )
    with pytest.raises(LLMResponseInvalid, match="cv_markdown"):
        tailor({}, "JD", api_key="k", client_factory=_factory(response))


def test_tailor_raises_response_invalid_when_no_tool_use_block() -> None:
    response = _FakeResponse(
        content=[_FakeTextBlock("free-form prose, no tool call")],
        usage=_FakeUsage(10, 5),
    )
    with pytest.raises(LLMResponseInvalid, match="tool_use"):
        tailor({}, "JD", api_key="k", client_factory=_factory(response))


def test_tailor_raises_response_invalid_when_usage_missing() -> None:
    """Review pass: a response without `usage` must raise `LLMResponseInvalid`,
    not silently record a $0 call. Without this guard, a buggy or
    misconfigured SDK response would defeat the monthly cap because every
    call would accumulate $0 — repeated forever.
    """

    class _ResponseNoUsage:
        content = [
            _FakeToolUseBlock(
                {"cv_markdown": "# CV\n", "cover_letter_markdown": "Hi\n"}
            )
        ]
        usage = None

    with pytest.raises(LLMResponseInvalid, match="usage missing"):
        tailor(
            {}, "JD", api_key="k", client_factory=_factory(_ResponseNoUsage())
        )


def test_tailor_raises_response_invalid_when_usage_missing_token_fields() -> None:
    """Review pass: `usage` present but missing `input_tokens`/`output_tokens`
    must also raise, for the same cap-accounting reason as the absent-usage
    case.
    """

    class _PartialUsage:
        input_tokens = 100
        # output_tokens deliberately omitted.

    response = _FakeResponse(
        content=[
            _FakeToolUseBlock(
                {"cv_markdown": "# CV\n", "cover_letter_markdown": "Hi\n"}
            )
        ],
        usage=_PartialUsage(),
    )
    with pytest.raises(LLMResponseInvalid, match="output_tokens"):
        tailor({}, "JD", api_key="k", client_factory=_factory(response))


def test_tailor_wraps_timeout_error_as_call_failed() -> None:
    exc = anthropic.APITimeoutError(request=None)  # type: ignore[arg-type]
    with pytest.raises(LLMCallFailed, match="timeout"):
        tailor({}, "JD", api_key="k", client_factory=_factory(exc))


def test_tailor_wraps_unexpected_error_as_call_failed() -> None:
    exc = RuntimeError("kaboom")
    with pytest.raises(LLMCallFailed, match="unexpected error"):
        tailor({}, "JD", api_key="k", client_factory=_factory(exc))


def test_system_prompt_is_stable_string() -> None:
    """Snapshot test: prompt text is a module-level constant so a casual
    refactor cannot silently move it inside the function body."""
    assert isinstance(SYSTEM_PROMPT, str)
    assert "tailors" in SYSTEM_PROMPT
    assert "emit_tailored_artifacts" in SYSTEM_PROMPT
