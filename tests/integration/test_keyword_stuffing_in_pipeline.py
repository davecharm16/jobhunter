"""Story 5.1 end-to-end: keyword-stuffing density check runs in POST /api/paste.

Drives the whole pipeline through the FastAPI route and asserts:

- AC4: per-artifact evaluation — 2 occurrences in cv.md + 2 in
  cover-letter.md does NOT cross the default 3-rep ceiling because each
  file is evaluated independently.
- Tailoring integration: `metadata.json` carries
  `drift_verdicts.keyword_stuffing` as `"pass"` or `"fail"` (depending on
  whether artifacts breach the per-keyword thresholds).
- AC8: no LLM client surface is invoked during the keyword-stuffing
  check.
- Story 5.3 boundary: this story does NOT write
  `package.drift.json.keyword_stuffing` or extend the held-package
  writer; we assert the file/sidecar still match the Story 4.2 shape.
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
    """Smallest canonical-CV shape the pipeline accepts; no high-impact tags.

    Keyword-stuffing measures the tailored artifacts against the JD's
    `must_haves[]` — the canonical CV's contents are irrelevant to the
    check itself, so we stage the simplest possible shape that the
    canonical_cv reader accepts.
    """
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
    """Emit zero claims so the fabrication matcher passes — keeps the test
    surface narrow to the keyword-stuffing check."""
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
    """Wire stage_tailoring + extractor through the FastAPI route."""
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


# ---- AC pass case: artifacts clean -> keyword_stuffing = pass -------------


def test_paste_metadata_records_keyword_stuffing_pass_on_clean_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Clean artifacts (each must-have appears once in a long body) yield
    verdict=pass — 1 occurrence in a 200-token cv = 0.5% density, well
    under the 1.5% default ceiling."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    _stage_canonical_cv_dict(tmp_path, monkeypatch, _minimal_cv())
    # ~200 filler tokens so 1 mention of each must-have stays under 1.5%.
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


# ---- AC2 fail case: density breach -> keyword_stuffing = fail -------------


def test_paste_metadata_records_keyword_stuffing_fail_on_density_breach(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A keyword that exceeds the 1.5% default density ceiling on cv.md
    flips `keyword_stuffing` from `pending` to `fail`."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    _stage_canonical_cv_dict(tmp_path, monkeypatch, _minimal_cv())
    # 10 occurrences of "Python" in a ~50-token cv = ~20% density, well
    # over the 1.5% ceiling.
    stuffed_cv = (
        "# CV\n\n"
        "I am Python Python Python Python Python Python Python Python "
        "Python Python and I love writing code.\n"
    )
    out_root, _ = _stage(
        tmp_path,
        monkeypatch,
        cv=stuffed_cv,
        cover="Hello there.\n",
        must_haves=["Python"],
    )

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )
    # Story 5.1 does NOT extend the held-package writer — the pipeline
    # still returns 200; the verdict only reaches `drift_verdicts` on
    # metadata.json. (Story 5.3 will wire the held-package extension.)
    assert response.status_code == 200

    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    metadata = json.loads((slug_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["drift_verdicts"]["keyword_stuffing"] == "fail"


# ---- AC4: per-artifact evaluation (not summed across files) ---------------


def test_paste_keyword_stuffing_does_not_sum_across_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC4: 2 in cv.md + 2 in cover-letter.md must NOT trigger a repetition
    violation; each file is under the 3-rep ceiling independently."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    _stage_canonical_cv_dict(tmp_path, monkeypatch, _minimal_cv())

    # Each artifact gets exactly 2 occurrences of "python" inside a long
    # corpus so the density stays under 1.5% per artifact AND each is at
    # 2/3 reps — combined they would be 4 (> 3), but AC4 forbids summing.
    filler = " ".join(["alpha"] * 200)
    cv_body = f"# CV\n\nDave has Python skills. Python is great. {filler}\n"
    cover_body = (
        f"Dear hiring manager, Python is my main language. "
        f"I love Python. {filler}\n"
    )
    out_root, _ = _stage(
        tmp_path,
        monkeypatch,
        cv=cv_body,
        cover=cover_body,
        must_haves=["Python"],
    )

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={"jd_text": "Python role.\n", "source": "browser"},
    )
    assert response.status_code == 200

    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    metadata = json.loads((slug_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["drift_verdicts"]["keyword_stuffing"] == "pass"


# ---- AC8: no LLM call from the keyword-stuffing step ----------------------


def test_paste_keyword_stuffing_step_makes_no_llm_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC8: monkeypatch every LLM client surface to record calls; assert no
    LLM surface fires during or after the keyword-stuffing matcher runs.

    Mirrors the Story 4.1 `test_paste_content_loss_step_makes_no_llm_call`
    strategy: count how many LLM-client calls occur AT OR AFTER the
    matcher entry.
    """
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    _stage_canonical_cv_dict(tmp_path, monkeypatch, _minimal_cv())

    state = {
        "matcher_started": False,
        "llm_calls_after_matcher": 0,
    }

    import jobhunter.keyword_stuffing_matcher as matcher_module
    import jobhunter.llm_client as llm_module
    import jobhunter.tailoring as tailoring_module

    original_run = matcher_module.run_density_check

    def patched_run(*args: Any, **kwargs: Any):
        state["matcher_started"] = True
        return original_run(*args, **kwargs)

    monkeypatch.setattr(matcher_module, "run_density_check", patched_run)
    monkeypatch.setattr(
        tailoring_module.keyword_stuffing_matcher,
        "run_density_check",
        patched_run,
    )

    def make_trap(name: str):
        def trap(*args: Any, **kwargs: Any):
            if state["matcher_started"]:
                state["llm_calls_after_matcher"] += 1
            raise AssertionError(
                f"LLM client surface `{name}` was invoked during/after "
                "the keyword-stuffing check"
            )

        return trap

    monkeypatch.setattr(llm_module, "tailor", make_trap("tailor"), raising=False)
    monkeypatch.setattr(
        llm_module, "parse_jd", make_trap("parse_jd"), raising=False
    )
    monkeypatch.setattr(
        llm_module,
        "tailor_upwork_proposal",
        make_trap("tailor_upwork_proposal"),
        raising=False,
    )

    # Use a long body so a single mention of each must-have stays under
    # the 1.5% density ceiling — the LLM-trap test is verdict-agnostic
    # but a clean pass makes the assertion intent clearer.
    filler = " ".join(["alpha"] * 200)
    cv_body = f"# CV\n\nDave has Python and Docker skills. {filler}\n"
    out_root, _ = _stage(
        tmp_path,
        monkeypatch,
        cv=cv_body,
        cover="Hi.\n",
        must_haves=["Python", "Docker"],
    )

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={"jd_text": "Python role.\n", "source": "browser"},
    )
    assert response.status_code == 200
    assert state["matcher_started"] is True
    assert state["llm_calls_after_matcher"] == 0


def test_paste_keyword_stuffing_step_adds_no_extra_cost_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC8 stronger check: the per-request `cost.calls[]` log carries no
    entry with a `purpose` referencing the keyword-stuffing check."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    _stage_canonical_cv_dict(tmp_path, monkeypatch, _minimal_cv())
    out_root, _ = _stage(
        tmp_path,
        monkeypatch,
        cv="# CV\n\nDave has Python skills.\n",
        cover="Hi.\n",
        must_haves=["Python"],
    )

    client = TestClient(create_app())
    client.post(
        "/api/paste",
        json={"jd_text": "Python role.\n", "source": "browser"},
    )

    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    metadata = json.loads((slug_dir / "metadata.json").read_text(encoding="utf-8"))
    purposes = {call["purpose"] for call in metadata["cost"]["calls"]}
    assert all("keyword_stuffing" not in p for p in purposes)


# ---- Story 5.3 update: this story DOES write drift.json keyword block ----


def test_story_5_1_writes_keyword_stuffing_block_in_drift_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Story 5.3: `package.drift.json.keyword_stuffing` is now written on
    every run (pass or fail). Originally a boundary test asserting Story 5.1
    did NOT write it; reframed when Story 5.3 landed the writer.
    """
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    _stage_canonical_cv_dict(tmp_path, monkeypatch, _minimal_cv())
    out_root, _ = _stage(
        tmp_path,
        monkeypatch,
        cv="# CV\n\nDave has Python skills.\n",
        cover="Hi.\n",
        must_haves=["Python"],
    )

    client = TestClient(create_app())
    client.post(
        "/api/paste",
        json={"jd_text": "Python role.\n", "source": "browser"},
    )

    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    drift = json.loads((slug_dir / "package.drift.json").read_text(encoding="utf-8"))
    # Story 5.3 AC1: keyword_stuffing block coexists with fabrication_check + content_loss.
    assert "keyword_stuffing" in drift
    assert "fabrication_check" in drift
    assert "content_loss" in drift


def test_story_5_3_density_fail_produces_held_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Story 5.3 AC4: a keyword-stuffing-only fail now produces a
    `package.held.json` (previously Story 5.1 explicitly did not). The
    held sidecar carries the new `keyword_stuffing_violations[]` field.
    """
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    _stage_canonical_cv_dict(tmp_path, monkeypatch, _minimal_cv())
    # Massively stuffed cv to guarantee density-fail.
    stuffed_cv = "# CV\n\n" + " ".join(["Python"] * 20) + " I love coding.\n"
    out_root, _ = _stage(
        tmp_path,
        monkeypatch,
        cv=stuffed_cv,
        cover="hello\n",
        must_haves=["Python"],
    )

    client = TestClient(create_app())
    client.post(
        "/api/paste",
        json={"jd_text": "Python role.\n", "source": "browser"},
    )

    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    metadata = json.loads((slug_dir / "metadata.json").read_text(encoding="utf-8"))
    # Verdict still reaches metadata.json (Story 5.1 deliverable preserved).
    assert metadata["drift_verdicts"]["keyword_stuffing"] == "fail"
    # Story 5.3 AC4: held sidecar now produced on keyword-stuffing-only fail.
    assert metadata["held"] is True
    assert (slug_dir / "package.held.json").exists()
    held = json.loads((slug_dir / "package.held.json").read_text(encoding="utf-8"))
    assert len(held["keyword_stuffing_violations"]) >= 1
