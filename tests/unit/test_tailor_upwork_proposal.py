"""Unit tests for `jobhunter.llm_client.tailor_upwork_proposal` (Story 2.7).

The `anthropic` SDK is required to import the module under test. The
suite-wide convention is `pytest.importorskip` so a venv without the SDK
still produces exactly one clear skip per module.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("anthropic")

import anthropic  # noqa: E402

from jobhunter.llm_client import (  # noqa: E402
    MODEL_NAME,
    UPWORK_PROPOSAL_SYSTEM_PROMPT,
    UPWORK_PROPOSAL_TOOL,
    LLMCallFailed,
    LLMResponseInvalid,
    UpworkProposalOverLength,
    UpworkProposalResult,
    count_words,
    tailor_upwork_proposal,
)
from jobhunter.prompts import PromptTemplate


class _FakeToolUseBlock:
    type = "tool_use"

    def __init__(self, payload: dict[str, Any]) -> None:
        self.input = payload


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
                    "proposal_markdown": (
                        "I read your job description and I have built similar "
                        "Python systems.\n"
                    ),
                }
            )
        ],
        usage=_FakeUsage(input_tokens=900, output_tokens=300),
    )


# --- Happy path -----------------------------------------------------------


def test_tailor_upwork_proposal_returns_validated_result() -> None:
    result = tailor_upwork_proposal(
        {"basics": {"name": "X"}},
        "Senior Python role on upwork.com",
        api_key="test-key",
        timeout_seconds=12.5,
        client_factory=_factory(_happy_response()),
        max_words=250,
    )
    assert isinstance(result, UpworkProposalResult)
    assert "Python" in result.proposal_markdown
    assert result.input_tokens == 900
    assert result.output_tokens == 300
    # cost = 900 * 1 / 1e6 + 300 * 5 / 1e6 = 0.0009 + 0.0015 = 0.0024
    assert result.cost_usd == Decimal("0.002400")


def test_tailor_upwork_proposal_uses_pinned_model_and_tool_choice() -> None:
    _FakeClient.instances.clear()
    tailor_upwork_proposal(
        {},
        "JD",
        api_key="k",
        client_factory=_factory(_happy_response()),
        max_words=250,
    )
    kwargs = _FakeClient.instances[-1].recorder["create_kwargs"]
    assert kwargs["model"] == MODEL_NAME
    assert kwargs["system"] == UPWORK_PROPOSAL_SYSTEM_PROMPT
    assert kwargs["tools"] == [UPWORK_PROPOSAL_TOOL]
    assert kwargs["tool_choice"] == {
        "type": "tool",
        "name": "emit_upwork_proposal",
    }


def test_tailor_upwork_proposal_user_prompt_carries_jd_cv_and_questions() -> None:
    _FakeClient.instances.clear()
    tailor_upwork_proposal(
        {"basics": {"name": "Ada"}},
        "Need a Python developer on upwork.com",
        api_key="k",
        client_factory=_factory(_happy_response()),
        screening_questions=["How many years of Python?", "Earliest start?"],
        max_words=200,
    )
    user_prompt = _FakeClient.instances[-1].recorder["create_kwargs"]["messages"][0][
        "content"
    ]
    assert '"name": "Ada"' in user_prompt
    assert "Need a Python developer" in user_prompt
    assert "How many years of Python?" in user_prompt
    assert "Earliest start?" in user_prompt
    assert "200 words maximum" in user_prompt


def test_tailor_upwork_proposal_user_prompt_handles_no_screening_questions() -> None:
    _FakeClient.instances.clear()
    tailor_upwork_proposal(
        {},
        "JD",
        api_key="k",
        client_factory=_factory(_happy_response()),
        max_words=100,
    )
    user_prompt = _FakeClient.instances[-1].recorder["create_kwargs"]["messages"][0][
        "content"
    ]
    assert "(none)" in user_prompt


def test_tailor_upwork_proposal_uses_prompt_template_content_when_provided() -> None:
    _FakeClient.instances.clear()
    template = PromptTemplate(
        name="upwork_proposal",
        version="v9",
        content="CUSTOM UPWORK PROPOSAL SYSTEM PROMPT v9",
        path=Path("/tmp/upwork_proposal.v9.md"),
    )
    tailor_upwork_proposal(
        {},
        "JD",
        api_key="k",
        client_factory=_factory(_happy_response()),
        prompt=template,
        max_words=200,
    )
    kwargs = _FakeClient.instances[-1].recorder["create_kwargs"]
    assert kwargs["system"] == "CUSTOM UPWORK PROPOSAL SYSTEM PROMPT v9"


# --- Failure modes --------------------------------------------------------


def test_tailor_upwork_proposal_raises_when_proposal_markdown_missing() -> None:
    response = _FakeResponse(
        content=[_FakeToolUseBlock({})],
        usage=_FakeUsage(10, 5),
    )
    with pytest.raises(LLMResponseInvalid, match="proposal_markdown missing"):
        tailor_upwork_proposal(
            {},
            "JD",
            api_key="k",
            client_factory=_factory(response),
            max_words=250,
        )


def test_tailor_upwork_proposal_raises_when_proposal_markdown_empty() -> None:
    response = _FakeResponse(
        content=[_FakeToolUseBlock({"proposal_markdown": "  \n\t"})],
        usage=_FakeUsage(10, 5),
    )
    with pytest.raises(LLMResponseInvalid, match="proposal_markdown"):
        tailor_upwork_proposal(
            {},
            "JD",
            api_key="k",
            client_factory=_factory(response),
            max_words=250,
        )


def test_tailor_upwork_proposal_raises_when_usage_missing() -> None:
    class _NoUsage:
        content = [_FakeToolUseBlock({"proposal_markdown": "Hi\n"})]
        usage = None

    with pytest.raises(LLMResponseInvalid, match="usage missing"):
        tailor_upwork_proposal(
            {},
            "JD",
            api_key="k",
            client_factory=_factory(_NoUsage()),
            max_words=250,
        )


def test_tailor_upwork_proposal_wraps_timeout_as_call_failed() -> None:
    exc = anthropic.APITimeoutError(request=None)  # type: ignore[arg-type]
    with pytest.raises(LLMCallFailed, match="timeout"):
        tailor_upwork_proposal(
            {},
            "JD",
            api_key="k",
            client_factory=_factory(exc),
            max_words=250,
        )


# --- Constants stability snapshot ------------------------------------------


def test_upwork_proposal_system_prompt_is_stable_string() -> None:
    assert isinstance(UPWORK_PROPOSAL_SYSTEM_PROMPT, str)
    assert "Upwork" in UPWORK_PROPOSAL_SYSTEM_PROMPT
    assert "emit_upwork_proposal" in UPWORK_PROPOSAL_SYSTEM_PROMPT


def test_upwork_proposal_tool_schema_requires_proposal_markdown() -> None:
    schema = UPWORK_PROPOSAL_TOOL["input_schema"]
    assert schema["required"] == ["proposal_markdown"]
    assert schema["properties"]["proposal_markdown"]["type"] == "string"


# --- count_words helper ---------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("", 0),
        ("hello", 1),
        ("hello world", 2),
        ("  hello   world  \n", 2),
        ("one two three four five", 5),
        # Markdown markers count as whitespace-delimited tokens — this is the
        # conservative-cutting bias the prompt also asks the LLM to honor.
        ("# Heading\n\n- bullet one\n- bullet two\n", 8),
    ],
)
def test_count_words(text: str, expected: int) -> None:
    assert count_words(text) == expected


# --- UpworkProposalOverLength sanity ---------------------------------------


def test_overlength_exception_carries_counts() -> None:
    exc = UpworkProposalOverLength(word_count=312, max_words=250)
    assert exc.word_count == 312
    assert exc.max_words == 250
    assert "312" in str(exc)
    assert "250" in str(exc)
