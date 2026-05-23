"""Story 5.2 end-to-end: dump-paragraph + comma-run detection in POST /api/paste.

Drives the whole pipeline through the FastAPI route and asserts:

- AC5: the matcher's `dump_paragraph_locations[]` carries through the
  pipeline so `metadata.json` records the OR-combined verdict.
- AC6: the verdict is `"fail"` when EITHER density OR placement fires —
  pure-placement-fail (no density violation) still flips the verdict.
- AC7: a five-bullet skills list of pure JD keywords is caught as a
  `comma_run_violation`.

Mirrors `test_keyword_stuffing_in_pipeline.py` patterns. Story 5.3 owns
the `package.drift.json` write contract; this story only owns the
in-memory check.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

import pytest
from fastapi.testclient import TestClient

from jobhunter.claim_extractor import ClaimExtractionResult
from jobhunter.web.api import create_app
from tests.integration._web_helpers import (
    make_fake_parse,
    make_fake_tailor,
    stage_tailoring,
)


# ---- canonical-CV staging -------------------------------------------------


def _minimal_cv() -> dict[str, Any]:
    return {
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
                "highlights": ["Built things."],
            }
        ],
        "skills": [{"name": "Backend", "keywords": ["pytest"]}],
    }


def _stage_canonical_cv_dict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cv: dict[str, Any]
) -> Path:
    cv_path = tmp_path / "canonical-cv.json"
    cv_path.write_text(json.dumps(cv), encoding="utf-8")
    import jobhunter.canonical_cv as reader_module
    import jobhunter.config as config_module

    monkeypatch.setattr(config_module, "CANONICAL_CV_PATH", cv_path)
    monkeypatch.setattr(reader_module, "CANONICAL_CV_PATH", cv_path)
    return cv_path


def _zero_cost_extractor(
    markdown_text: str,
    source_artifact: str,
    *,
    api_key: str,
    timeout_seconds: float,
    prompt: Any,
) -> ClaimExtractionResult:
    """Emit zero claims so fabrication passes — keeps the test focused on
    placement detection."""
    return ClaimExtractionResult(
        claims=[],
        cost_usd=Decimal("0"),
        input_tokens=0,
        output_tokens=0,
    )


def _stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    cv: str,
    cover: str,
    must_haves: list[str],
    extractor: Callable[..., ClaimExtractionResult] | None = None,
):
    import jobhunter.web.api as api_module

    out_root, ledger_path = stage_tailoring(
        tmp_path,
        monkeypatch,
        fake_tailor=make_fake_tailor(cv=cv, cover=cover),
        fake_parse=make_fake_parse(must_haves=must_haves, nice_to_haves=[]),
    )
    inner_run = api_module.run_tailoring
    chosen_extractor = extractor or _zero_cost_extractor

    def wrapped(canonical_cv, jd_text, **kwargs):
        kwargs.setdefault("llm_extract_claims", chosen_extractor)
        return inner_run(canonical_cv, jd_text, **kwargs)

    monkeypatch.setattr(api_module, "run_tailoring", wrapped)
    return out_root, ledger_path


# ---- AC5/AC6: placement-only fail flips the verdict -----------------------


def test_paste_metadata_records_keyword_stuffing_fail_on_dump_paragraph_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC6: a dump paragraph alone (without any density violation) is
    enough to flip `drift_verdicts.keyword_stuffing` to `"fail"`.

    The cv body has one 16-token block where 6 distinct JD must-haves
    cluster (37.5% ratio > 30% default), plus a long filler paragraph so
    each individual keyword's whole-artifact density stays under 1.5%.
    """
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    _stage_canonical_cv_dict(tmp_path, monkeypatch, _minimal_cv())

    filler = " ".join(["alpha"] * 200)
    stuffed_cv = (
        "# CV\n\n"
        "skilled in python django flask postgres redis kafka "
        "across many roles built systems shipped on time\n"
        "\n"
        f"{filler}\n"
    )
    out_root, _ = _stage(
        tmp_path,
        monkeypatch,
        cv=stuffed_cv,
        cover=f"Hi.\n{filler}\n",
        must_haves=["python", "django", "flask", "postgres", "redis", "kafka"],
    )

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior backend role.\n", "source": "browser"},
    )
    assert response.status_code == 200, response.text

    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    metadata = json.loads((slug_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["drift_verdicts"]["keyword_stuffing"] == "fail"


# ---- AC6: pure-density-fail still fails (regression check) ----------------


def test_paste_density_only_fail_still_fails_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC6 the other direction: a density-only fail (no dump paragraph)
    must still flip the verdict — confirms Story 5.1's behavior survives
    the Story 5.2 wrap.
    """
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    _stage_canonical_cv_dict(tmp_path, monkeypatch, _minimal_cv())

    # 10 occurrences of "Python" in a short cv = ~20% density, well over
    # the 1.5% ceiling. But the single paragraph is 17 tokens total with
    # 10 must-haves -> 58.8% ratio, so this ALSO trips placement. To
    # isolate density-only, spread occurrences across multiple short
    # paragraphs so no individual paragraph is a dump.
    cv_body = (
        "# CV\n\n"
        "Python is great.\n"
        "\n"
        "Python is great.\n"
        "\n"
        "Python is great.\n"
        "\n"
        "Python is great.\n"
        "\n"
        "Python is great.\n"
        "\n"
        "Python is great.\n"
        "\n"
        "Python is great.\n"
        "\n"
        "Python is great.\n"
        "\n"
        "Python is great.\n"
        "\n"
        "Python is great.\n"
    )
    out_root, _ = _stage(
        tmp_path,
        monkeypatch,
        cv=cv_body,
        cover="Hello there.\n",
        must_haves=["Python"],
    )

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )
    assert response.status_code == 200

    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    metadata = json.loads((slug_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["drift_verdicts"]["keyword_stuffing"] == "fail"


# ---- AC7: five-bullet skills list -> comma_run_violation ------------------


def test_paste_five_bullet_skills_list_triggers_comma_run_violation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC7: a five-bullet skills list of pure JD keywords flips the
    verdict to `"fail"` — bullet blocks are subject to the comma-run rule.
    """
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    _stage_canonical_cv_dict(tmp_path, monkeypatch, _minimal_cv())

    # Long filler around the bullet block keeps per-keyword density
    # under 1.5% so the verdict's flip is attributable to the comma-run
    # rule alone (no density violation contaminating the result).
    filler = " ".join(["alpha"] * 200)
    cv_body = (
        f"# CV\n\n{filler}\n"
        "\n"
        "## Skills\n"
        "\n"
        "- TypeScript\n"
        "- Node\n"
        "- Kubernetes\n"
        "- GraphQL\n"
        "- Postgres\n"
        "\n"
        f"{filler}\n"
    )
    out_root, _ = _stage(
        tmp_path,
        monkeypatch,
        cv=cv_body,
        cover=f"Hi.\n{filler}\n",
        must_haves=[
            "TypeScript",
            "Node",
            "Kubernetes",
            "GraphQL",
            "Postgres",
        ],
    )

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={"jd_text": "Backend role.\n", "source": "browser"},
    )
    assert response.status_code == 200

    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    metadata = json.loads((slug_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["drift_verdicts"]["keyword_stuffing"] == "fail"


# ---- AC6: clean artifacts -> verdict stays pass ---------------------------


def test_paste_clean_artifacts_stay_pass_under_combined_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC6: no density violations + no placement violations -> verdict
    is `"pass"`. Confirms the OR-combine does not over-flag clean output.
    """
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    _stage_canonical_cv_dict(tmp_path, monkeypatch, _minimal_cv())

    filler = " ".join(["alpha"] * 200)
    cv_body = f"# CV\n\nDave has Python experience. {filler}\n"
    cover_body = f"Hello, Dave has FastAPI experience. {filler}\n"
    out_root, _ = _stage(
        tmp_path,
        monkeypatch,
        cv=cv_body,
        cover=cover_body,
        must_haves=["Python", "FastAPI"],
    )

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )
    assert response.status_code == 200, response.text

    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    metadata = json.loads((slug_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["drift_verdicts"]["keyword_stuffing"] == "pass"
