"""Story 6.1 integration: GChat notification gates correctly on drift verdicts.

Drives `run_tailoring` end-to-end with the conftest-level autouse stubs in
place, then asserts the notification side-effect:

- AC2 happy path: all three drift verdicts `"pass"` + `gchat_webhook_url`
  set -> exactly one POST happens and `metadata.notification.status` is
  `"delivered"`.
- AC3 failure path: 5xx after retries -> POST is attempted, returns
  delivered=False, `metadata.notification.status` is `"delivery_failed"`,
  the package directory + sidecar stay on disk, and run_tailoring still
  returns a TailoringOutcome (no exception propagates).
- AC2 + AC3 gate: any drift verdict !== "pass" -> ZERO POSTs happen
  (verifies the no-notify-on-fail contract at the integration layer; the
  Story 6.2 held-branch structural guard pins it from the other side).
- AC1 gate: `gchat_webhook_url=None` -> ZERO POSTs happen, no
  `notification` field written.

httpx is intercepted via a Spy callable injected through
`monkeypatch.setattr("jobhunter.notifier.httpx.Client", ...)`; no real
network traffic leaves the process.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx

from jobhunter.claim_extractor import Claim, ClaimExtractionResult
from jobhunter.llm_client import TailoringResult
from jobhunter.runtime_config import RuntimeConfig
from jobhunter.tailoring import run_tailoring

FIXED_NOW = datetime(2026, 5, 23, 4, 0, 0, tzinfo=UTC)


def _config(*, gchat_webhook_url: str | None = None) -> RuntimeConfig:
    return RuntimeConfig(
        llm_api_key="test-key",
        monthly_spend_cap_usd=Decimal("25.00"),
        llm_call_timeout_seconds=60.0,
        gchat_webhook_url=gchat_webhook_url,
    )


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


def _all_pass_extractor() -> Callable[..., ClaimExtractionResult]:
    """A claim extractor that emits only canonical-CV-sourced claims.

    The committed `canonical-cv.json` lists "Python" as a skill keyword on
    the test-author basics block, so a `Python` claim resolves via the
    fabrication matcher. The minimal CV markdown body keeps density well
    below the keyword-stuffing threshold and the content-loss matcher
    has nothing to lose because the staged canonical CV has no high-impact
    entries -> all three verdicts come up `pass`.
    """

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
                    claim_id=f"{source_artifact}:1:pythonpy",
                    claim_type="skill",
                    claim_text="Python",
                    source_artifact=source_artifact,
                    line_number=1,
                )
            ],
            cost_usd=Decimal("0.000050"),
            input_tokens=5,
            output_tokens=3,
        )

    return fake_extract


def _stage_canonical_cv(tmp_path: Path, monkeypatch) -> Path:
    """Write a canonical CV that yields all-pass drift verdicts."""
    cv_path = tmp_path / "canonical-cv.json"
    cv_path.write_text(
        json.dumps(
            {
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
                "skills": [
                    {"name": "Python", "keywords": ["Python", "pytest"]},
                ],
                "education": [
                    {"institution": "U", "area": "CS", "studyType": "BSc"},
                ],
                "projects": [
                    {"name": "jobhunter", "highlights": ["Walking skeleton"]},
                ],
            }
        ),
        encoding="utf-8",
    )
    import jobhunter.canonical_cv as reader_module
    import jobhunter.config as config_module

    monkeypatch.setattr(config_module, "CANONICAL_CV_PATH", cv_path)
    monkeypatch.setattr(reader_module, "CANONICAL_CV_PATH", cv_path)
    return cv_path


def _install_mock_httpx(
    monkeypatch, *, responses: list[Any], spy: list[httpx.Request]
) -> None:
    iterator = iter(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        spy.append(request)
        item = next(iterator)
        if isinstance(item, BaseException):
            raise item
        return item

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def _client_with_transport(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr("jobhunter.notifier.httpx.Client", _client_with_transport)


def _run_all_pass(tmp_path: Path, monkeypatch, *, config: RuntimeConfig):
    canonical_cv = json.loads(
        _stage_canonical_cv(tmp_path, monkeypatch).read_text(encoding="utf-8")
    )
    # Patch sleep so retry backoff does not slow the test suite.
    monkeypatch.setattr("jobhunter.notifier.time.sleep", lambda _: None)
    return run_tailoring(
        canonical_cv,
        "Senior Python role.\n",
        config=config,
        now=FIXED_NOW,
        llm_tailor=_fake_tailor(),
        llm_extract_claims=_all_pass_extractor(),
        out_root=tmp_path / "out",
        ledger_path=tmp_path / ".cost-ledger.json",
    )


# --- AC2: happy-path notification on all-pass + webhook configured -------


def test_all_pass_with_webhook_posts_once_and_records_delivered(
    tmp_path: Path, monkeypatch
) -> None:
    spy: list[httpx.Request] = []
    _install_mock_httpx(
        monkeypatch,
        responses=[httpx.Response(200, json={"ok": True})],
        spy=spy,
    )

    outcome = _run_all_pass(
        tmp_path,
        monkeypatch,
        config=_config(gchat_webhook_url="https://example.test/hook"),
    )
    metadata = json.loads(
        (outcome.out_dir / "metadata.json").read_text(encoding="utf-8")
    )

    # Pre-condition: drift verdicts really are all-pass.
    assert metadata["drift_verdicts"] == {
        "fabrication": "pass",
        "content_loss": "pass",
        "keyword_stuffing": "pass",
    }
    # AC2: exactly one POST happened.
    assert len(spy) == 1
    assert str(spy[0].url) == "https://example.test/hook"
    body = json.loads(spy[0].content.decode("utf-8"))
    assert "text" in body
    assert "Ready for your review" in body["text"]
    # AC3: sidecar records delivered status.
    assert metadata["notification"]["status"] == "delivered"
    assert metadata["notification"]["delivered_at"].endswith("Z")


# --- AC1 gate: webhook URL not configured -> no POST, no notification ----


def test_all_pass_with_no_webhook_does_not_post(
    tmp_path: Path, monkeypatch
) -> None:
    spy: list[httpx.Request] = []
    _install_mock_httpx(
        monkeypatch, responses=[], spy=spy
    )

    outcome = _run_all_pass(
        tmp_path, monkeypatch, config=_config(gchat_webhook_url=None)
    )
    metadata = json.loads(
        (outcome.out_dir / "metadata.json").read_text(encoding="utf-8")
    )

    assert spy == []
    assert metadata["notification"] is None
    # Drift verdicts still all-pass — the gate ran, just didn't fire.
    assert metadata["drift_verdicts"]["fabrication"] == "pass"


# --- AC3: delivery failure is non-fatal + sidecar captures it ------------


def test_all_pass_with_unreachable_webhook_records_delivery_failed(
    tmp_path: Path, monkeypatch
) -> None:
    """5xx after retries -> delivery_failed, package stays on disk, no raise."""
    spy: list[httpx.Request] = []
    _install_mock_httpx(
        monkeypatch,
        responses=[
            httpx.Response(502),
            httpx.Response(503),
            httpx.Response(500),
        ],
        spy=spy,
    )

    outcome = _run_all_pass(
        tmp_path,
        monkeypatch,
        config=_config(gchat_webhook_url="https://example.test/hook"),
    )
    metadata = json.loads(
        (outcome.out_dir / "metadata.json").read_text(encoding="utf-8")
    )

    assert len(spy) == 3  # 3 attempts
    assert metadata["notification"]["status"] == "delivery_failed"
    assert metadata["notification"]["attempts"] == 3
    assert metadata["notification"]["last_error"] == "http_500"
    # Package artifacts and sidecars stay on disk.
    assert (outcome.out_dir / "cv.md").exists()
    assert (outcome.out_dir / "cover-letter.md").exists()
    assert (outcome.out_dir / "metadata.json").exists()


def test_all_pass_with_network_error_records_delivery_failed(
    tmp_path: Path, monkeypatch
) -> None:
    spy: list[httpx.Request] = []
    _install_mock_httpx(
        monkeypatch,
        responses=[
            httpx.ConnectError("DNS fail"),
            httpx.ConnectError("DNS fail"),
            httpx.ConnectError("DNS fail"),
        ],
        spy=spy,
    )

    outcome = _run_all_pass(
        tmp_path,
        monkeypatch,
        config=_config(gchat_webhook_url="https://example.test/hook"),
    )
    metadata = json.loads(
        (outcome.out_dir / "metadata.json").read_text(encoding="utf-8")
    )

    assert len(spy) == 3
    assert metadata["notification"]["status"] == "delivery_failed"
    assert "ConnectError" in metadata["notification"]["last_error"]


# --- AC2 gate: any drift fail -> ZERO POSTs ------------------------------


def test_drift_fail_does_not_post_to_webhook(
    tmp_path: Path, monkeypatch
) -> None:
    """Story 6.2 contract preview: a fail anywhere in drift_verdicts -> no POST.

    This test stages a fabrication-fail (claim text "fabricated 99x" with
    no canonical source) and asserts:
      - the package is held (`held=true` in metadata)
      - ZERO POSTs hit the webhook
      - no `notification` field on the sidecar
    """
    spy: list[httpx.Request] = []
    _install_mock_httpx(monkeypatch, responses=[], spy=spy)
    _stage_canonical_cv(tmp_path, monkeypatch)
    canonical_cv = json.loads(
        (tmp_path / "canonical-cv.json").read_text(encoding="utf-8")
    )

    def fail_extractor(
        markdown_text, source_artifact, *, api_key, timeout_seconds, prompt
    ) -> ClaimExtractionResult:
        return ClaimExtractionResult(
            claims=[
                Claim(
                    claim_id=f"{source_artifact}:1:fakefake",
                    claim_type="metric",
                    claim_text="fabricated 99x throughput gain",
                    source_artifact=source_artifact,
                    line_number=1,
                )
            ],
            cost_usd=Decimal("0.000050"),
            input_tokens=5,
            output_tokens=3,
        )

    outcome = run_tailoring(
        canonical_cv,
        "Senior Python role.\n",
        config=_config(gchat_webhook_url="https://example.test/hook"),
        now=FIXED_NOW,
        llm_tailor=_fake_tailor(),
        llm_extract_claims=fail_extractor,
        out_root=tmp_path / "out",
        ledger_path=tmp_path / ".cost-ledger.json",
    )
    metadata = json.loads(
        (outcome.out_dir / "metadata.json").read_text(encoding="utf-8")
    )

    # Pre-condition: at least one drift verdict is fail.
    fail_count = sum(
        1 for v in metadata["drift_verdicts"].values() if v == "fail"
    )
    assert fail_count >= 1
    assert metadata["held"] is True
    # AC2 gate: ZERO POSTs.
    assert spy == []
    # Held packages never carry a `notification` block.
    assert metadata["notification"] is None
