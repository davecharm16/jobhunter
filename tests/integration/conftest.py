"""Integration-test fixtures (Stories 2.3, 2.4).

Adds autouse fixtures that keep the Story 2.3 parse step from reaching real
Anthropic during integration tests that drive the orchestrator without
injecting `llm_parse` explicitly. Two layers:

1. Stub `jobhunter.llm_client.parse_jd` to return a deterministic `ParseResult`
   so any code path that bottoms out at the SDK is intercepted.
2. Wrap `jobhunter.prompts.load_prompt` so a request for the `jd_parse`
   template resolves to a synthetic `PromptTemplate` even when the staged
   prompts directory does not contain `jd_parse.v1.md` (this lets Story 2.9
   tests stage minimal prompt dirs without knowing about Story 2.3).

The Story 2.4 classifier is heuristic-only (no LLM call), so it does not need
an autouse stub for cost/safety reasons — but tests that want a deterministic
classification can pass `fake_classify=make_fake_classifier(...)` through
`stage_tailoring()`.

Tests that need to assert parse-stage behavior (timeout, malformed response)
override the stubs with their own `monkeypatch.setattr` — the autouse fixtures
are baselines, not locks.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _stub_llm_parse_jd(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the Anthropic-touching parser with a deterministic stub."""
    from jobhunter.llm_client import ParseResult

    def fake_parse(
        jd_text: str,
        *,
        api_key: str,
        timeout_seconds: float,
        prompt,
        client_factory=None,
    ) -> ParseResult:
        return ParseResult(
            must_haves=["Python"],
            nice_to_haves=["Docker"],
            tone="neutral",
            seniority="senior",
            red_flags=[],
            cost_usd=Decimal("0.000100"),
            input_tokens=10,
            output_tokens=5,
        )

    import jobhunter.llm_client as llm_module

    monkeypatch.setattr(llm_module, "parse_jd", fake_parse)


@pytest.fixture(autouse=True)
def _autoresolve_jd_parse_template(monkeypatch: pytest.MonkeyPatch) -> None:
    """Synthesize a `jd_parse` PromptTemplate so test-staged dirs do not need one."""
    import jobhunter.prompts as prompts_module
    from jobhunter.prompts import PromptTemplate

    original_load = prompts_module.load_prompt

    def patched_load(artifact: str, *, prompts_dir: Path | None = None) -> PromptTemplate:
        if artifact == "jd_parse":
            try:
                return original_load(artifact, prompts_dir=prompts_dir)
            except prompts_module.PromptTemplateMissing:
                return PromptTemplate(
                    name="jd_parse",
                    version="v1",
                    content="parse the JD into structured fields\n",
                    path=Path("<synthetic jd_parse.v1.md for tests>"),
                )
        return original_load(artifact, prompts_dir=prompts_dir)

    monkeypatch.setattr(prompts_module, "load_prompt", patched_load)
    import jobhunter.tailoring as tailoring_module

    monkeypatch.setattr(tailoring_module.prompts, "load_prompt", patched_load)
