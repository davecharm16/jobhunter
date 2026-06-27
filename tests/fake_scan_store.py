"""In-memory ScanStore for fast, DB-free tests (pythonpath includes '.')."""

from __future__ import annotations

import itertools

from jobhunter.scan import (
    Candidate,
    Scan,
    ScanSettings,
    ScanStatus,
    validate_candidate_status,
)

_FIXED_TS = "2026-06-26T00:00:00Z"


class FakeScanStore:
    def __init__(self) -> None:
        self._settings = ScanSettings(
            search_titles=[],
            sites_enabled=["indeed", "onlinejobs_ph", "jobstreet", "linkedin"],
            picks_per_site=3, enabled=True,
            updated_at=_FIXED_TS,
        )
        self._scans: dict[str, Scan] = {}
        self._candidates: dict[str, Candidate] = {}
        self._urls: set[str] = set()
        self._status = ScanStatus(
            status="idle", started_at=None, finished_at=None,
            new_count=0, site_summary={}, per_site={},
        )
        self._current_scan_id: str | None = None
        self._scan_ids = (f"scan-{n}" for n in itertools.count(1))
        self._cand_ids = (f"cand-{n}" for n in itertools.count(1))

    def get_settings(self) -> ScanSettings:
        return self._settings

    def update_settings(self, *, search_titles, sites_enabled, picks_per_site,
                        enabled, location="") -> ScanSettings:
        self._settings = ScanSettings(
            search_titles=list(search_titles), sites_enabled=list(sites_enabled),
            picks_per_site=picks_per_site, enabled=enabled, updated_at=_FIXED_TS,
            location=location,
        )
        return self._settings

    def known_urls(self) -> list[str]:
        return [c.url for c in self._candidates.values()]

    def record_scan(self, *, started_at, finished_at, status, site_summary,
                    candidates) -> tuple[Scan, int, int]:
        scan_id = next(self._scan_ids)
        scan = Scan(id=scan_id, started_at=started_at, finished_at=finished_at,
                    status=status, site_summary=site_summary, created_at=_FIXED_TS)
        self._scans[scan_id] = scan
        new = skipped = 0
        for ci in candidates:
            if ci.url in self._urls:
                skipped += 1
                continue
            cand_id = next(self._cand_ids)
            self._candidates[cand_id] = Candidate(
                id=cand_id, scan_id=scan_id, site=ci.site, url=ci.url,
                title=ci.title, company=ci.company, location=ci.location,
                jd_text=ci.jd_text, fit_reason=ci.fit_reason,
                fit_score=ci.fit_score, status="new", slug=None,
                created_at=_FIXED_TS,
            )
            self._urls.add(ci.url)
            new += 1
        return scan, new, skipped

    def list_candidates(self, *, status=None, scan_id=None) -> list[Candidate]:
        cands = list(self._candidates.values())
        if status is not None:
            cands = [c for c in cands if c.status == status]
        if scan_id is not None:
            cands = [c for c in cands if c.scan_id == scan_id]
        return sorted(cands, key=lambda c: c.id)

    def get_candidate(self, candidate_id) -> Candidate | None:
        return self._candidates.get(candidate_id)

    def set_candidate_status(self, candidate_id, *, status, slug=None):
        validate_candidate_status(status)
        cand = self._candidates.get(candidate_id)
        if cand is None:
            return None
        cand.status = status
        if slug is not None:
            cand.slug = slug
        return cand

    def list_scans(self) -> list[Scan]:
        return sorted(self._scans.values(), key=lambda s: s.id, reverse=True)

    def mark_scan_running(self) -> ScanStatus:
        self._status = ScanStatus(
            status="running", started_at=_FIXED_TS, finished_at=None,
            new_count=0, site_summary={}, per_site={},
        )
        self._current_scan_id = None
        return self._status

    def append_site_results(self, *, site, site_status, candidates):
        if self._current_scan_id is None:
            scan_id = next(self._scan_ids)
            self._scans[scan_id] = Scan(
                id=scan_id, started_at=None, finished_at=None, status="running",
                site_summary={}, created_at=_FIXED_TS,
            )
            self._current_scan_id = scan_id
            if self._status.status != "running":
                self.mark_scan_running()
                self._current_scan_id = scan_id
        scan_id = self._current_scan_id
        scan = self._scans[scan_id]
        new = skipped = 0
        for ci in candidates:
            if ci.url in self._urls:
                skipped += 1
                continue
            cand_id = next(self._cand_ids)
            self._candidates[cand_id] = Candidate(
                id=cand_id, scan_id=scan_id, site=ci.site, url=ci.url,
                title=ci.title, company=ci.company, location=ci.location,
                jd_text=ci.jd_text, fit_reason=ci.fit_reason,
                fit_score=ci.fit_score, status="new", slug=None,
                created_at=_FIXED_TS,
            )
            self._urls.add(ci.url)
            new += 1
        scan.site_summary[site] = {"status": site_status, "count": new}
        self._status.per_site[site] = {"status": site_status, "count": new}
        return scan, new, skipped

    def mark_scan_completed(self, *, new_count, site_summary) -> ScanStatus:
        self._status = ScanStatus(
            status="completed", started_at=self._status.started_at,
            finished_at=_FIXED_TS, new_count=new_count, site_summary=site_summary,
            per_site=self._status.per_site,
        )
        return self._status

    def get_scan_status(self) -> ScanStatus:
        return self._status
