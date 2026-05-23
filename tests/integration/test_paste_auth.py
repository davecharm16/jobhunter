"""POST /api/paste shared-token auth tests (Story 2.11).

Loopback callers (127.0.0.1, ::1, localhost, TestClient default) bypass the
token check per DECISIONS.md §6. Non-loopback callers must present a matching
`Authorization: Bearer <INGEST_TOKEN>` header. The 401 short-circuit happens
before the body is parsed and before the pipeline (and thus the LLM) runs.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from jobhunter.llm_client import TailoringResult
from jobhunter.web.api import create_app
from tests.integration._web_helpers import (
    FAKE_COST_USD,
    stage_canonical_cv,
    stage_tailoring,
)


REMOTE_CLIENT = ("203.0.113.10", 51422)


def _record_tailor_calls(monkeypatch) -> dict:
    """Patch `run_tailoring` on the api module to record invocation only.

    Returns a dict with `"called": bool` flipped to True if the route reaches
    the pipeline. The auth-failure tests assert it stays False.
    """
    import jobhunter.web.api as api_module

    state = {"called": False}

    def recording_run(canonical_cv, jd_text, *, config, **_):
        state["called"] = True
        return TailoringResult(  # pragma: no cover — auth tests never reach here
            cv_markdown="",
            cover_letter_markdown="",
            cost_usd=Decimal("0"),
            input_tokens=0,
            output_tokens=0,
        )

    monkeypatch.setattr(api_module, "run_tailoring", recording_run)
    return state


# --- AC1/AC4 loopback bypass: existing browser path still works ------------


def test_loopback_caller_without_token_is_accepted(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    monkeypatch.delenv("INGEST_TOKEN", raising=False)
    stage_canonical_cv(tmp_path, monkeypatch)
    stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior Python.\n", "source": "browser"},
    )
    assert response.status_code == 200, response.text


def test_loopback_caller_with_token_is_accepted(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    monkeypatch.setenv("INGEST_TOKEN", "secret-abc")
    stage_canonical_cv(tmp_path, monkeypatch)
    stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        headers={"Authorization": "Bearer secret-abc"},
        json={"jd_text": "Senior Python.\n", "source": "browser"},
    )
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("client_host", ["127.0.0.1", "::1", "localhost"])
def test_explicit_loopback_ip_bypasses_token(
    tmp_path, monkeypatch, client_host
) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    monkeypatch.delenv("INGEST_TOKEN", raising=False)
    stage_canonical_cv(tmp_path, monkeypatch)
    stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app(), client=(client_host, 54321))
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior Python.\n", "source": "browser"},
    )
    assert response.status_code == 200, response.text


# --- AC2: non-loopback callers need the token ------------------------------


def test_non_loopback_missing_authorization_returns_401(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    monkeypatch.setenv("INGEST_TOKEN", "secret-abc")
    stage_canonical_cv(tmp_path, monkeypatch)
    stage_tailoring(tmp_path, monkeypatch)
    pipeline = _record_tailor_calls(monkeypatch)

    client = TestClient(create_app(), client=REMOTE_CLIENT)
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior Python.\n", "source": "n8n"},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "missing_ingest_token"}
    assert pipeline["called"] is False


def test_non_loopback_wrong_token_returns_401(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    monkeypatch.setenv("INGEST_TOKEN", "secret-abc")
    stage_canonical_cv(tmp_path, monkeypatch)
    stage_tailoring(tmp_path, monkeypatch)
    pipeline = _record_tailor_calls(monkeypatch)

    client = TestClient(create_app(), client=REMOTE_CLIENT)
    response = client.post(
        "/api/paste",
        headers={"Authorization": "Bearer wrong-token"},
        json={"jd_text": "Senior Python.\n", "source": "n8n"},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "invalid_ingest_token"}
    assert pipeline["called"] is False


def test_non_loopback_wrong_scheme_returns_401(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    monkeypatch.setenv("INGEST_TOKEN", "secret-abc")
    stage_canonical_cv(tmp_path, monkeypatch)
    stage_tailoring(tmp_path, monkeypatch)
    pipeline = _record_tailor_calls(monkeypatch)

    client = TestClient(create_app(), client=REMOTE_CLIENT)
    response = client.post(
        "/api/paste",
        headers={"Authorization": "Basic secret-abc"},
        json={"jd_text": "Senior Python.\n", "source": "n8n"},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "missing_ingest_token"}
    assert pipeline["called"] is False


def test_non_loopback_without_server_token_returns_401(
    tmp_path, monkeypatch
) -> None:
    """Server has no INGEST_TOKEN configured — non-loopback callers fail loud."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    monkeypatch.delenv("INGEST_TOKEN", raising=False)
    stage_canonical_cv(tmp_path, monkeypatch)
    stage_tailoring(tmp_path, monkeypatch)
    pipeline = _record_tailor_calls(monkeypatch)

    client = TestClient(create_app(), client=REMOTE_CLIENT)
    response = client.post(
        "/api/paste",
        headers={"Authorization": "Bearer any-token"},
        json={"jd_text": "Senior Python.\n", "source": "n8n"},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "ingest_token_not_configured_on_server"}
    assert pipeline["called"] is False


def test_non_loopback_empty_server_token_returns_401(
    tmp_path, monkeypatch
) -> None:
    """Empty INGEST_TOKEN (e.g. the .env.example placeholder) is treated as unset."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    monkeypatch.setenv("INGEST_TOKEN", "   ")
    stage_canonical_cv(tmp_path, monkeypatch)
    stage_tailoring(tmp_path, monkeypatch)
    pipeline = _record_tailor_calls(monkeypatch)

    client = TestClient(create_app(), client=REMOTE_CLIENT)
    response = client.post(
        "/api/paste",
        headers={"Authorization": "Bearer any-token"},
        json={"jd_text": "Senior Python.\n", "source": "n8n"},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "ingest_token_not_configured_on_server"}
    assert pipeline["called"] is False


# --- AC3: body validation preserved (401 fires BEFORE body parsing) --------


def test_auth_fails_before_body_validation(tmp_path, monkeypatch) -> None:
    """A non-loopback caller sending invalid JSON without a token gets 401, not 422.

    The auth dependency runs at the request level, before Pydantic parses the
    body — proving the LLM is unreachable on malformed n8n posts that also
    lack auth.
    """
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    monkeypatch.setenv("INGEST_TOKEN", "secret-abc")
    stage_canonical_cv(tmp_path, monkeypatch)
    stage_tailoring(tmp_path, monkeypatch)
    pipeline = _record_tailor_calls(monkeypatch)

    client = TestClient(create_app(), client=REMOTE_CLIENT)
    response = client.post("/api/paste", json={})
    assert response.status_code == 401
    assert pipeline["called"] is False


def test_authed_non_loopback_with_invalid_body_returns_422(
    tmp_path, monkeypatch
) -> None:
    """With a valid token, body validation still applies."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    monkeypatch.setenv("INGEST_TOKEN", "secret-abc")
    stage_canonical_cv(tmp_path, monkeypatch)
    stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app(), client=REMOTE_CLIENT)
    response = client.post(
        "/api/paste",
        headers={"Authorization": "Bearer secret-abc"},
        json={"jd_text": ""},
    )
    assert response.status_code == 422


# --- AC4: single code path — n8n shape gets the same 200 OK response --------


def test_non_loopback_with_token_and_spec_body_shape_succeeds(
    tmp_path, monkeypatch
) -> None:
    """The spec'd `{jd_text, source_board, metadata}` body returns 200 just like the browser shape."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    monkeypatch.setenv("INGEST_TOKEN", "secret-abc")
    stage_canonical_cv(tmp_path, monkeypatch)
    stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app(), client=REMOTE_CLIENT)
    response = client.post(
        "/api/paste",
        headers={"Authorization": "Bearer secret-abc"},
        json={
            "jd_text": "Senior Python role.\n",
            "source": "n8n",
            "source_board": "upwork",
            "metadata": {"posting_id": "abc-123", "scraped_at": "2026-05-23"},
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body.keys()) == {
        "slug",
        "cv_path",
        "cover_letter_path",
        "cost_usd",
        "status",
        "metadata_path",
        "upwork_proposal_path",
    }
    assert body["cost_usd"] == str(FAKE_COST_USD)


def test_browser_and_n8n_paths_return_equivalent_response_shape(
    tmp_path, monkeypatch
) -> None:
    """Same handler, same response shape, regardless of caller origin."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    monkeypatch.setenv("INGEST_TOKEN", "secret-abc")
    stage_canonical_cv(tmp_path, monkeypatch)
    stage_tailoring(tmp_path, monkeypatch)

    browser_client = TestClient(create_app())
    browser_resp = browser_client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role for browser caller.\n", "source": "browser"},
    )
    assert browser_resp.status_code == 200, browser_resp.text

    n8n_client = TestClient(create_app(), client=REMOTE_CLIENT)
    n8n_resp = n8n_client.post(
        "/api/paste",
        headers={"Authorization": "Bearer secret-abc"},
        json={
            "jd_text": "Senior Rust role for n8n caller.\n",
            "source": "n8n",
            "source_board": "upwork",
            "metadata": {"posting_id": "xyz"},
        },
    )
    assert n8n_resp.status_code == 200, n8n_resp.text
    assert set(browser_resp.json().keys()) == set(n8n_resp.json().keys())


# --- AC5: response shape adds status + metadata_path -----------------------


def test_paste_response_includes_status_and_metadata_path(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    monkeypatch.delenv("INGEST_TOKEN", raising=False)
    stage_canonical_cv(tmp_path, monkeypatch)
    stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior Python.\n", "source": "browser"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "passed"
    assert body["metadata_path"].endswith("metadata.json")
    assert body["slug"] in body["metadata_path"]
