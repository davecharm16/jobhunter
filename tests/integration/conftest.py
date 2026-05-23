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
    """Synthesize the `jd_parse` and `claims_extract` PromptTemplates."""
    import jobhunter.prompts as prompts_module
    from jobhunter.prompts import PromptTemplate

    original_load = prompts_module.load_prompt
    _SYNTHETIC = {
        "jd_parse": "parse the JD into structured fields\n",
        # Story 3.1: tests that stage minimal prompt dirs (Story 2.9 family)
        # should not need to know about the claim-extraction prompt either.
        "claims_extract": "extract atomic claims from the source markdown\n",
    }

    def patched_load(artifact: str, *, prompts_dir: Path | None = None) -> PromptTemplate:
        if artifact in _SYNTHETIC:
            try:
                return original_load(artifact, prompts_dir=prompts_dir)
            except prompts_module.PromptTemplateMissing:
                return PromptTemplate(
                    name=artifact,
                    version="v1",
                    content=_SYNTHETIC[artifact],
                    path=Path(f"<synthetic {artifact}.v1.md for tests>"),
                )
        return original_load(artifact, prompts_dir=prompts_dir)

    monkeypatch.setattr(prompts_module, "load_prompt", patched_load)
    import jobhunter.tailoring as tailoring_module

    monkeypatch.setattr(tailoring_module.prompts, "load_prompt", patched_load)


@pytest.fixture(autouse=True)
def _stub_llm_extract_claims(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the Anthropic-touching claim extractor with a deterministic stub.

    Story 3.1 introduces a third LLM call (after `parse_jd` and `tailor`).
    Mirrors the `_stub_llm_parse_jd` pattern: any integration test that does
    not explicitly inject `llm_extract_claims` gets a zero-cost, deterministic
    result. Tests that need to assert extraction behavior (timeout, malformed
    response) override this with their own `monkeypatch.setattr`.
    """
    from jobhunter.claim_extractor import Claim, ClaimExtractionResult

    def fake_extract(
        markdown_text: str,
        source_artifact: str,
        *,
        api_key: str,
        timeout_seconds: float,
        prompt,
        llm_extract=None,
    ) -> ClaimExtractionResult:
        # Emit one trivial claim per artifact so claims.json is non-empty
        # but deterministic — integration tests assert shape, not content.
        return ClaimExtractionResult(
            claims=[
                Claim(
                    claim_id=f"{source_artifact}:1:stubstub",
                    claim_type="skill",
                    claim_text="pytest",
                    source_artifact=source_artifact,
                    line_number=1,
                )
            ],
            cost_usd=Decimal("0.000050"),
            input_tokens=5,
            output_tokens=3,
        )

    import jobhunter.claim_extractor as extractor_module
    import jobhunter.tailoring as tailoring_module

    monkeypatch.setattr(extractor_module, "extract_claims_from_markdown", fake_extract)
    monkeypatch.setattr(
        tailoring_module.claim_extractor,
        "extract_claims_from_markdown",
        fake_extract,
    )
