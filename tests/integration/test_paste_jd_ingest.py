"""POST /api/paste JD-ingest tests.

Mirrors the role of the Story 1.4 CLI tests: env-gate, empty-body, encoding,
and source-attribution behaviors at the HTTP boundary. Uses FastAPI's
`TestClient` so no real socket opens.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from tests.integration._web_helpers import (
    stage_canonical_cv,
    stage_tailoring,
)

from jobhunter.config import PROJECT_ROOT
from jobhunter.web.api import create_app

# --- AC11 forbidden-imports static guardrail -------------------------------


def test_jobhunter_source_does_not_import_forbidden_runtime_deps() -> None:
    """No HTTP client, no CLI framework, no second LLM SDK in src/jobhunter/.

    The LLM SDK (`anthropic`) is allowed in `llm_client.py` only. FastAPI,
    starlette, pydantic, and uvicorn are the web surface — permitted only
    inside `web/`. Everything else stays stdlib-only.
    """
    src_root = PROJECT_ROOT / "src" / "jobhunter"
    forbidden = [
        "import click",
        "from click",
        "import typer",
        "from typer",
        "import rich",
        "from rich",
        "import requests",
        "from requests",
        "import urllib.request",
        "from urllib.request",
        "import openai",
        "from openai",
    ]

    for py_path in sorted(src_root.rglob("*.py")):
        src = py_path.read_text(encoding="utf-8")
        for needle in forbidden:
            assert needle not in src, (
                f"{py_path.relative_to(PROJECT_ROOT)} must not contain "
                f"`{needle}` (AC11)."
            )

        if py_path.name == "llm_client.py":
            continue
        for needle in ("import anthropic", "from anthropic"):
            assert needle not in src, (
                f"{py_path.relative_to(PROJECT_ROOT)} must not contain "
                f"`{needle}` — the LLM SDK is permitted only in llm_client.py."
            )


def test_no_job_board_hostnames_in_jobhunter_source() -> None:
    src_root = PROJECT_ROOT / "src" / "jobhunter"
    for host in ("upwork.com", "linkedin.com", "onlinejobs.ph"):
        for py_path in sorted(src_root.rglob("*.py")):
            src = py_path.read_text(encoding="utf-8").lower()
            assert host not in src, (
                f"{py_path.relative_to(PROJECT_ROOT)} contains forbidden "
                f"hostname `{host}` (FR44/FR11)."
            )


def test_gitignore_excludes_cost_ledger_and_out_directory() -> None:
    content = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    lines = {line.strip() for line in content.splitlines() if line.strip()}
    assert ".cost-ledger.json" in lines
    assert "out/" in lines


# --- Env-gate paths ---------------------------------------------------------


def test_paste_missing_llm_key_returns_500_and_writes_nothing(
    tmp_path, monkeypatch,
) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root, ledger_path = stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app(), raise_server_exceptions=False)
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )
    assert response.status_code == 500
    assert "LLM_API_KEY" in response.json()["detail"]
    assert not out_root.exists()
    assert not ledger_path.exists()


def test_paste_missing_cap_returns_500_and_writes_nothing(
    tmp_path, monkeypatch,
) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.delenv("MONTHLY_SPEND_CAP_USD", raising=False)
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root, _ = stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app(), raise_server_exceptions=False)
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )
    assert response.status_code == 500
    assert "MONTHLY_SPEND_CAP_USD" in response.json()["detail"]
    assert not out_root.exists()


def test_paste_invalid_cap_returns_500(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "0")
    stage_canonical_cv(tmp_path, monkeypatch)
    stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app(), raise_server_exceptions=False)
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )
    assert response.status_code == 500
    assert "MONTHLY_SPEND_CAP_USD" in response.json()["detail"]


# --- Body validation -------------------------------------------------------


def test_paste_empty_jd_text_is_rejected(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app())
    response = client.post("/api/paste", json={"jd_text": "", "source": "browser"})
    # Pydantic min_length=1 fails fast as 422.
    assert response.status_code == 422


def test_paste_whitespace_only_jd_returns_400(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app())
    response = client.post(
        "/api/paste", json={"jd_text": "   \n\t\n", "source": "browser"}
    )
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


def test_paste_missing_source_field_is_rejected(tmp_path, monkeypatch) -> None:
    stage_canonical_cv(tmp_path, monkeypatch)
    stage_tailoring(tmp_path, monkeypatch)
    client = TestClient(create_app())
    response = client.post("/api/paste", json={"jd_text": "Senior Python.\n"})
    assert response.status_code == 422


# --- Unicode end-to-end ----------------------------------------------------


def test_paste_unicode_jd_round_trips_to_tailoring(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)

    seen: dict[str, str] = {}

    def capturing_tailor(canonical_cv, jd_text, *, api_key, timeout_seconds):
        from decimal import Decimal as _Decimal

        from jobhunter.llm_client import TailoringResult

        seen["jd"] = jd_text
        return TailoringResult(
            cv_markdown="# CV\n",
            cover_letter_markdown="cover\n",
            cost_usd=_Decimal("0.0042"),
            input_tokens=10,
            output_tokens=5,
        )

    stage_tailoring(tmp_path, monkeypatch, fake_tailor=capturing_tailor)

    client = TestClient(create_app())
    jd_text = "Senior Python — café 🚀 €100k\n"
    response = client.post(
        "/api/paste", json={"jd_text": jd_text, "source": "browser"}
    )
    assert response.status_code == 200
    assert seen["jd"] == jd_text
