from tests.fake_scan_store import FakeScanStore

from jobhunter.scan import CandidateInput


def _ci(url, site="indeed"):
    return CandidateInput(site=site, url=url, title="Dev", company="Acme",
                          location="Remote", jd_text="JD body",
                          fit_reason="fits", fit_score=0.8)

def test_record_scan_dedups_by_url():
    store = FakeScanStore()
    scan, new, skipped = store.record_scan(
        started_at=None, finished_at=None, status="completed",
        site_summary={}, candidates=[_ci("https://jobs.example.com/1")],
    )
    assert (new, skipped) == (1, 0)
    _, new2, skipped2 = store.record_scan(
        started_at=None, finished_at=None, status="completed",
        site_summary={}, candidates=[_ci("https://jobs.example.com/1")],
    )
    assert (new2, skipped2) == (0, 1)
    assert store.known_urls() == ["https://jobs.example.com/1"]

def test_settings_defaults_then_update():
    store = FakeScanStore()
    assert store.get_settings().enabled is True
    updated = store.update_settings(
        search_titles=["Architect"], sites_enabled=["linkedin"],
        picks_per_site=5, enabled=False,
    )
    assert updated.picks_per_site == 5 and updated.enabled is False

def test_set_candidate_status_sets_slug():
    store = FakeScanStore()
    scan, _, _ = store.record_scan(
        started_at=None, finished_at=None, status="completed",
        site_summary={}, candidates=[_ci("https://jobs.example.com/2")],
    )
    cand = store.list_candidates()[0]
    out = store.set_candidate_status(cand.id, status="generated", slug="my-slug")
    assert out.status == "generated" and out.slug == "my-slug"
