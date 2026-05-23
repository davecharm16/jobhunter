"""Anthropic LLM client wrapper for the tailoring step (Story 1.5).

The single public entry is `tailor()`. The module isolates SDK details so a
future provider switch (DECISIONS.md §4) is a single-file rewrite — see PRD
NFR-Integration: "switching providers must be a config change, not a code
rewrite".

Costs are computed in `Decimal` (never float) from the provider's reported
`Usage(input_tokens, output_tokens)` multiplied by the per-model price
constants in this module. Pricing constants and the chosen model are pinned
here so prompt/model edits are diffable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import anthropic

from jobhunter.prompts import PromptTemplate


__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "INPUT_PRICE_PER_MTOK",
    "LLMCallFailed",
    "LLMResponseInvalid",
    "MODEL_NAME",
    "OUTPUT_PRICE_PER_MTOK",
    "SYSTEM_PROMPT",
    "TAILORING_TOOL",
    "TailoringResult",
    "tailor",
]


MODEL_NAME = "claude-haiku-4-5"
INPUT_PRICE_PER_MTOK = Decimal("1.00")
OUTPUT_PRICE_PER_MTOK = Decimal("5.00")
DEFAULT_TIMEOUT_SECONDS = 60.0
_PRICE_DENOMINATOR = Decimal("1000000")
_COST_QUANTUM = Decimal("0.000001")


SYSTEM_PROMPT = (
    "You are an assistant that tailors a software engineer's CV and cover letter "
    "for a specific job description (JD).\n\n"
    "You are given:\n"
    "1. The candidate's canonical CV in JSON Resume v1.0.0 format. This is the "
    "authoritative source of the candidate's history.\n"
    "2. A JD pasted by the candidate.\n\n"
    "Produce two markdown artifacts:\n"
    "- A tailored CV that prioritizes canonical-CV entries relevant to the JD.\n"
    "- A cover letter (3-5 short paragraphs) addressing the JD specifically.\n\n"
    "NON-NEGOTIABLE RULES\n"
    "- Every skill, project, and claim in the tailored CV MUST trace to an entry "
    "in the canonical CV. Do not invent skills, employers, or experience the "
    "candidate has not stated.\n"
    "- Preserve the candidate's voice. Plain language. No corporate filler "
    "(\"synergize\", \"leverage\", \"results-driven\", \"passionate\", "
    "\"extensive experience\").\n"
    "- Use markdown only. Headings with ##, lists with -, emphasis with ** "
    "where appropriate. No HTML.\n"
    "- The cover letter is a letter, not a list. Paragraphs, not bullets.\n"
    "- Do not include a placeholder for the recipient's name unless the JD "
    "provides one.\n\n"
    "OUTPUT FORMAT\n"
    "Call the emit_tailored_artifacts tool with two string fields: cv_markdown "
    "and cover_letter_markdown. No other output.\n"
)


TAILORING_TOOL: dict[str, Any] = {
    "name": "emit_tailored_artifacts",
    "description": "Emit the tailored CV and cover letter for the candidate's JD.",
    "input_schema": {
        "type": "object",
        "properties": {
            "cv_markdown": {
                "type": "string",
                "description": "Tailored CV as a markdown document.",
            },
            "cover_letter_markdown": {
                "type": "string",
                "description": "Tailored cover letter as a markdown document.",
            },
        },
        "required": ["cv_markdown", "cover_letter_markdown"],
    },
}


class LLMCallFailed(RuntimeError):
    """Network/transport/timeout/HTTP failure during the LLM call."""


class LLMResponseInvalid(RuntimeError):
    """The LLM response was a paid-API success but its shape was unusable."""


@dataclass(frozen=True)
class TailoringResult:
    cv_markdown: str
    cover_letter_markdown: str
    cost_usd: Decimal
    input_tokens: int
    output_tokens: int


def _compute_cost(input_tokens: int, output_tokens: int) -> Decimal:
    cost = (
        Decimal(input_tokens) * INPUT_PRICE_PER_MTOK / _PRICE_DENOMINATOR
        + Decimal(output_tokens) * OUTPUT_PRICE_PER_MTOK / _PRICE_DENOMINATOR
    )
    return cost.quantize(_COST_QUANTUM)


def _build_user_prompt(canonical_cv: dict[str, Any], jd_text: str) -> str:
    cv_json = json.dumps(canonical_cv, indent=2)
    return (
        "## Canonical CV (JSON Resume v1.0.0)\n"
        "```json\n"
        f"{cv_json}\n"
        "```\n\n"
        "## Job Description\n"
        f"{jd_text}\n\n"
        "Produce the tailored CV and cover letter."
    )


def _extract_tool_input(response: Any) -> dict[str, Any]:
    content = getattr(response, "content", None)
    if not content:
        raise LLMResponseInvalid("LLM response had no content blocks")
    for block in content:
        block_type = getattr(block, "type", None)
        if block_type == "tool_use":
            payload = getattr(block, "input", None)
            if not isinstance(payload, dict):
                raise LLMResponseInvalid(
                    "tool_use block did not carry a dict input"
                )
            return payload
    raise LLMResponseInvalid("LLM response did not contain a tool_use block")


def _validate_field(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if value is None:
        raise LLMResponseInvalid(f"{field} missing from tool_use payload")
    if not isinstance(value, str):
        raise LLMResponseInvalid(f"{field} is not a string")
    if not value.strip():
        raise LLMResponseInvalid(f"{field} is empty or whitespace-only")
    return value


def tailor(
    canonical_cv: dict[str, Any],
    jd_text: str,
    *,
    api_key: str,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    client_factory: Any = None,
    prompts: dict[str, PromptTemplate] | None = None,
) -> TailoringResult:
    """Call the LLM once and return a validated `TailoringResult`.

    `client_factory` is a test seam: a callable returning a pre-built client
    object whose `.messages.create(...)` matches the Anthropic SDK shape. In
    production it defaults to `anthropic.Anthropic`.

    `prompts`, when provided, is a map of artifact name -> `PromptTemplate`;
    the `cv` entry's content replaces the baked-in `SYSTEM_PROMPT`. The v1
    `cv` and `cover_letter` templates are identical (one combined prompt
    drives both artifacts); the `cover_letter` entry is loaded for
    metadata-version tracking (Story 2.10) and is unused by this call.
    """
    factory = client_factory or anthropic.Anthropic
    client = factory(api_key=api_key, timeout=timeout_seconds)

    user_prompt = _build_user_prompt(canonical_cv, jd_text)
    system_prompt = prompts["cv"].content if prompts is not None else SYSTEM_PROMPT

    try:
        response = client.messages.create(
            model=MODEL_NAME,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            tools=[TAILORING_TOOL],
            tool_choice={"type": "tool", "name": "emit_tailored_artifacts"},
        )
    except anthropic.APITimeoutError as exc:
        raise LLMCallFailed(f"timeout after {timeout_seconds}s") from exc
    except anthropic.APIConnectionError as exc:
        raise LLMCallFailed(f"network error: {exc}") from exc
    except anthropic.APIStatusError as exc:
        status_code = getattr(exc, "status_code", "unknown")
        raise LLMCallFailed(f"provider returned {status_code}") from exc
    except Exception as exc:  # noqa: BLE001 — wrap unexpected SDK errors
        raise LLMCallFailed(f"unexpected error: {exc}") from exc

    usage = getattr(response, "usage", None)
    if usage is None:
        raise LLMResponseInvalid("usage missing from LLM response")
    raw_input_tokens = getattr(usage, "input_tokens", None)
    raw_output_tokens = getattr(usage, "output_tokens", None)
    if raw_input_tokens is None or raw_output_tokens is None:
        raise LLMResponseInvalid(
            "usage missing input_tokens or output_tokens — cost cannot be "
            "computed (this would silently zero-out the cap accounting)"
        )
    input_tokens = int(raw_input_tokens)
    output_tokens = int(raw_output_tokens)
    cost = _compute_cost(input_tokens, output_tokens)

    payload = _extract_tool_input(response)
    cv_markdown = _validate_field(payload, "cv_markdown")
    cover_letter_markdown = _validate_field(payload, "cover_letter_markdown")

    return TailoringResult(
        cv_markdown=cv_markdown,
        cover_letter_markdown=cover_letter_markdown,
        cost_usd=cost,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
