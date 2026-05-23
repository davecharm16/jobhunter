"""Story 4.1 end-to-end: content-loss check runs in the POST /api/paste pipeline.

Drives the whole pipeline through the FastAPI route with a custom canonical CV
(staged with `highImpact` + `tags` extensions) and asserts:

- AC1: a high-impact entry whose tags overlap the JD's must-haves is in the
  must-appear set; the verdict reads from `metadata.json` afterwards.
- AC2: substring presence of a chunk of the entry's primary_text in any of
  cv.md / cover-letter.md is enough to preserve it.
- AC3: a logged drop in `tailoring.trace.json` with `reason: irrelevant_to_jd`
  flips a missing entry from `silently_lost` to a non-failing drop.
- AC4: `verdict: "fail"` reaches `metadata.json` via
  `drift_verdicts.content_loss`, and the pipeline still returns HTTP 200
  (held-package wiring for content-loss-only fails lands in Story 4.2).
- AC5: zero LLM calls are made during the content-loss check phase. Verified
  by trapping the LLM-client surfaces with `must_not_run` shims that fire
  only after the orchestrator's earlier (already-stubbed) LLM steps.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

import pytest
from fastapi.testclient import TestClient

from jobhunter.claim_extractor import Claim, ClaimExtractionResult
from jobhunter.web.api import create_app
from tests.integration._web_helpers import (
    make_fake_parse,
    make_fake_tailor,
    stage_tailoring,
)


# ---- canonical-CV staging with the Story 2.1 extensions -------------------


def _cv_with_high_impact() -> dict[str, Any]:
    """Canonical CV with one high-impact work entry tagged `typescript`.

    Mirrors the shape `canonical_cv.read_canonical_cv` returns. The `pytest`
    skill is preserved so the autouse fabrication-claim stub still finds a
    canonical source and the fabrication verdict stays `pass`.
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
                "position": "Senior Engineer",
                "startDate": "2020-01-01",
                "tags": ["typescript", "node"],
                "highImpact": True,
                "highlights": [
                    "Shipped a TypeScript ingestion service that cut latency by 60%",
                    "Led the on-call rotation for the payments squad",
                ],
            }
        ],
        "skills": [
            {"name": "Backend", "keywords": ["Python", "pytest"]},
        ],
    }


def _stage_canonical_cv_dict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cv: dict[str, Any]
) -> Path:
    """Write *cv* into tmp_path and point `CANONICAL_CV_PATH` at it."""
    cv_path = tmp_path / "canonical-cv.json"
    cv_path.write_text(json.dumps(cv), encoding="utf-8")
    import jobhunter.canonical_cv as reader_module
    import jobhunter.config as config_module

    monkeypatch.setattr(config_module, "CANONICAL_CV_PATH", cv_path)
    monkeypatch.setattr(reader_module, "CANONICAL_CV_PATH", cv_path)
    return cv_path


# ---- shared stub wiring ---------------------------------------------------


def _make_extractor(claims_by_artifact: dict[str, list[dict[str, Any]]]) -> Callable[..., ClaimExtractionResult]:
    """Yield a fake claim-extractor keyed on source_artifact."""

    def fake_extract(
        markdown_text: str,
        source_artifact: str,
        *,
        api_key: str,
        timeout_seconds: float,
        prompt: Any,
    ) -> ClaimExtractionResult:
        raw = claims_by_artifact.get(source_artifact, [])
        claims = [
            Claim(
                claim_id=f"{source_artifact}:{c['line_number']}:abcdef01",
                claim_type=c["claim_type"],
                claim_text=c["claim_text"],
                source_artifact=source_artifact,
                line_number=c["line_number"],
            )
            for c in raw
        ]
        return ClaimExtractionResult(
            claims=claims,
            cost_usd=Decimal("0.000420"),
            input_tokens=42,
            output_tokens=21,
        )

    return fake_extract


def _stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    cv: str,
    cover: str,
    extractor: Callable[..., ClaimExtractionResult] | None = None,
    parser=None,
):
    """Wire stage_tailoring + the extractor through the FastAPI route."""
    import jobhunter.web.api as api_module

    out_root, ledger_path = stage_tailoring(
        tmp_path,
        monkeypatch,
        fake_tailor=make_fake_tailor(cv=cv, cover=cover),
        fake_parse=parser,
    )
    if extractor is not None:
        inner_run = api_module.run_tailoring

        def wrapped(canonical_cv, jd_text, **kwargs):
            kwargs.setdefault("llm_extract_claims", extractor)
            return inner_run(canonical_cv, jd_text, **kwargs)

        monkeypatch.setattr(api_module, "run_tailoring", wrapped)
    return out_root, ledger_path


def _zero_cost_extractor(
    markdown_text: str,
    source_artifact: str,
    *,
    api_key: str,
    timeout_seconds: float,
    prompt: Any,
) -> ClaimExtractionResult:
    """Emit zero claims so the fabrication matcher passes — keeps the test
    surface narrow to the content-loss check."""
    return ClaimExtractionResult(
        claims=[],
        cost_usd=Decimal("0"),
        input_tokens=0,
        output_tokens=0,
    )


# ---- AC1 + AC2: present entry -> content_loss = pass ----------------------


def test_paste_writes_tailoring_trace_with_empty_dropped_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC3 placeholder shape: `tailoring.trace.json` lands with `dropped_entries: []`."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    _stage_canonical_cv_dict(tmp_path, monkeypatch, _cv_with_high_impact())
    out_root, _ = _stage(
        tmp_path,
        monkeypatch,
        cv="# CV\n\nTypeScript ingestion\n",
        cover="hi\n",
        extractor=_zero_cost_extractor,
        parser=make_fake_parse(must_haves=["typescript"], nice_to_haves=[]),
    )

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior TypeScript role.\n", "source": "browser"},
    )
    assert response.status_code == 200, response.text

    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    trace_path = slug_dir / "tailoring.trace.json"
    assert trace_path.exists()
    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    assert payload == {"dropped_entries": []}
    # Atomic write idiom: no `.tailoring.trace.tmp` left behind.
    assert not (slug_dir / ".tailoring.trace.tmp").exists()


def test_paste_metadata_records_content_loss_pass_when_entry_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC1+AC2 pass: a high-impact JD-relevant entry whose chunk appears in
    cv.md flips `content_loss` from "pending" to "pass"."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    _stage_canonical_cv_dict(tmp_path, monkeypatch, _cv_with_high_impact())
    out_root, _ = _stage(
        tmp_path,
        monkeypatch,
        # Chunk-match the canonical highlight: "Shipped a TypeScript
        # ingestion service that cut latency by 60%".
        cv="# CV\n\n- Shipped a TypeScript ingestion service that cut latency by 60%\n",
        cover="hi\n",
        extractor=_zero_cost_extractor,
        parser=make_fake_parse(must_haves=["typescript"], nice_to_haves=[]),
    )

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior TypeScript role.\n", "source": "browser"},
    )
    assert response.status_code == 200

    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    metadata = json.loads((slug_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["drift_verdicts"]["content_loss"] == "pass"


def test_paste_content_loss_passes_when_chunk_lives_in_cover_letter_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC2: chunk-match in ANY artifact counts as preserved (cv vs cover-letter)."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    _stage_canonical_cv_dict(tmp_path, monkeypatch, _cv_with_high_impact())
    out_root, _ = _stage(
        tmp_path,
        monkeypatch,
        cv="# CV\n\n- unrelated content\n",
        cover="Dear hiring manager, I led the on-call rotation for the payments squad.\n",
        extractor=_zero_cost_extractor,
        parser=make_fake_parse(must_haves=["typescript"], nice_to_haves=[]),
    )

    client = TestClient(create_app())
    client.post(
        "/api/paste",
        json={"jd_text": "Senior TypeScript role.\n", "source": "browser"},
    )

    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    metadata = json.loads((slug_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["drift_verdicts"]["content_loss"] == "pass"


# ---- AC4: silent loss -> fail + 200 status --------------------------------


def test_paste_metadata_records_content_loss_fail_on_silent_loss(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC4 fail: a JD-relevant high-impact entry absent from every artifact
    with no logged rationale flips `content_loss` to "fail"."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    _stage_canonical_cv_dict(tmp_path, monkeypatch, _cv_with_high_impact())
    out_root, _ = _stage(
        tmp_path,
        monkeypatch,
        cv="# CV\n\n- completely unrelated content\n",
        cover="Dear hiring manager, generic boilerplate.\n",
        extractor=_zero_cost_extractor,
        parser=make_fake_parse(must_haves=["typescript"], nice_to_haves=[]),
    )

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior TypeScript role.\n", "source": "browser"},
    )
    # AC4: pipeline still returns 200; the verdict is metadata-only for v1.
    # Story 4.2 will wire the held-package extension for content-loss fails.
    assert response.status_code == 200

    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    metadata = json.loads((slug_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["drift_verdicts"]["content_loss"] == "fail"


def test_paste_content_loss_pass_when_no_jd_overlap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC1 negative: if the only high-impact entry's tags do not overlap the
    JD's must/nice-haves, the must-appear set is empty and the verdict is
    `pass` regardless of the artifact text."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    _stage_canonical_cv_dict(tmp_path, monkeypatch, _cv_with_high_impact())
    out_root, _ = _stage(
        tmp_path,
        monkeypatch,
        cv="# CV\n\n- nothing relevant\n",
        cover="boilerplate\n",
        extractor=_zero_cost_extractor,
        parser=make_fake_parse(must_haves=["Rust"], nice_to_haves=["Haskell"]),
    )

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior Rust role.\n", "source": "browser"},
    )
    assert response.status_code == 200

    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    metadata = json.loads((slug_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["drift_verdicts"]["content_loss"] == "pass"


# ---- AC3 end-to-end: logged rationale exempts from fail -------------------


def test_paste_logged_irrelevant_drop_in_trace_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC3 end-to-end: an authored `dropped_entries[]` rationale in the trace
    flips a missing entry from `silently_lost` to a non-failing drop.

    The orchestrator writes the trace with an empty `dropped_entries[]` and
    then runs the check. This test patches `_write_tailoring_trace` to seed
    a logged rationale BEFORE the check runs, simulating a future tailoring
    step (or manual edit) that populated the trace.
    """
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    _stage_canonical_cv_dict(tmp_path, monkeypatch, _cv_with_high_impact())

    # Compute the entry_id the matcher will assign to the high-impact work
    # entry so the trace can target it.
    from jobhunter.content_loss_matcher import iter_high_impact_relevant

    relevant = iter_high_impact_relevant(
        _cv_with_high_impact(),
        {"must_haves": ["typescript"], "nice_to_haves": []},
    )
    assert len(relevant) == 1
    target_entry_id = relevant[0].entry_id

    import jobhunter.tailoring as tailoring_module

    original_write_trace = tailoring_module._write_tailoring_trace

    def patched_write_trace(out_dir: Path):
        path = original_write_trace(out_dir)
        # Overwrite the empty placeholder with a logged-rationale trace.
        path.write_text(
            json.dumps(
                {
                    "dropped_entries": [
                        {
                            "entry_id": target_entry_id,
                            "reason": "irrelevant_to_jd",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        return path

    monkeypatch.setattr(
        tailoring_module, "_write_tailoring_trace", patched_write_trace
    )

    out_root, _ = _stage(
        tmp_path,
        monkeypatch,
        cv="# CV\n\n- nothing relevant\n",
        cover="boilerplate\n",
        extractor=_zero_cost_extractor,
        parser=make_fake_parse(must_haves=["typescript"], nice_to_haves=[]),
    )

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior TypeScript role.\n", "source": "browser"},
    )
    assert response.status_code == 200

    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    metadata = json.loads((slug_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["drift_verdicts"]["content_loss"] == "pass"


def test_paste_unknown_reason_code_in_trace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC3: an unknown reason string is treated as `silently_lost` and fails."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    _stage_canonical_cv_dict(tmp_path, monkeypatch, _cv_with_high_impact())

    from jobhunter.content_loss_matcher import iter_high_impact_relevant

    relevant = iter_high_impact_relevant(
        _cv_with_high_impact(),
        {"must_haves": ["typescript"], "nice_to_haves": []},
    )
    target_entry_id = relevant[0].entry_id

    import jobhunter.tailoring as tailoring_module

    original_write_trace = tailoring_module._write_tailoring_trace

    def patched_write_trace(out_dir: Path):
        path = original_write_trace(out_dir)
        path.write_text(
            json.dumps(
                {
                    "dropped_entries": [
                        {
                            "entry_id": target_entry_id,
                            "reason": "weird_invented_code",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        return path

    monkeypatch.setattr(
        tailoring_module, "_write_tailoring_trace", patched_write_trace
    )

    out_root, _ = _stage(
        tmp_path,
        monkeypatch,
        cv="# CV\n\n- nothing\n",
        cover="hi\n",
        extractor=_zero_cost_extractor,
        parser=make_fake_parse(must_haves=["typescript"], nice_to_haves=[]),
    )

    client = TestClient(create_app())
    client.post(
        "/api/paste",
        json={"jd_text": "Senior TypeScript role.\n", "source": "browser"},
    )

    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    metadata = json.loads((slug_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["drift_verdicts"]["content_loss"] == "fail"


# ---- AC5: no LLM call from the content-loss step --------------------------


def test_paste_content_loss_step_makes_no_llm_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC5: monkeypatch every LLM client surface to record calls; assert the
    content-loss step does not increment the counter beyond the already-known
    earlier LLM stubs.

    Strategy: count how many times `jobhunter.content_loss_matcher.run_check`
    is invoked (the matcher entry) and tally how many LLM-client calls occur
    AFTER that point. The orchestrator runs the matcher inline, so any LLM
    call after the matcher returns would be a regression — there should be
    zero such calls because `build_metadata` + `write_sidecar` are pure.
    """
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    _stage_canonical_cv_dict(tmp_path, monkeypatch, _cv_with_high_impact())

    # Counter: increments every time a "live" LLM client surface is touched
    # at or after the content-loss matcher invocation.
    state = {"matcher_started": False, "llm_calls_after_matcher": 0}

    import jobhunter.content_loss_matcher as matcher_module
    import jobhunter.llm_client as llm_module

    original_run_check = matcher_module.run_check

    def patched_run_check(*args: Any, **kwargs: Any):
        state["matcher_started"] = True
        return original_run_check(*args, **kwargs)

    monkeypatch.setattr(matcher_module, "run_check", patched_run_check)
    import jobhunter.tailoring as tailoring_module

    monkeypatch.setattr(
        tailoring_module.content_loss_matcher, "run_check", patched_run_check
    )

    def make_trap(name: str):
        def trap(*args: Any, **kwargs: Any):
            if state["matcher_started"]:
                state["llm_calls_after_matcher"] += 1
            raise AssertionError(
                f"LLM client surface `{name}` was invoked during/after "
                "the content-loss check"
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

    out_root, _ = _stage(
        tmp_path,
        monkeypatch,
        cv="# CV\n\n- Shipped a TypeScript ingestion service\n",
        cover="hi\n",
        extractor=_zero_cost_extractor,
        parser=make_fake_parse(must_haves=["typescript"], nice_to_haves=[]),
    )

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior TypeScript role.\n", "source": "browser"},
    )
    assert response.status_code == 200
    # Both: the matcher ran AND zero LLM calls happened after it started.
    assert state["matcher_started"] is True
    assert state["llm_calls_after_matcher"] == 0


def test_paste_content_loss_step_adds_no_extra_cost_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC5 stronger check: the per-request token log (cost.calls) has the
    same purpose distribution after Story 4.1 as it would without the
    check — no new entries with `purpose = content_loss*`.
    """
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    _stage_canonical_cv_dict(tmp_path, monkeypatch, _cv_with_high_impact())
    out_root, _ = _stage(
        tmp_path,
        monkeypatch,
        cv="# CV\n\n- Shipped a TypeScript ingestion service\n",
        cover="hi\n",
        extractor=_zero_cost_extractor,
        parser=make_fake_parse(must_haves=["typescript"], nice_to_haves=[]),
    )

    client = TestClient(create_app())
    client.post(
        "/api/paste",
        json={"jd_text": "Senior TypeScript role.\n", "source": "browser"},
    )
    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    metadata = json.loads((slug_dir / "metadata.json").read_text(encoding="utf-8"))
    purposes = {call["purpose"] for call in metadata["cost"]["calls"]}
    # The known Epic 1-3 purposes: tailor + N extract_claims. No
    # "content_loss" purpose is permitted (AC5).
    assert all("content_loss" not in p for p in purposes)
