"""POST /api/paste smoke tests for the n8n ingest contract (Story 7.1).

Covers AC1 (shared-token auth for non-loopback n8n calls) and AC2 (canonical
JSON body shape with optional `url` + `discovered_at`). Auth-side regressions
are guarded by `test_paste_auth.py` (Story 2.11); these tests exercise the
new contract surface added by Story 7.1.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from jobhunter.web.api import create_app
from tests.integration._web_helpers import (
    stage_canonical_cv,
    stage_tailoring,
)


REMOTE_CLIENT = ("203.0.113.10", 51422)


# --- AC1: n8n body shape + bearer token returns 200 --------------------------


def test_n8n_body_shape_with_valid_token_returns_200(tmp_path, monkeypatch) -> None:
    """The full n8n body (jd_text + source + url + discovered_at) succeeds."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    monkeypatch.setenv("INGEST_TOKEN", "secret-n8n")
    stage_canonical_cv(tmp_path, monkeypatch)
    stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app(), client=REMOTE_CLIENT)
    response = client.post(
        "/api/paste",
        headers={"Authorization": "Bearer secret-n8n"},
        json={
            "jd_text": "Senior Python role from n8n.\n",
            "source": "upwork",
            "url": "https://example.com/jobs/abc",
            "discovered_at": "2026-05-24T10:15:00Z",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "passed"
    assert body["metadata_path"].endswith("metadata.json")


def test_n8n_body_with_missing_token_returns_401(tmp_path, monkeypatch) -> None:
    """The n8n body shape without the bearer header still 401s (auth runs first)."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    monkeypatch.setenv("INGEST_TOKEN", "secret-n8n")
    stage_canonical_cv(tmp_path, monkeypatch)
    stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app(), client=REMOTE_CLIENT)
    response = client.post(
        "/api/paste",
        json={
            "jd_text": "Senior Python role from n8n.\n",
            "source": "upwork",
            "url": "https://example.com/jobs/abc",
            "discovered_at": "2026-05-24T10:15:00Z",
        },
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "missing_ingest_token"}


def test_n8n_body_missing_jd_text_returns_422(tmp_path, monkeypatch) -> None:
    """Pydantic body validation: missing `jd_text` returns 422 (machine-readable)."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    monkeypatch.setenv("INGEST_TOKEN", "secret-n8n")
    stage_canonical_cv(tmp_path, monkeypatch)
    stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app(), client=REMOTE_CLIENT)
    response = client.post(
        "/api/paste",
        headers={"Authorization": "Bearer secret-n8n"},
        json={
            "source": "upwork",
            "url": "https://example.com/jobs/abc",
            "discovered_at": "2026-05-24T10:15:00Z",
        },
    )
    assert response.status_code == 422


def test_n8n_body_missing_source_returns_422(tmp_path, monkeypatch) -> None:
    """Pydantic body validation: missing `source` returns 422."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    monkeypatch.setenv("INGEST_TOKEN", "secret-n8n")
    stage_canonical_cv(tmp_path, monkeypatch)
    stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app(), client=REMOTE_CLIENT)
    response = client.post(
        "/api/paste",
        headers={"Authorization": "Bearer secret-n8n"},
        json={
            "jd_text": "Senior Python role from n8n.\n",
            "url": "https://example.com/jobs/abc",
        },
    )
    assert response.status_code == 422


# --- AC2: metadata sidecar records source, url, discovered_at ---------------


def test_n8n_upwork_source_records_jd_source_url_and_discovered_at(
    tmp_path, monkeypatch
) -> None:
    """An `upwork` n8n post writes `jd_source: upwork` + `url` + `discovered_at`."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    monkeypatch.setenv("INGEST_TOKEN", "secret-n8n")
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root, _ = stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app(), client=REMOTE_CLIENT)
    response = client.post(
        "/api/paste",
        headers={"Authorization": "Bearer secret-n8n"},
        json={
            "jd_text": "Senior Python role from Upwork.\n",
            "source": "upwork",
            "url": "https://www.example.com/jobs/upwork-1",
            "discovered_at": "2026-05-24T10:15:00Z",
        },
    )
    assert response.status_code == 200, response.text
    slug = response.json()["slug"]
    metadata_path = out_root / slug / "metadata.json"
    data = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert data["jd_source"] == "upwork"
    assert data["url"] == "https://www.example.com/jobs/upwork-1"
    assert data["discovered_at"] == "2026-05-24T10:15:00Z"


def test_n8n_onlinejobs_ph_source_records_jd_source(tmp_path, monkeypatch) -> None:
    """An `onlinejobs_ph` post writes `jd_source: onlinejobs_ph`."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    monkeypatch.setenv("INGEST_TOKEN", "secret-n8n")
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root, _ = stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app(), client=REMOTE_CLIENT)
    response = client.post(
        "/api/paste",
        headers={"Authorization": "Bearer secret-n8n"},
        json={
            "jd_text": "VA role from OJ.ph.\n",
            "source": "onlinejobs_ph",
            "url": "https://example.com/jobs/oj-1",
            "discovered_at": "2026-05-24T10:15:00Z",
        },
    )
    assert response.status_code == 200, response.text
    slug = response.json()["slug"]
    data = json.loads((out_root / slug / "metadata.json").read_text(encoding="utf-8"))
    assert data["jd_source"] == "onlinejobs_ph"


def test_n8n_linkedin_email_source_records_jd_source(tmp_path, monkeypatch) -> None:
    """A `linkedin_email` post writes `jd_source: linkedin_email`."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    monkeypatch.setenv("INGEST_TOKEN", "secret-n8n")
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root, _ = stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app(), client=REMOTE_CLIENT)
    response = client.post(
        "/api/paste",
        headers={"Authorization": "Bearer secret-n8n"},
        json={
            "jd_text": "Senior role from LinkedIn email digest.\n",
            "source": "linkedin_email",
            "url": "https://example.com/jobs/li-1",
            "discovered_at": "2026-05-24T10:15:00Z",
        },
    )
    assert response.status_code == 200, response.text
    slug = response.json()["slug"]
    data = json.loads((out_root / slug / "metadata.json").read_text(encoding="utf-8"))
    assert data["jd_source"] == "linkedin_email"


def test_browser_source_preserves_paste_jd_source(tmp_path, monkeypatch) -> None:
    """The browser path keeps the pre-Story-7.1 `jd_source: paste` mapping."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    monkeypatch.delenv("INGEST_TOKEN", raising=False)
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root, _ = stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role from browser.\n", "source": "browser"},
    )
    assert response.status_code == 200, response.text
    slug = response.json()["slug"]
    data = json.loads((out_root / slug / "metadata.json").read_text(encoding="utf-8"))
    assert data["jd_source"] == "paste"
    assert data["url"] is None
    assert data["discovered_at"] is None


def test_n8n_post_without_optional_url_or_discovered_at_succeeds(
    tmp_path, monkeypatch
) -> None:
    """`url` and `discovered_at` are optional — a minimal n8n post still returns 200."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    monkeypatch.setenv("INGEST_TOKEN", "secret-n8n")
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root, _ = stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app(), client=REMOTE_CLIENT)
    response = client.post(
        "/api/paste",
        headers={"Authorization": "Bearer secret-n8n"},
        json={
            "jd_text": "Minimal n8n payload.\n",
            "source": "upwork",
        },
    )
    assert response.status_code == 200, response.text
    slug = response.json()["slug"]
    data = json.loads((out_root / slug / "metadata.json").read_text(encoding="utf-8"))
    assert data["jd_source"] == "upwork"
    assert data["url"] is None
    assert data["discovered_at"] is None


# --- AC2: docs/n8n-contract.md exists and references INGEST_TOKEN ----------


def test_contract_doc_exists_and_documents_token_aliasing(project_root) -> None:
    """The contract doc is checked in and explains the INGEST_TOKEN naming."""
    doc_path = project_root / "docs" / "n8n-contract.md"
    assert doc_path.is_file()
    contents = doc_path.read_text(encoding="utf-8")
    # AC2: endpoint, headers, body, error matrix, and FR11 statement.
    assert "POST /api/paste" in contents
    assert "INGEST_TOKEN" in contents
    assert "INGEST_SHARED_TOKEN" in contents
    assert "FR11" in contents
    # AC3: the FR11 statement must explicitly call out LinkedIn-email-only.
    assert "email parsing only" in contents.lower()
    assert "401" in contents and "422" in contents
