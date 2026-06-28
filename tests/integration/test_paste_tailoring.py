"""POST /api/paste tailoring contracts (the Story 1.5 ACs, ported)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from tests.integration._web_helpers import (
    FAKE_COST_USD,
    FAKE_COVER_LETTER_MARKDOWN,
    FAKE_CV_MARKDOWN,
    make_fake_tailor,
    stage_canonical_cv,
    stage_tailoring,
    write_ledger,
)

from jobhunter import __version__
from jobhunter.slug import SLUG_REGEX
from jobhunter.web.api import create_app

# --- Healthz ---------------------------------------------------------------


def test_healthz_returns_ok_with_package_version() -> None:
    client = TestClient(create_app())
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body == {"status": "ok", "version": __version__}


# --- AC1 happy path --------------------------------------------------------


def test_paste_happy_path_writes_both_artifacts_and_names_them(
    tmp_path, monkeypatch,
) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root, ledger_path = stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert SLUG_REGEX.fullmatch(body["slug"])
    assert body["cv_path"].endswith("cv.md")
    assert body["cover_letter_path"].endswith("cover-letter.md")
    assert body["cost_usd"] == str(FAKE_COST_USD)

    slug_dirs = [p for p in out_root.iterdir() if p.is_dir()]
    assert len(slug_dirs) == 1
    slug_dir = slug_dirs[0]
    assert (slug_dir / "cv.md").read_text(encoding="utf-8") == FAKE_CV_MARKDOWN
    assert (
        (slug_dir / "cover-letter.md").read_text(encoding="utf-8")
        == FAKE_COVER_LETTER_MARKDOWN
    )
    assert ledger_path.exists()


# --- AC3 cap pre-check -----------------------------------------------------


def test_paste_cap_exceeded_returns_402_and_does_not_invoke_llm(
    tmp_path, monkeypatch,
) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    month_key = datetime.now(UTC).strftime("%Y-%m")
    out_root = tmp_path / "out"
    ledger_path = tmp_path / ".cost-ledger.json"
    write_ledger(ledger_path, month_key, "25.00", 999)

    invoked = {"called": False}

    def must_not_run(*args, **kwargs):
        invoked["called"] = True
        raise AssertionError("LLM must not be invoked when cap is reached")

    stage_tailoring(tmp_path, monkeypatch, fake_tailor=must_not_run)

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )
    assert response.status_code == 402, response.text
    detail = response.json()["detail"]
    assert detail["error"] == "monthly_spend_cap_reached"
    assert detail["current_usd"] == "25.00"
    assert detail["cap_usd"] == "25.00"
    assert invoked["called"] is False
    assert not out_root.exists()


# --- AC4 ledger updates ----------------------------------------------------


def test_paste_success_updates_ledger(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    month_key = datetime.now(UTC).strftime("%Y-%m")
    ledger_path = tmp_path / ".cost-ledger.json"
    write_ledger(ledger_path, month_key, "10.00", 3)
    stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )
    assert response.status_code == 200, response.text

    data = json.loads(ledger_path.read_text(encoding="utf-8"))
    new_total = Decimal(data[month_key]["total_usd"])
    assert new_total == Decimal("10.00") + FAKE_COST_USD
    assert data[month_key]["calls"] == 4


# --- AC5 LLM failure -------------------------------------------------------


def test_paste_llm_failure_returns_502_and_writes_nothing(
    tmp_path, monkeypatch,
) -> None:
    from jobhunter.llm_client import LLMCallFailed

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)

    def boom(*args, **kwargs):
        raise LLMCallFailed("provider returned 503")

    out_root, ledger_path = stage_tailoring(tmp_path, monkeypatch, fake_tailor=boom)

    client = TestClient(create_app(), raise_server_exceptions=False)
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )
    assert response.status_code == 502
    assert "LLM call failed" in response.json()["detail"]
    assert not out_root.exists()
    assert not ledger_path.exists()


# --- AC6 invalid LLM response ----------------------------------------------


def test_paste_invalid_llm_response_returns_502(tmp_path, monkeypatch) -> None:
    from jobhunter.llm_client import LLMResponseInvalid

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)

    def invalid(*args, **kwargs):
        raise LLMResponseInvalid("cv_markdown missing")

    out_root, _ = stage_tailoring(tmp_path, monkeypatch, fake_tailor=invalid)

    client = TestClient(create_app(), raise_server_exceptions=False)
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )
    assert response.status_code == 502
    assert "LLM response was unusable" in response.json()["detail"]
    assert not out_root.exists()


# --- AC7 timeout env validation --------------------------------------------


def test_paste_invalid_timeout_env_returns_500(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    monkeypatch.setenv("LLM_CALL_TIMEOUT_SECONDS", "-1")
    stage_canonical_cv(tmp_path, monkeypatch)
    stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app(), raise_server_exceptions=False)
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )
    assert response.status_code == 500
    assert "LLM_CALL_TIMEOUT_SECONDS" in response.json()["detail"]


# --- AC9 canonical CV untouched -------------------------------------------


def test_paste_does_not_mutate_canonical_cv(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    cv_path = stage_canonical_cv(tmp_path, monkeypatch)
    stage_tailoring(tmp_path, monkeypatch)

    before = hashlib.sha256(cv_path.read_bytes()).hexdigest()
    before_mtime = cv_path.stat().st_mtime_ns

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )
    assert response.status_code == 200, response.text

    assert hashlib.sha256(cv_path.read_bytes()).hexdigest() == before
    assert cv_path.stat().st_mtime_ns == before_mtime


# --- AC10 env gate ordering ------------------------------------------------


def test_paste_env_gate_fires_before_corrupt_ledger_is_read(
    tmp_path, monkeypatch,
) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    ledger_path = tmp_path / ".cost-ledger.json"
    ledger_path.write_text("garbage", encoding="utf-8")
    stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app(), raise_server_exceptions=False)
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )
    assert response.status_code == 500
    assert "LLM_API_KEY" in response.json()["detail"]


# --- Slug-collision happy path through the route handler ------------------


def test_paste_pre_existing_slug_dir_returns_409(tmp_path, monkeypatch) -> None:
    import jobhunter.tailoring as tailoring_module

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root, _ = stage_tailoring(tmp_path, monkeypatch)

    # Force the next run's slug to a known, stable value so the pre-created
    # collision directory is guaranteed to match.
    fixed_slug = "20260524t031530z-senior-python-role"
    monkeypatch.setattr(
        tailoring_module, "make_slug", lambda jd_text, now=None: fixed_slug
    )
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / fixed_slug).mkdir()

    client = TestClient(create_app(), raise_server_exceptions=False)
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


# --- AC8 / FR44: no outbound HTTP during a normal run ---------------------


def test_paste_makes_no_outbound_http_during_normal_run(
    tmp_path, monkeypatch,
) -> None:
    """Tailoring goes through the injected stub; the only network surface
    is the LLM client, which we replace. Monkeypatching `socket.create_connection`
    to fail catches any accidental outbound socket attempt.
    """
    import socket

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    stage_tailoring(tmp_path, monkeypatch)

    original_connect = socket.create_connection

    def guarded_connect(address, *args, **kwargs):
        host, _port = address
        if host in ("127.0.0.1", "localhost", "::1", "testserver"):
            return original_connect(address, *args, **kwargs)
        raise AssertionError(f"unexpected outbound connection to {host!r}")

    monkeypatch.setattr(socket, "create_connection", guarded_connect)

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )
    assert response.status_code == 200, response.text


# --- Response shape contract ------------------------------------------------


def test_paste_response_lists_cost_with_six_decimal_precision(
    tmp_path, monkeypatch,
) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    stage_tailoring(
        tmp_path,
        monkeypatch,
        fake_tailor=make_fake_tailor(cost=Decimal("0.001234")),
    )

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior Python.\n", "source": "browser"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["cost_usd"] == "0.001234"


# --- Run-tailoring direct ---------------------------------------------------


def test_run_tailoring_returns_decimal_cost_six_decimal_places(tmp_path) -> None:
    from jobhunter.runtime_config import RuntimeConfig
    from jobhunter.tailoring import run_tailoring

    config = RuntimeConfig(
        llm_api_key="k",
        monthly_spend_cap_usd=Decimal("25.00"),
        llm_call_timeout_seconds=60.0,
    )

    outcome = run_tailoring(
        {"basics": {"name": "X"}},
        "Senior Python role.\n",
        config=config,
        llm_tailor=make_fake_tailor(),
        out_root=tmp_path / "out",
        ledger_path=tmp_path / ".cost-ledger.json",
    )
    assert outcome.result.cost_usd == FAKE_COST_USD


def test_pyproject_pinning_preserves_epic1_runtime_deps() -> None:
    """Existing pins survive; the web extras land in the right group."""
    from jobhunter.config import PROJECT_ROOT as _ROOT

    text = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "jsonschema>=4.21" in text
    assert "python-dotenv>=1.2.2" in text
    assert "anthropic>=0.40.0" in text
    assert "fastapi" in text
    assert "uvicorn" in text


@pytest.mark.parametrize("forbidden", ["requests>=", "selenium>=", "playwright>="])
def test_pyproject_does_not_introduce_http_or_browser_clients(forbidden: str) -> None:
    from jobhunter.config import PROJECT_ROOT as _ROOT

    text = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert forbidden not in text
