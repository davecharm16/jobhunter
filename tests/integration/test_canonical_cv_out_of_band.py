"""AC4: out-of-band edits to the canonical CV are visible on the next GET.

The `read_canonical_cv()` reader contract from DECISIONS.md §2 re-reads from
disk on every call — no caching. This file proves the contract end-to-end at
the HTTP boundary: a user editing `canonical-cv.json` in their text editor
between two `GET /api/canonical-cv` requests sees the new content on the
second request with no server reload.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from jobhunter.web.api import create_app
from tests.integration._web_helpers import stage_canonical_cv


def test_out_of_band_edits_visible_on_next_get(tmp_path, monkeypatch) -> None:
    cv_path = stage_canonical_cv(tmp_path, monkeypatch)
    client = TestClient(create_app())

    first = client.get("/api/canonical-cv")
    assert first.status_code == 200
    original_label = first.json()["basics"]["label"]

    # Simulate the user editing the file in their text editor.
    doc = json.loads(cv_path.read_text(encoding="utf-8"))
    doc["basics"]["label"] = "Out-of-Band Edited Label"
    cv_path.write_text(json.dumps(doc), encoding="utf-8")

    second = client.get("/api/canonical-cv")
    assert second.status_code == 200
    assert second.json()["basics"]["label"] == "Out-of-Band Edited Label"
    assert second.json()["basics"]["label"] != original_label


def test_out_of_band_added_tags_visible_on_next_get(tmp_path, monkeypatch) -> None:
    cv_path = stage_canonical_cv(tmp_path, monkeypatch)
    client = TestClient(create_app())

    first = client.get("/api/canonical-cv")
    assert first.status_code == 200
    assert "tags" not in first.json()["work"][0]

    doc = json.loads(cv_path.read_text(encoding="utf-8"))
    doc["work"][0]["tags"] = ["out-of-band-added"]
    doc["work"][0]["highImpact"] = True
    cv_path.write_text(json.dumps(doc), encoding="utf-8")

    second = client.get("/api/canonical-cv")
    assert second.status_code == 200
    assert second.json()["work"][0]["tags"] == ["out-of-band-added"]
    assert second.json()["work"][0]["highImpact"] is True
