import pytest
from jobhunter.scan import (
    SITES, CANDIDATE_STATUSES, validate_site, validate_candidate_status,
    validate_settings, ScanSettings,
)

def test_sites_and_statuses_are_canonical():
    assert SITES == ("indeed", "onlinejobs_ph", "jobstreet", "linkedin")
    assert CANDIDATE_STATUSES == ("new", "generated", "dismissed")

def test_validate_site_rejects_unknown():
    validate_site("indeed")
    with pytest.raises(ValueError):
        validate_site("monster")

def test_validate_candidate_status_rejects_unknown():
    validate_candidate_status("new")
    with pytest.raises(ValueError):
        validate_candidate_status("archived")

def test_validate_settings_rejects_empty_titles():
    with pytest.raises(ValueError):
        validate_settings([], ["indeed"], 3)

def test_validate_settings_rejects_unknown_site():
    with pytest.raises(ValueError):
        validate_settings(["Dev"], ["monster"], 3)

def test_validate_settings_rejects_out_of_range_picks():
    with pytest.raises(ValueError):
        validate_settings(["Dev"], ["indeed"], 0)
    with pytest.raises(ValueError):
        validate_settings(["Dev"], ["indeed"], 11)

def test_validate_settings_accepts_valid():
    validate_settings(["Dev", "Architect"], ["indeed", "linkedin"], 3)

def test_scan_settings_to_dict_roundtrip():
    s = ScanSettings(["Dev"], ["indeed"], 3, True, "2026-06-26T00:00:00Z")
    assert s.to_dict()["search_titles"] == ["Dev"]
