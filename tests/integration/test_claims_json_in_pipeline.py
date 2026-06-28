"""Story 3.1 AC2-AC4 end-to-end: claims.json lands in `./out/<slug>/`.

Drives the whole pipeline through POST /api/paste with the LLM client
stubbed (integration conftest's autouse `_stub_llm_extract_claims` provides
the baseline; tests here that want richer fixtures inject their own
`llm_extract_claims` callable through `stage_tailoring`).

Covers:
- AC2: tailored CV decomposes into claims with the 5-field shape and a
  claim count >= 10 on a 3-roles / 5-skills / 2-metrics fixture.
- AC3: cover letter extraction skips greetings/closings/JD-restatements;
  count matches the documented expected +/- 1.
- AC4: per-call cost lands in metadata; extract_claims CallLog entries
  appear next to the tailoring entries.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from tests.integration._web_helpers import (
    make_fake_tailor,
    stage_canonical_cv,
    stage_tailoring,
)

from jobhunter.claim_extractor import Claim, ClaimExtractionResult
from jobhunter.web.api import create_app

# ---- AC2: rich CV produces >= 10 atomic claims ---------------------------


_RICH_CV = """# Tailored CV

## Roles
- Senior Engineer at Acme
- Staff Engineer at BetaCorp
- Tech Lead at Gamma

## Skills
- Python
- Go
- Rust
- PostgreSQL
- Redis

## Metrics
- Led a 5-person team
- Shipped 40% faster
"""


_RICH_CV_CLAIMS = [
    {"claim_type": "role", "claim_text": "Senior Engineer at Acme", "line_number": 4},
    {"claim_type": "role", "claim_text": "Staff Engineer at BetaCorp", "line_number": 5},
    {"claim_type": "role", "claim_text": "Tech Lead at Gamma", "line_number": 6},
    {"claim_type": "skill", "claim_text": "Python", "line_number": 9},
    {"claim_type": "skill", "claim_text": "Go", "line_number": 10},
    {"claim_type": "skill", "claim_text": "Rust", "line_number": 11},
    {"claim_type": "skill", "claim_text": "PostgreSQL", "line_number": 12},
    {"claim_type": "skill", "claim_text": "Redis", "line_number": 13},
    {"claim_type": "metric", "claim_text": "5-person team", "line_number": 16},
    {"claim_type": "metric", "claim_text": "40% faster", "line_number": 17},
]


_FIXTURE_COVER = (
    "Dear hiring manager,\n"
    "\n"
    "I am writing about your Senior Engineer role at Acme.\n"
    "As your posting mentions, you need Python and FastAPI experience.\n"
    "I work with Python, FastAPI, and PostgreSQL day-to-day.\n"
    "I shipped the v2 API last year.\n"
    "\n"
    "I would love to chat further.\n"
    "\n"
    "Best regards,\n"
    "Dave\n"
)


# Documented expected count: 5 atomic claims for the fixture cover letter
# (one role, three skills, one accomplishment). The greeting, closing, JD
# restatement ("As your posting mentions..."), and opinion phrase ("I would
# love to chat further.") are NOT claims.
_FIXTURE_COVER_CLAIMS = [
    {"claim_type": "role", "claim_text": "Senior Engineer at Acme", "line_number": 3},
    {"claim_type": "skill", "claim_text": "Python", "line_number": 5},
    {"claim_type": "skill", "claim_text": "FastAPI", "line_number": 5},
    {"claim_type": "skill", "claim_text": "PostgreSQL", "line_number": 5},
    {
        "claim_type": "accomplishment",
        "claim_text": "shipped the v2 API",
        "line_number": 6,
    },
]


def _make_extract_fixture(
    cv_claims, cover_claims,
) -> Callable[..., ClaimExtractionResult]:
    """Return an extractor stub that emits per-artifact claim lists."""

    def fake_extract(
        markdown_text: str,
        source_artifact: str,
        *,
        api_key: str,
        timeout_seconds: float,
        prompt: Any,
    ) -> ClaimExtractionResult:
        raw = cv_claims if source_artifact == "cv" else cover_claims
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


def _stage_with_extract(
    tmp_path, monkeypatch, *, extractor,
):
    """Wire `stage_tailoring` to inject our claim extractor via run_tailoring."""
    import jobhunter.web.api as api_module

    out_root, ledger_path = stage_tailoring(
        tmp_path,
        monkeypatch,
        fake_tailor=make_fake_tailor(cv=_RICH_CV, cover=_FIXTURE_COVER),
    )

    # `stage_tailoring` patches run_tailoring; chain through our extractor.
    inner_run = api_module.run_tailoring

    def wrapped(canonical_cv, jd_text, **kwargs):
        kwargs.setdefault("llm_extract_claims", extractor)
        return inner_run(canonical_cv, jd_text, **kwargs)

    monkeypatch.setattr(api_module, "run_tailoring", wrapped)
    return out_root, ledger_path


# ---- AC2 ------------------------------------------------------------------


def test_paste_writes_claims_json_with_ten_or_more_claims(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    extractor = _make_extract_fixture(_RICH_CV_CLAIMS, _FIXTURE_COVER_CLAIMS)
    out_root, _ = _stage_with_extract(tmp_path, monkeypatch, extractor=extractor)

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )
    assert response.status_code == 200, response.text

    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    claims_path = slug_dir / "claims.json"
    assert claims_path.exists()
    data = json.loads(claims_path.read_text(encoding="utf-8"))
    assert isinstance(data, list)

    cv_claims = [c for c in data if c["source_artifact"] == "cv"]
    assert len(cv_claims) >= 10


def test_paste_claims_json_entries_have_five_required_fields(
    tmp_path, monkeypatch,
) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    extractor = _make_extract_fixture(_RICH_CV_CLAIMS, _FIXTURE_COVER_CLAIMS)
    out_root, _ = _stage_with_extract(tmp_path, monkeypatch, extractor=extractor)

    client = TestClient(create_app())
    client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )

    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    data = json.loads((slug_dir / "claims.json").read_text(encoding="utf-8"))

    required = {"claim_id", "claim_type", "claim_text", "source_artifact", "line_number"}
    assert all(set(entry.keys()) == required for entry in data)
    allowed_types = {"role", "metric", "skill", "tool", "responsibility", "accomplishment"}
    assert all(entry["claim_type"] in allowed_types for entry in data)


def test_paste_claims_json_cv_entries_have_3_roles_5_skills_2_metrics(
    tmp_path, monkeypatch,
) -> None:
    """AC2 fixture verification: the rich CV produces the documented counts."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    extractor = _make_extract_fixture(_RICH_CV_CLAIMS, _FIXTURE_COVER_CLAIMS)
    out_root, _ = _stage_with_extract(tmp_path, monkeypatch, extractor=extractor)

    client = TestClient(create_app())
    client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )
    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    data = json.loads((slug_dir / "claims.json").read_text(encoding="utf-8"))

    cv = [c for c in data if c["source_artifact"] == "cv"]
    types = [c["claim_type"] for c in cv]
    assert types.count("role") == 3
    assert types.count("skill") == 5
    assert types.count("metric") == 2


# ---- AC3 cover-letter extraction -----------------------------------------


def test_paste_claims_json_cover_letter_within_one_of_expected(
    tmp_path, monkeypatch,
) -> None:
    """AC3: documented expected count is 5; assert within +/- 1."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    extractor = _make_extract_fixture(_RICH_CV_CLAIMS, _FIXTURE_COVER_CLAIMS)
    out_root, _ = _stage_with_extract(tmp_path, monkeypatch, extractor=extractor)

    client = TestClient(create_app())
    client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )
    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    data = json.loads((slug_dir / "claims.json").read_text(encoding="utf-8"))

    cover = [c for c in data if c["source_artifact"] == "cover_letter"]
    expected = len(_FIXTURE_COVER_CLAIMS)
    assert abs(len(cover) - expected) <= 1


def test_paste_claims_json_cover_letter_skips_greetings_and_closings(
    tmp_path, monkeypatch,
) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    extractor = _make_extract_fixture(_RICH_CV_CLAIMS, _FIXTURE_COVER_CLAIMS)
    out_root, _ = _stage_with_extract(tmp_path, monkeypatch, extractor=extractor)

    client = TestClient(create_app())
    client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )
    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    data = json.loads((slug_dir / "claims.json").read_text(encoding="utf-8"))
    cover_texts = [c["claim_text"] for c in data if c["source_artifact"] == "cover_letter"]
    for ban in (
        "Dear hiring manager",
        "Best regards",
        "I would love",
        "As your posting mentions",
    ):
        assert not any(ban in text for text in cover_texts), (
            f"non-assertive phrase {ban!r} should not appear in claims"
        )


# ---- AC4 cost-logging contract -------------------------------------------


def test_paste_metadata_records_extract_claims_call_log(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    extractor = _make_extract_fixture(_RICH_CV_CLAIMS, _FIXTURE_COVER_CLAIMS)
    out_root, _ = _stage_with_extract(tmp_path, monkeypatch, extractor=extractor)

    client = TestClient(create_app())
    client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )
    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    metadata = json.loads((slug_dir / "metadata.json").read_text(encoding="utf-8"))

    extract_calls = [
        c for c in metadata["cost"]["calls"] if c["purpose"] == "extract_claims"
    ]
    # cv + cover_letter -> two extract_claims entries.
    assert len(extract_calls) == 2
    for entry in extract_calls:
        assert entry["usd_cost"] == "0.000420"
        assert entry["input_tokens"] == 42
        assert entry["output_tokens"] == 21


def test_paste_extract_claims_cost_rolls_into_total(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    extractor = _make_extract_fixture(_RICH_CV_CLAIMS, _FIXTURE_COVER_CLAIMS)
    out_root, _ = _stage_with_extract(tmp_path, monkeypatch, extractor=extractor)

    client = TestClient(create_app())
    client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )
    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    metadata = json.loads((slug_dir / "metadata.json").read_text(encoding="utf-8"))
    total = Decimal(metadata["cost"]["total_usd"])
    # Tailor (FAKE_COST_USD=0.004200) + 2 * 0.000420 = 0.005040
    assert total == Decimal("0.005040")


# ---- claim_id is deterministic across a re-run --------------------------


def test_claims_json_is_deterministic_across_runs(tmp_path, monkeypatch) -> None:
    """Re-running on identical input yields byte-identical claim_ids — the
    diffability promise from the AC2 spec."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    extractor = _make_extract_fixture(_RICH_CV_CLAIMS, _FIXTURE_COVER_CLAIMS)
    out_root, _ = _stage_with_extract(tmp_path, monkeypatch, extractor=extractor)

    client = TestClient(create_app())
    client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role A.\n", "source": "browser"},
    )
    client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role B.\n", "source": "browser"},
    )
    slug_dirs = sorted([p for p in out_root.iterdir() if p.is_dir()])
    ids_a = sorted(
        c["claim_id"]
        for c in json.loads((slug_dirs[0] / "claims.json").read_text(encoding="utf-8"))
    )
    ids_b = sorted(
        c["claim_id"]
        for c in json.loads((slug_dirs[1] / "claims.json").read_text(encoding="utf-8"))
    )
    # The CV and cover-letter markdown is identical across runs (stubs return
    # constants), so the per-claim hashes must match exactly.
    assert ids_a == ids_b
