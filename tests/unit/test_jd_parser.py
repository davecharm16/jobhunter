"""Unit tests for `jobhunter.jd_parser` (Story 2.3)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("anthropic")

import anthropic  # noqa: E402

from jobhunter.jd_parser import (  # noqa: E402
    ParseTimedOut,
    ParsedJD,
    ParsedJDInvalid,
    parse_jd,
)
from jobhunter.llm_client import (  # noqa: E402
    JD_PARSE_SYSTEM_PROMPT,
    JD_PARSE_TOOL,
    LLMCallFailed,
    LLMCallTimedOut,
    LLMResponseInvalid,
    MODEL_NAME,
    ParseResult,
)
from jobhunter.llm_client import parse_jd as llm_parse_jd  # noqa: E402
from jobhunter.prompts import PromptTemplate  # noqa: E402


def _template(content: str = "parse the JD\n") -> PromptTemplate:
    return PromptTemplate(
        name="jd_parse",
        version="v1",
        content=content,
        path=Path("<test>"),
    )


# --- llm_client.parse_jd: SDK-level fake client ----------------------------


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
    instances: list["_FakeClient"] = []

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
                    "must_haves": ["Python", "FastAPI"],
                    "nice_to_haves": ["Docker"],
                    "tone": "casual",
                    "seniority": "senior",
                    "red_flags": ["vague scope"],
                }
            )
        ],
        usage=_FakeUsage(input_tokens=900, output_tokens=120),
    )


# --- llm_client.parse_jd happy path ---------------------------------------


def test_llm_parse_jd_returns_validated_parse_result() -> None:
    result = llm_parse_jd(
        "Senior Python role.\n",
        api_key="k",
        timeout_seconds=10.0,
        client_factory=_factory(_happy_response()),
    )
    assert isinstance(result, ParseResult)
    assert result.must_haves == ["Python", "FastAPI"]
    assert result.nice_to_haves == ["Docker"]
    assert result.tone == "casual"
    assert result.seniority == "senior"
    assert result.red_flags == ["vague scope"]
    assert result.input_tokens == 900
    assert result.output_tokens == 120


def test_llm_parse_jd_uses_pinned_model_and_tool_choice() -> None:
    _FakeClient.instances.clear()
    llm_parse_jd(
        "JD",
        api_key="k",
        client_factory=_factory(_happy_response()),
    )
    kwargs = _FakeClient.instances[-1].recorder["create_kwargs"]
    assert kwargs["model"] == MODEL_NAME
    assert kwargs["system"] == JD_PARSE_SYSTEM_PROMPT
    assert kwargs["tools"] == [JD_PARSE_TOOL]
    assert kwargs["tool_choice"] == {"type": "tool", "name": "emit_parsed_jd"}


def test_llm_parse_jd_uses_prompt_template_content_when_provided() -> None:
    _FakeClient.instances.clear()
    llm_parse_jd(
        "JD",
        api_key="k",
        prompt=_template("CUSTOM parse prompt\n"),
        client_factory=_factory(_happy_response()),
    )
    kwargs = _FakeClient.instances[-1].recorder["create_kwargs"]
    assert kwargs["system"] == "CUSTOM parse prompt\n"


def test_llm_parse_jd_passes_timeout_to_client_constructor() -> None:
    _FakeClient.instances.clear()
    llm_parse_jd(
        "JD",
        api_key="k",
        timeout_seconds=7.5,
        client_factory=_factory(_happy_response()),
    )
    assert _FakeClient.instances[-1].timeout == 7.5


def test_llm_parse_jd_wraps_timeout_error_as_call_timed_out() -> None:
    exc = anthropic.APITimeoutError(request=None)  # type: ignore[arg-type]
    with pytest.raises(LLMCallTimedOut, match="timeout"):
        llm_parse_jd("JD", api_key="k", client_factory=_factory(exc))


def test_llm_parse_jd_wraps_unexpected_error_as_call_failed() -> None:
    exc = RuntimeError("kaboom")
    with pytest.raises(LLMCallFailed, match="unexpected"):
        llm_parse_jd("JD", api_key="k", client_factory=_factory(exc))


# --- llm_client.parse_jd validation failures ------------------------------


def test_llm_parse_jd_raises_when_must_haves_missing() -> None:
    response = _FakeResponse(
        content=[
            _FakeToolUseBlock(
                {
                    "nice_to_haves": [],
                    "tone": "casual",
                    "seniority": "senior",
                    "red_flags": [],
                }
            )
        ],
        usage=_FakeUsage(10, 5),
    )
    with pytest.raises(LLMResponseInvalid, match="must_haves"):
        llm_parse_jd("JD", api_key="k", client_factory=_factory(response))


def test_llm_parse_jd_raises_when_must_haves_not_a_list() -> None:
    response = _FakeResponse(
        content=[
            _FakeToolUseBlock(
                {
                    "must_haves": "not a list",
                    "nice_to_haves": [],
                    "tone": "casual",
                    "seniority": "senior",
                    "red_flags": [],
                }
            )
        ],
        usage=_FakeUsage(10, 5),
    )
    with pytest.raises(LLMResponseInvalid, match="must_haves"):
        llm_parse_jd("JD", api_key="k", client_factory=_factory(response))


def test_llm_parse_jd_raises_when_tone_empty() -> None:
    response = _FakeResponse(
        content=[
            _FakeToolUseBlock(
                {
                    "must_haves": [],
                    "nice_to_haves": [],
                    "tone": "   ",
                    "seniority": "senior",
                    "red_flags": [],
                }
            )
        ],
        usage=_FakeUsage(10, 5),
    )
    with pytest.raises(LLMResponseInvalid, match="tone"):
        llm_parse_jd("JD", api_key="k", client_factory=_factory(response))


def test_llm_parse_jd_raises_when_usage_missing() -> None:
    class _NoUsage:
        content = [
            _FakeToolUseBlock(
                {
                    "must_haves": [],
                    "nice_to_haves": [],
                    "tone": "casual",
                    "seniority": "senior",
                    "red_flags": [],
                }
            )
        ]
        usage = None

    with pytest.raises(LLMResponseInvalid, match="usage missing"):
        llm_parse_jd("JD", api_key="k", client_factory=_factory(_NoUsage()))


# --- jd_parser.parse_jd wraps llm_client.parse_jd -------------------------


def _fake_parse_result(
    *,
    must_haves: list[str] | None = None,
    nice_to_haves: list[str] | None = None,
    tone: str = "casual",
    seniority: str = "senior",
    red_flags: list[str] | None = None,
) -> ParseResult:
    return ParseResult(
        must_haves=must_haves or ["Python"],
        nice_to_haves=nice_to_haves or ["Docker"],
        tone=tone,
        seniority=seniority,
        red_flags=red_flags or [],
        cost_usd=Decimal("0.001000"),
        input_tokens=100,
        output_tokens=50,
    )


def test_jd_parser_returns_parsed_jd_with_raw_text_length() -> None:
    jd_text = "Senior Python role.\n"

    def fake_parser(jd, *, api_key, timeout_seconds, prompt):
        return _fake_parse_result()

    parsed = parse_jd(
        jd_text,
        api_key="k",
        timeout_seconds=30.0,
        prompt=_template(),
        llm_parse=fake_parser,
    )
    assert isinstance(parsed, ParsedJD)
    assert parsed.raw_text_length == len(jd_text)
    assert parsed.must_haves == ["Python"]
    assert parsed.nice_to_haves == ["Docker"]
    assert parsed.tone == "casual"
    assert parsed.seniority == "senior"
    assert parsed.red_flags == []


def test_jd_parser_translates_timeout_to_parse_timed_out() -> None:
    def boom(*args, **kwargs):
        raise LLMCallTimedOut("timeout after 60s")

    with pytest.raises(ParseTimedOut, match="timeout"):
        parse_jd(
            "JD",
            api_key="k",
            timeout_seconds=60.0,
            prompt=_template(),
            llm_parse=boom,
        )


def test_jd_parser_translates_response_invalid_to_parsed_jd_invalid() -> None:
    def bad(*args, **kwargs):
        raise LLMResponseInvalid("must_haves missing")

    with pytest.raises(ParsedJDInvalid, match="must_haves"):
        parse_jd(
            "JD",
            api_key="k",
            timeout_seconds=60.0,
            prompt=_template(),
            llm_parse=bad,
        )


def test_parse_timed_out_is_a_subclass_of_llm_call_timed_out() -> None:
    """The orchestrator's existing 502 handler catches `LLMCallFailed`; if
    `ParseTimedOut` is in that hierarchy the FastAPI route maps it cleanly
    without changes to api.py.
    """
    assert issubclass(ParseTimedOut, LLMCallTimedOut)
    assert issubclass(ParseTimedOut, LLMCallFailed)


def test_parsed_jd_is_frozen_dataclass() -> None:
    parsed = ParsedJD(
        must_haves=["x"],
        nice_to_haves=[],
        tone="casual",
        seniority="senior",
        red_flags=[],
        raw_text_length=10,
    )
    with pytest.raises(Exception):
        parsed.tone = "formal"  # type: ignore[misc]


# --- D1: ParsedJD job_title + company_name optional fields ---------------


def test_parsed_jd_job_title_and_company_name_default_to_none() -> None:
    """D1: ParsedJD accepts the new fields and defaults them to None."""
    parsed = ParsedJD(
        must_haves=["Python"],
        nice_to_haves=[],
        tone="casual",
        seniority="senior",
        red_flags=[],
        raw_text_length=20,
    )
    assert parsed.job_title is None
    assert parsed.company_name is None


def test_parsed_jd_accepts_explicit_job_title_and_company_name() -> None:
    """D1: ParsedJD stores job_title and company_name when supplied."""
    parsed = ParsedJD(
        must_haves=["Python"],
        nice_to_haves=[],
        tone="casual",
        seniority="senior",
        red_flags=[],
        raw_text_length=20,
        job_title="Senior Frontend Engineer",
        company_name="Stripe",
    )
    assert parsed.job_title == "Senior Frontend Engineer"
    assert parsed.company_name == "Stripe"


def test_parse_jd_maps_job_title_and_company_name_from_llm() -> None:
    """D1: parse_jd passes job_title and company_name from the LLM ParseResult into ParsedJD."""
    jd_text = "Senior Frontend Engineer at Stripe.\n"

    def fake_parser(jd, *, api_key, timeout_seconds, prompt):
        return ParseResult(
            must_haves=["React"],
            nice_to_haves=[],
            tone="professional",
            seniority="senior",
            red_flags=[],
            cost_usd=Decimal("0.001"),
            input_tokens=100,
            output_tokens=50,
            job_title="Senior Frontend Engineer",
            company_name="Stripe",
        )

    parsed = parse_jd(
        jd_text,
        api_key="k",
        timeout_seconds=30.0,
        prompt=_template(),
        llm_parse=fake_parser,
    )
    assert parsed.job_title == "Senior Frontend Engineer"
    assert parsed.company_name == "Stripe"


def test_parse_jd_handles_none_job_title_and_company_name() -> None:
    """D1: parse_jd gracefully handles a JD with no stated title/company (both None)."""
    jd_text = "Looking for a developer.\n"

    def fake_parser(jd, *, api_key, timeout_seconds, prompt):
        return ParseResult(
            must_haves=["Python"],
            nice_to_haves=[],
            tone="casual",
            seniority="mid",
            red_flags=[],
            cost_usd=Decimal("0.001"),
            input_tokens=100,
            output_tokens=50,
            job_title=None,
            company_name=None,
        )

    parsed = parse_jd(
        jd_text,
        api_key="k",
        timeout_seconds=30.0,
        prompt=_template(),
        llm_parse=fake_parser,
    )
    assert parsed.job_title is None
    assert parsed.company_name is None
