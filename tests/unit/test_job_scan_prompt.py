"""Tests for the versioned job_scan prompt template (F2 scan engine)."""

from jobhunter.prompts import load_prompt


def test_job_scan_prompt_loads_and_has_contract_tokens():
    p = load_prompt("job_scan")
    assert p.version == "v1"
    body = p.content
    for token in (
        "{{SEARCH_TITLES}}",
        "{{SITES_ENABLED}}",
        "{{PICKS_PER_SITE}}",
        "{{CANONICAL_PROFILE}}",
        "{{KNOWN_URLS}}",
    ):
        assert token in body, f"Missing injection token: {token}"
    # output JSON contract fields Claude must emit
    for field in (
        "site",
        "url",
        "title",
        "company",
        "location",
        "jd_text",
        "fit_reason",
        "fit_score",
        "site_summary",
        "candidates",
    ):
        assert field in body, f"Missing output contract field: {field}"
