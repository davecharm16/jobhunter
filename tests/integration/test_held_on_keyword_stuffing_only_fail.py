"""Story 5.3 AC4 — keyword-stuffing-only fail triggers held-package writer.

When fabrication + content-loss pass but keyword-stuffing fails, the package
is still held (per Epic 3 pattern). The held.json's
`keyword_stuffing_violations[]` field carries the flattened view so
Epic 6's queue can surface the fail reason without re-parsing
package.drift.json.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jobhunter.web.api import create_app
from tests.integration._web_helpers import (
    make_fake_parse,
    make_fake_tailor,
    stage_canonical_cv,
    stage_tailoring,
)


def test_keyword_stuffing_only_fail_writes_held_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)

    # CV densely repeats "python" so the keyword-stuffing density check fails
    # while fabrication/content-loss have nothing to flag.
    out_root, _ = stage_tailoring(
        tmp_path,
        monkeypatch,
        fake_tailor=make_fake_tailor(
            cv="python python python python python python end\n",
            cover="hi\n",
        ),
        fake_parse=make_fake_parse(must_haves=["python"], nice_to_haves=[]),
    )

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )
    assert response.status_code == 200, response.text

    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())

    # Held sidecar exists.
    held_path = slug_dir / "package.held.json"
    assert held_path.exists()

    held = json.loads(held_path.read_text(encoding="utf-8"))
    assert "keyword_stuffing_violations" in held
    # At least one violation projected from the density check.
    assert len(held["keyword_stuffing_violations"]) >= 1

    # Metadata reflects held=True with a pointer to the sidecar.
    metadata = json.loads((slug_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["held"] is True
    assert metadata["held_path"] is not None
    assert metadata["drift_verdicts"]["keyword_stuffing"] == "fail"


def test_keyword_stuffing_pass_leaves_held_violations_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When keyword-stuffing passes, the held.json field is absent or empty."""
    filler = (
        " alpha beta gamma delta epsilon zeta eta theta iota kappa lambda "
        "mu nu xi omicron pi rho sigma tau upsilon phi chi psi omega "
    ) * 4
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root, _ = stage_tailoring(
        tmp_path,
        monkeypatch,
        fake_tailor=make_fake_tailor(
            cv="Python developer broad experience" + filler,
            cover="Hello" + filler,
        ),
        fake_parse=make_fake_parse(must_haves=["python"], nice_to_haves=[]),
    )
    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior role.\n", "source": "browser"},
    )
    assert response.status_code == 200, response.text

    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    # All checks pass → no held.json.
    assert not (slug_dir / "package.held.json").exists()
    metadata = json.loads((slug_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["held"] is False
    assert metadata["drift_verdicts"]["keyword_stuffing"] == "pass"
