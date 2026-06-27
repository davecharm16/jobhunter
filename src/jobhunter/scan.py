"""Job-scan domain types (spec 2026-06-26). Pure data + storage interface.

No I/O, no SQL, no FastAPI — import-safe without a DB so routes can be tested
against an in-memory fake (tests/fake_scan_store.py).
"""

import builtins
from dataclasses import asdict, dataclass
from typing import Protocol

SITES: tuple[str, ...] = ("indeed", "onlinejobs_ph", "jobstreet", "linkedin")
CANDIDATE_STATUSES: tuple[str, ...] = ("new", "generated", "dismissed")
SCAN_STATUSES: tuple[str, ...] = ("completed", "partial")
INITIAL_CANDIDATE_STATUS = "new"
PICKS_MIN, PICKS_MAX = 1, 10


def validate_site(site: str) -> None:
    if site not in SITES:
        raise ValueError(f"unknown site: {site!r} (allowed: {', '.join(SITES)})")


def validate_candidate_status(status: str) -> None:
    if status not in CANDIDATE_STATUSES:
        raise ValueError(
            f"unknown status: {status!r} (allowed: {', '.join(CANDIDATE_STATUSES)})"
        )


def validate_settings(
    search_titles: builtins.list[str],
    sites_enabled: builtins.list[str],
    picks_per_site: int,
) -> None:
    if not search_titles or any(not t.strip() for t in search_titles):
        raise ValueError("search_titles must be a non-empty list of non-blank strings")
    if not sites_enabled:
        raise ValueError("sites_enabled must not be empty")
    for s in sites_enabled:
        validate_site(s)
    if not (PICKS_MIN <= picks_per_site <= PICKS_MAX):
        raise ValueError(f"picks_per_site must be between {PICKS_MIN} and {PICKS_MAX}")


@dataclass
class ScanSettings:
    search_titles: builtins.list[str]
    sites_enabled: builtins.list[str]
    picks_per_site: int
    enabled: bool
    updated_at: str
    location: str = ""  # configurable search location (e.g. "Philippines", "Remote")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ScanStatus:
    status: str  # idle | running | completed | error
    started_at: str | None
    finished_at: str | None
    new_count: int
    site_summary: dict

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CandidateInput:
    site: str
    url: str
    title: str
    company: str | None
    location: str | None
    jd_text: str
    fit_reason: str | None
    fit_score: float | None


@dataclass
class Candidate:
    id: str
    scan_id: str
    site: str
    url: str
    title: str
    company: str | None
    location: str | None
    jd_text: str
    fit_reason: str | None
    fit_score: float | None
    status: str
    slug: str | None
    created_at: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Scan:
    id: str
    started_at: str | None
    finished_at: str | None
    status: str
    site_summary: dict
    created_at: str

    def to_dict(self) -> dict:
        return asdict(self)


class ScanStore(Protocol):
    def get_settings(self) -> ScanSettings: ...

    def update_settings(
        self,
        *,
        search_titles: builtins.list[str],
        sites_enabled: builtins.list[str],
        picks_per_site: int,
        enabled: bool,
        location: str = "",
    ) -> ScanSettings: ...

    def known_urls(self) -> builtins.list[str]: ...

    def record_scan(
        self,
        *,
        started_at: str | None,
        finished_at: str | None,
        status: str,
        site_summary: dict,
        candidates: builtins.list[CandidateInput],
    ) -> tuple[Scan, int, int]:
        """Insert scan + new candidates. Returns (scan, new_count, skipped_count)."""
        ...

    def list_candidates(
        self, *, status: str | None = None, scan_id: str | None = None
    ) -> builtins.list[Candidate]: ...

    def get_candidate(self, candidate_id: str) -> Candidate | None: ...

    def set_candidate_status(
        self, candidate_id: str, *, status: str, slug: str | None = None
    ) -> Candidate | None: ...

    def list_scans(self) -> builtins.list[Scan]: ...

    def mark_scan_running(self) -> ScanStatus: ...

    def mark_scan_completed(
        self, *, new_count: int, site_summary: dict
    ) -> ScanStatus: ...

    def get_scan_status(self) -> ScanStatus: ...


__all__ = [
    "SITES", "CANDIDATE_STATUSES", "SCAN_STATUSES", "INITIAL_CANDIDATE_STATUS",
    "PICKS_MIN", "PICKS_MAX", "validate_site", "validate_candidate_status",
    "validate_settings", "ScanSettings", "ScanStatus", "CandidateInput",
    "Candidate", "Scan", "ScanStore",
]
