"""Story 6.2 AC1 + AC4 — silent-hold structural guard: fail -> ZERO POSTs.

This integration test pins the no-notify-on-fail contract by driving
`run_tailoring` end-to-end with a `GCHAT_WEBHOOK_URL` configured AND a
spy on `httpx.Client`, then asserting:

- For each of the four fail-mode fixtures (fabrication-only, content-loss-only,
  keyword-stuffing-only, and a multi-fail combination), ZERO POSTs reach the
  webhook URL and `metadata.notification` stays null.

- AC4 crash-survive + no double-stage: a pre-existing `./out/<slug>/`
  directory blocks the rerun with `409 Output slug already exists` (Story 1.5
  / 1.6 atomic-write contract), and the pre-existing directory is not
  modified.

Architectural deviation from the original Story 6.2 AC2 wording: held
packages live at `./out/<slug>/` (co-located with passed packages, identified
by `metadata.held=true` + `package.held.json` + `drift-report.md` sidecars),
NOT under a separate `./out/_held/<slug>/` tree. Stories 3.4 / 4.2 / 5.3
shipped that working architecture; Story 6.2 keeps the contract intact.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from tests.integration._web_helpers import (
    make_fake_parse,
    stage_tailoring,
)

from jobhunter.claim_extractor import Claim, ClaimExtractionResult
from jobhunter.llm_client import TailoringResult
from jobhunter.runtime_config import RuntimeConfig
from jobhunter.tailoring import run_tailoring
from jobhunter.web.api import create_app

FIXED_NOW = datetime(2026, 5, 23, 4, 0, 0, tzinfo=UTC)
GCHAT_WEBHOOK_URL = "https://example.test/webhook/silent-hold"


# ---- httpx spy ----------------------------------------------------------


def _install_post_spy(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    """Replace `jobhunter.notifier.httpx.Client` with one whose transport
    records every POST attempt. Any request leaving the pipeline lands in
    the returned list — the fail-path tests assert the list stays empty.
    """
    spy: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        spy.append(request)
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def _client_with_transport(*args: Any, **kwargs: Any) -> httpx.Client:
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(
        "jobhunter.notifier.httpx.Client", _client_with_transport
    )
    # Keep retry sleeps from slowing the suite if anything slipped past.
    monkeypatch.setattr("jobhunter.notifier.time.sleep", lambda _: None)
    return spy


# ---- canonical-CV staging -----------------------------------------------


def _canonical_cv_with_high_impact() -> dict[str, Any]:
    """Canonical CV with a tagged high-impact entry (Story 4.1 relevance trigger)."""
    return {
        "basics": {
            "name": "Test Author",
            "label": "Engineer",
            "email": "test@example.com",
        },
        "work": [
            {
                "name": "Acme",
                "position": "Senior Engineer",
                "startDate": "2020-01-01",
                "tags": ["typescript", "node"],
                "highImpact": True,
                "highlights": [
                    "Shipped a TypeScript ingestion service that cut latency by 60%",
                ],
            }
        ],
        "skills": [{"name": "Backend", "keywords": ["Python", "pytest"]}],
    }


def _stage_canonical_cv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cv: dict[str, Any] | None = None,
) -> Path:
    cv_path = tmp_path / "canonical-cv.json"
    cv_path.write_text(
        json.dumps(cv or _canonical_cv_with_high_impact()), encoding="utf-8"
    )
    import jobhunter.canonical_cv as reader_module
    import jobhunter.config as config_module

    monkeypatch.setattr(config_module, "CANONICAL_CV_PATH", cv_path)
    monkeypatch.setattr(reader_module, "CANONICAL_CV_PATH", cv_path)
    return cv_path


# ---- per-fail-mode extractor factories ----------------------------------


def _fail_extractor_fabrication() -> Callable[..., ClaimExtractionResult]:
    """Extractor whose claims have NO canonical-CV source -> fabrication fail."""

    def fake_extract(
        markdown_text: str,
        source_artifact: str,
        *,
        api_key: str,
        timeout_seconds: float,
        prompt: Any,
    ) -> ClaimExtractionResult:
        return ClaimExtractionResult(
            claims=[
                Claim(
                    claim_id=f"{source_artifact}:1:fakecla1",
                    claim_type="metric",
                    claim_text="fabricated 99x throughput improvement",
                    source_artifact=source_artifact,
                    line_number=1,
                )
            ],
            cost_usd=Decimal("0.000050"),
            input_tokens=5,
            output_tokens=3,
        )

    return fake_extract


def _zero_claim_extractor() -> Callable[..., ClaimExtractionResult]:
    """Extractor that emits zero claims -> fabrication passes vacuously."""

    def fake_extract(
        markdown_text: str,
        source_artifact: str,
        *,
        api_key: str,
        timeout_seconds: float,
        prompt: Any,
    ) -> ClaimExtractionResult:
        return ClaimExtractionResult(
            claims=[], cost_usd=Decimal("0"), input_tokens=0, output_tokens=0
        )

    return fake_extract


def _fake_tailor(cv: str = "# CV\n", cover: str = "Dear hiring manager,\n"):
    def _inner(canonical_cv, jd_text, *, api_key, timeout_seconds):
        return TailoringResult(
            cv_markdown=cv,
            cover_letter_markdown=cover,
            cost_usd=Decimal("0.004200"),
            input_tokens=10,
            output_tokens=5,
        )

    return _inner


# Long Greek-alphabet filler so passes-by-default modes don't trip the
# keyword-stuffing density check inadvertently (mirrors the Story 4.2 /
# Story 5.3 test conventions).
_FILLER = (
    " alpha beta gamma delta epsilon zeta eta theta iota kappa lambda "
    "mu nu xi omicron pi rho sigma tau upsilon phi chi psi omega "
) * 4


# ---- AC1: fail -> zero POSTs --------------------------------------------


def test_fabrication_only_fail_makes_zero_posts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fabrication fails (unsourced claim); content-loss + keyword-stuffing
    pass. Webhook URL is configured -> ZERO POSTs must reach it."""
    spy = _install_post_spy(monkeypatch)
    _stage_canonical_cv(tmp_path, monkeypatch)
    canonical_cv = json.loads(
        (tmp_path / "canonical-cv.json").read_text(encoding="utf-8")
    )
    # Chunk-match the high-impact highlight so content-loss passes.
    outcome = run_tailoring(
        canonical_cv,
        "Senior TypeScript role.\n",
        config=RuntimeConfig(
            llm_api_key="test-key",
            monthly_spend_cap_usd=Decimal("25.00"),
            llm_call_timeout_seconds=60.0,
            gchat_webhook_url=GCHAT_WEBHOOK_URL,
        ),
        now=FIXED_NOW,
        llm_tailor=_fake_tailor(
            cv=(
                "# CV\n\n"
                "- fabricated 99x throughput improvement\n"
                "- Shipped a TypeScript ingestion service that cut latency by 60%\n\n"
                + _FILLER + "\n"
            ),
            cover="hi\n",
        ),
        llm_extract_claims=_fail_extractor_fabrication(),
        llm_parse=make_fake_parse(must_haves=["typescript"], nice_to_haves=[]),
        out_root=tmp_path / "out",
        ledger_path=tmp_path / ".cost-ledger.json",
    )
    metadata = json.loads(
        (outcome.out_dir / "metadata.json").read_text(encoding="utf-8")
    )
    # Pre-condition: only fabrication failed.
    assert metadata["drift_verdicts"]["fabrication"] == "fail"
    assert metadata["drift_verdicts"]["content_loss"] == "pass"
    assert metadata["drift_verdicts"]["keyword_stuffing"] == "pass"
    assert metadata["held"] is True
    # AC1: ZERO POSTs to the webhook.
    assert spy == []
    # Held packages never carry a notification block.
    assert metadata["notification"] is None
    # AC2: drift-report.md sidecar is present and human-readable.
    assert (outcome.out_dir / "drift-report.md").is_file()


def test_content_loss_only_fail_makes_zero_posts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Content-loss fails (high-impact TypeScript drop); fabrication +
    keyword-stuffing pass. Webhook URL is configured -> ZERO POSTs."""
    spy = _install_post_spy(monkeypatch)
    _stage_canonical_cv(tmp_path, monkeypatch)
    canonical_cv = json.loads(
        (tmp_path / "canonical-cv.json").read_text(encoding="utf-8")
    )
    outcome = run_tailoring(
        canonical_cv,
        "Senior TypeScript role.\n",
        config=RuntimeConfig(
            llm_api_key="test-key",
            monthly_spend_cap_usd=Decimal("25.00"),
            llm_call_timeout_seconds=60.0,
            gchat_webhook_url=GCHAT_WEBHOOK_URL,
        ),
        now=FIXED_NOW,
        llm_tailor=_fake_tailor(
            # No TypeScript highlight present -> content-loss fail.
            cv="# CV\n\n- completely unrelated content\n\n" + _FILLER + "\n",
            cover="hi\n",
        ),
        llm_extract_claims=_zero_claim_extractor(),
        llm_parse=make_fake_parse(must_haves=["typescript"], nice_to_haves=[]),
        out_root=tmp_path / "out",
        ledger_path=tmp_path / ".cost-ledger.json",
    )
    metadata = json.loads(
        (outcome.out_dir / "metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["drift_verdicts"]["fabrication"] == "pass"
    assert metadata["drift_verdicts"]["content_loss"] == "fail"
    assert metadata["drift_verdicts"]["keyword_stuffing"] == "pass"
    assert metadata["held"] is True
    assert spy == []
    assert metadata["notification"] is None
    assert (outcome.out_dir / "drift-report.md").is_file()


def test_keyword_stuffing_only_fail_makes_zero_posts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keyword-stuffing fails (density well over 1.5%); fabrication +
    content-loss pass. Webhook URL is configured -> ZERO POSTs."""
    spy = _install_post_spy(monkeypatch)
    # Use a CV that has no high-impact entries so content-loss has nothing
    # to lose.
    cv_doc = {
        "basics": {
            "name": "Test Author",
            "label": "Engineer",
            "email": "test@example.com",
        },
        "work": [
            {
                "name": "Acme",
                "position": "Engineer",
                "startDate": "2020-01-01",
                "highlights": ["Shipped a Python service"],
            }
        ],
        "skills": [{"name": "Python", "keywords": ["python", "pytest"]}],
    }
    _stage_canonical_cv(tmp_path, monkeypatch, cv=cv_doc)
    canonical_cv = json.loads(
        (tmp_path / "canonical-cv.json").read_text(encoding="utf-8")
    )
    outcome = run_tailoring(
        canonical_cv,
        "Senior Python role.\n",
        config=RuntimeConfig(
            llm_api_key="test-key",
            monthly_spend_cap_usd=Decimal("25.00"),
            llm_call_timeout_seconds=60.0,
            gchat_webhook_url=GCHAT_WEBHOOK_URL,
        ),
        now=FIXED_NOW,
        llm_tailor=_fake_tailor(
            # Stuffing density: "python" repeated 6 times in a short CV body
            # crosses the 1.5% threshold AND the 3-rep ceiling.
            cv="python python python python python python end\n",
            cover="hi\n",
        ),
        llm_extract_claims=_zero_claim_extractor(),
        llm_parse=make_fake_parse(must_haves=["python"], nice_to_haves=[]),
        out_root=tmp_path / "out",
        ledger_path=tmp_path / ".cost-ledger.json",
    )
    metadata = json.loads(
        (outcome.out_dir / "metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["drift_verdicts"]["fabrication"] == "pass"
    assert metadata["drift_verdicts"]["content_loss"] == "pass"
    assert metadata["drift_verdicts"]["keyword_stuffing"] == "fail"
    assert metadata["held"] is True
    assert spy == []
    assert metadata["notification"] is None
    assert (outcome.out_dir / "drift-report.md").is_file()


def test_multi_fail_makes_zero_posts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """All three drift checks fail at once. Webhook is configured -> ZERO POSTs."""
    spy = _install_post_spy(monkeypatch)
    _stage_canonical_cv(tmp_path, monkeypatch)
    canonical_cv = json.loads(
        (tmp_path / "canonical-cv.json").read_text(encoding="utf-8")
    )
    outcome = run_tailoring(
        canonical_cv,
        "Senior TypeScript role.\n",
        config=RuntimeConfig(
            llm_api_key="test-key",
            monthly_spend_cap_usd=Decimal("25.00"),
            llm_call_timeout_seconds=60.0,
            gchat_webhook_url=GCHAT_WEBHOOK_URL,
        ),
        now=FIXED_NOW,
        llm_tailor=_fake_tailor(
            # Triple-fail body:
            # - "fabricated 99x" is the unsourced claim (fabrication fail)
            # - TypeScript highlight absent (content-loss fail)
            # - "typescript" repeated densely (keyword-stuffing fail)
            cv=(
                "# CV\n\n"
                "- fabricated 99x throughput improvement\n"
                "typescript typescript typescript typescript typescript "
                "typescript typescript end\n"
            ),
            cover="hi\n",
        ),
        llm_extract_claims=_fail_extractor_fabrication(),
        llm_parse=make_fake_parse(must_haves=["typescript"], nice_to_haves=[]),
        out_root=tmp_path / "out",
        ledger_path=tmp_path / ".cost-ledger.json",
    )
    metadata = json.loads(
        (outcome.out_dir / "metadata.json").read_text(encoding="utf-8")
    )
    # All three failed.
    assert metadata["drift_verdicts"]["fabrication"] == "fail"
    assert metadata["drift_verdicts"]["content_loss"] == "fail"
    assert metadata["drift_verdicts"]["keyword_stuffing"] == "fail"
    assert metadata["held"] is True
    assert spy == []
    assert metadata["notification"] is None
    # AC2: drift-report.md present and contains all three section headings.
    report = (outcome.out_dir / "drift-report.md").read_text(encoding="utf-8")
    assert "## Fabrication" in report
    assert "## Content loss" in report
    assert "## Keyword stuffing" in report
    # And the fail verdicts are surfaced in the rendered Markdown.
    assert report.count("Verdict: **fail**") == 3


# ---- AC4: pre-existing slug dir -> 409 + dir untouched ------------------


def test_pre_existing_slug_dir_returns_409_without_modifying_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A re-run on the same slug returns 409 (Story 1.5/1.6 contract) and
    leaves the pre-existing directory untouched. No POST happens either —
    the pipeline never reaches the notification gate."""
    import jobhunter.tailoring as tailoring_module

    spy = _install_post_spy(monkeypatch)
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    monkeypatch.setenv("GCHAT_WEBHOOK_URL", GCHAT_WEBHOOK_URL)
    _stage_canonical_cv(tmp_path, monkeypatch)
    out_root, _ = stage_tailoring(tmp_path, monkeypatch)

    # Force a stable slug so the pre-created collision matches the re-run.
    fixed_slug = "20260524t031530z-senior-python-role"
    monkeypatch.setattr(
        tailoring_module, "make_slug", lambda jd_text, now=None: fixed_slug
    )
    out_root.mkdir(parents=True, exist_ok=True)
    pre_existing = out_root / fixed_slug
    pre_existing.mkdir()
    # Drop a sentinel file so we can detect any mutation by the failed run.
    sentinel = pre_existing / "sentinel.txt"
    sentinel.write_text("pre-existing content\n", encoding="utf-8")
    sentinel_mtime_before = sentinel.stat().st_mtime
    contents_before = sorted(p.name for p in pre_existing.iterdir())

    client = TestClient(create_app(), raise_server_exceptions=False)
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )

    # Story 1.5/1.6: slug collision returns 409 Conflict.
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]
    # AC4: pre-existing directory contents unchanged (no over-write).
    contents_after = sorted(p.name for p in pre_existing.iterdir())
    assert contents_after == contents_before
    assert sentinel.read_text(encoding="utf-8") == "pre-existing content\n"
    assert sentinel.stat().st_mtime == sentinel_mtime_before
    # AC1 contract still holds: no POST happened on this fail path either —
    # the pipeline raised before the notification gate.
    assert spy == []
