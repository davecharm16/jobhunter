from jobhunter.canonical_profile import build_canonical_profile


def test_projection_extracts_core_fields():
    cv = {
        "basics": {"name": "Dave", "label": "Solutions Designer", "summary": "Builds things."},
        "skills": [{"name": "Mobile"}, {"name": "Solutions Design"}],
        "work": [
            {"position": "Solutions Designer", "name": "Stratpoint"},
            {"position": "Mobile Dev", "name": "Acme"},
        ],
    }
    p = build_canonical_profile(cv)
    assert p["name"] == "Dave"
    assert p["label"] == "Solutions Designer"
    assert p["summary"] == "Builds things."
    assert p["skills"] == ["Mobile", "Solutions Design"]
    assert p["recent_titles"] == ["Solutions Designer @ Stratpoint", "Mobile Dev @ Acme"]


def test_projection_tolerates_missing_sections():
    p = build_canonical_profile({"basics": {"name": "X"}})
    assert p["name"] == "X"
    assert p["label"] == ""
    assert p["summary"] == ""
    assert p["skills"] == []
    assert p["recent_titles"] == []


def test_projection_caps_lengths():
    cv = {
        "basics": {"name": "N"},
        "skills": [{"name": f"s{i}"} for i in range(50)],
        "work": [{"position": f"p{i}", "name": "c"} for i in range(20)],
    }
    p = build_canonical_profile(cv)
    assert len(p["skills"]) == 30
    assert len(p["recent_titles"]) == 8
