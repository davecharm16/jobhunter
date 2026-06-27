# Job Scan (App-Side) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the jobhunter app side of the Automated Job Scan feature — Supabase persistence, `/api/scan/*` endpoints (settings, results-ingest with dedup, known-urls, canonical-profile, candidates list/dismiss/generate), GChat notification, and the React "Job Scan" dashboard — so the external scan engine (separate F2 plan) only has to POST results.

**Architecture:** The scanner is an external ingestion agent (like the existing n8n flows); this plan is the *tested boundary* it feeds. Mirrors the application-tracker pattern exactly: pure domain module (`scan.py`) + `Protocol`, a psycopg `PostgresScanStore`, an in-memory fake for tests, and thin FastAPI routes injected via a `get_store` dependency. "Generate CV" reuses `run_tailoring()` unchanged. No new LLM pathway in the app.

**Tech Stack:** Python 3 / FastAPI / pydantic / psycopg v3 / Supabase Postgres / pytest; React + Vite + Tailwind (no frontend test harness — frontend tasks verify via `npm run build` + manual check).

**Spec:** `docs/superpowers/specs/2026-06-26-job-scan-design.md`. **North star:** `docs/superpowers/specs/2026-06-26-job-scan-feature-overview.md` (cite F-IDs + AC numbers in commits).

## Global Constraints

- **Bind `127.0.0.1` only; no auth beyond loopback + `INGEST_TOKEN`** (DECISIONS.md §5/§6). Machine endpoints reuse `require_ingest_token`.
- **No new direct dependencies.** `tests/unit/test_secret_hygiene` forbids `playwright`/`httpx`/`requests`/`selenium` as direct deps. `httpx` is already transitively available for the notifier; do **not** add it to `pyproject`. Add **no** browser deps — Playwright lives only in n8n (F2).
- **No job-board hostnames in source or tests** — `test_no_job_board_hostnames_in_jobhunter_source` is repo-wide. Use bare site identifiers (`indeed`, `onlinejobs_ph`, `jobstreet`, `linkedin` — no TLD) in code; job-board URLs are runtime DB data only; **all test fixtures use placeholder hosts like `https://jobs.example.com/...`**.
- **Single LLM provider in-app** (DECISIONS.md §4): "Generate CV" calls existing `run_tailoring()`; introduce no other LLM calls.
- **Sites:** `indeed`, `onlinejobs_ph`, `jobstreet`, `linkedin`. **Candidate statuses:** `new`, `generated`, `dismissed`. **picks_per_site** default 3, range 1–10.
- **Timestamps:** render `timestamptz` as ISO-8601 `Z` strings via the same `_ISO`/`to_char` idiom as `application_store_pg.py`.
- **Tests:** `pytest -q` is the only hard gate. `ruff check . && ruff format . && mypy` advisory but keep new modules clean.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `supabase/migrations/20260626000000_job_scan.sql` | Create `scan_settings` (seeded single row), `scans`, `scan_candidates` (`UNIQUE(url)`). |
| `src/jobhunter/scan.py` | Pure domain: constants, validators, dataclasses (`ScanSettings`, `Scan`, `Candidate`), `ScanStore` Protocol. No I/O. |
| `src/jobhunter/scan_store_pg.py` | `PostgresScanStore` (psycopg v3, `SUPABASE_DB_URL`). |
| `src/jobhunter/canonical_profile.py` | `build_canonical_profile(cv) -> dict` — condensed CV for ranking. |
| `src/jobhunter/web/routes/scan.py` | `APIRouter` for all `/api/scan/*` endpoints + `get_store` dependency. |
| `src/jobhunter/notifier.py` (modify) | Add `build_scan_message()` + `notify_scan()` (dashboard-link only). |
| `src/jobhunter/web/api.py` (modify) | Register `scan_router`. |
| `tests/fake_scan_store.py` | In-memory `FakeScanStore`. |
| `tests/unit/test_scan_*.py` | Unit tests per task. |
| `src/jobhunter/web/frontend/src/api/scan.ts` | Frontend API client + types. |
| `.../frontend/src/JobScanPage.tsx` | Dashboard page. |
| `.../frontend/src/SettingsPage.tsx` (modify) | "Job Scan" settings section. |
| `.../frontend/src/Sidebar.tsx` + `App.tsx` (modify) | Nav item + route. |
| `DECISIONS.md`, `README.md` (modify) | Decision entry + setup docs. |

---

## Task 1: Migration — scan tables

**Files:**
- Create: `supabase/migrations/20260626000000_job_scan.sql`

**Interfaces:**
- Produces: tables `scan_settings`, `scans`, `scan_candidates`; `UNIQUE(scan_candidates.url)`.

- [ ] **Step 1: Write the migration**

```sql
-- Automated Job Scan (spec: 2026-06-26-job-scan-design.md)
create extension if not exists pgcrypto;  -- gen_random_uuid()

-- Single-row config table (id is always true).
create table if not exists scan_settings (
    id              boolean primary key default true check (id),
    search_titles   text[] not null default '{}',
    sites_enabled   text[] not null default '{indeed,onlinejobs_ph,jobstreet,linkedin}',
    picks_per_site  int    not null default 3 check (picks_per_site between 1 and 10),
    enabled         boolean not null default true,
    updated_at      timestamptz not null default now()
);
insert into scan_settings (id) values (true) on conflict (id) do nothing;

create table if not exists scans (
    id            uuid primary key default gen_random_uuid(),
    started_at    timestamptz,
    finished_at   timestamptz,
    status        text not null default 'completed'
                  check (status in ('completed','partial')),
    site_summary  jsonb not null default '{}'::jsonb,
    created_at    timestamptz not null default now()
);

create table if not exists scan_candidates (
    id          uuid primary key default gen_random_uuid(),
    scan_id     uuid not null references scans(id) on delete cascade,
    site        text not null
                check (site in ('indeed','onlinejobs_ph','jobstreet','linkedin')),
    url         text not null unique,
    title       text not null,
    company     text,
    location    text,
    jd_text     text not null,
    fit_reason  text,
    fit_score   numeric,
    status      text not null default 'new'
                check (status in ('new','generated','dismissed')),
    slug        text,
    created_at  timestamptz not null default now()
);

create index if not exists scan_candidates_scan_id_idx on scan_candidates (scan_id);
create index if not exists scan_candidates_status_idx on scan_candidates (status);
```

- [ ] **Step 2: Apply locally to verify it parses**

Run: `psql "$SUPABASE_DB_URL" -f supabase/migrations/20260626000000_job_scan.sql` (or `supabase db reset` if using the local stack).
Expected: no errors; `\d scan_candidates` shows the `url` unique constraint.

- [ ] **Step 3: Commit**

```bash
git add supabase/migrations/20260626000000_job_scan.sql
git commit -m "feat(scan): add scan_settings/scans/scan_candidates migration [F1,F3]"
```

---

## Task 2: Domain module `scan.py`

**Files:**
- Create: `src/jobhunter/scan.py`
- Test: `tests/unit/test_scan_domain.py`

**Interfaces:**
- Produces:
  - `SITES: tuple[str,...]`, `CANDIDATE_STATUSES: tuple[str,...]`, `SCAN_STATUSES: tuple[str,...]`
  - `validate_site(site:str)->None`, `validate_candidate_status(status:str)->None`
  - `@dataclass ScanSettings(search_titles:list[str], sites_enabled:list[str], picks_per_site:int, enabled:bool, updated_at:str)` with `.to_dict()`
  - `@dataclass Candidate(id, scan_id, site, url, title, company, location, jd_text, fit_reason, fit_score, status, slug, created_at)` with `.to_dict()`
  - `@dataclass Scan(id, started_at, finished_at, status, site_summary:dict, created_at)` with `.to_dict()`
  - `@dataclass CandidateInput(site, url, title, company, location, jd_text, fit_reason, fit_score)`
  - `validate_settings(search_titles, sites_enabled, picks_per_site)->None` (raises `ValueError`)
  - `ScanStore` Protocol (see methods below)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_scan_domain.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_scan_domain.py -v`
Expected: FAIL — `ModuleNotFoundError: jobhunter.scan`.

- [ ] **Step 3: Write `src/jobhunter/scan.py`**

```python
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
        """Insert scan + new candidates. Returns (scan, new_count, skipped_count)."""//
        ...

    def list_candidates(
        self, *, status: str | None = None, scan_id: str | None = None
    ) -> builtins.list[Candidate]: ...

    def get_candidate(self, candidate_id: str) -> Candidate | None: ...

    def set_candidate_status(
        self, candidate_id: str, *, status: str, slug: str | None = None
    ) -> Candidate | None: ...

    def list_scans(self) -> builtins.list[Scan]: ...


__all__ = [
    "SITES", "CANDIDATE_STATUSES", "SCAN_STATUSES", "INITIAL_CANDIDATE_STATUS",
    "PICKS_MIN", "PICKS_MAX", "validate_site", "validate_candidate_status",
    "validate_settings", "ScanSettings", "CandidateInput", "Candidate", "Scan",
    "ScanStore",
]
```

> NOTE: remove the stray `//` after the docstring in `record_scan` — it is not valid Python. The method body is just `...`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_scan_domain.py -v`
Expected: PASS (all 8 tests).

- [ ] **Step 5: Commit**

```bash
git add src/jobhunter/scan.py tests/unit/test_scan_domain.py
git commit -m "feat(scan): domain types + validators + ScanStore protocol [F1,F3]"
```

---

## Task 3: In-memory `FakeScanStore`

**Files:**
- Create: `tests/fake_scan_store.py`
- Test: `tests/unit/test_fake_scan_store.py`

**Interfaces:**
- Consumes: `ScanStore` Protocol from Task 2.
- Produces: `FakeScanStore` implementing every `ScanStore` method, used by all route tests.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_fake_scan_store.py
from jobhunter.scan import CandidateInput
from tests.fake_scan_store import FakeScanStore

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_fake_scan_store.py -v`
Expected: FAIL — `ModuleNotFoundError: tests.fake_scan_store`.

- [ ] **Step 3: Write `tests/fake_scan_store.py`**

```python
"""In-memory ScanStore for fast, DB-free tests (pythonpath includes '.')."""

from __future__ import annotations

import itertools

from jobhunter.scan import (
    Candidate, CandidateInput, Scan, ScanSettings, validate_candidate_status,
)

_FIXED_TS = "2026-06-26T00:00:00Z"


class FakeScanStore:
    def __init__(self) -> None:
        self._settings = ScanSettings(
            search_titles=[], sites_enabled=list(("indeed", "onlinejobs_ph",
            "jobstreet", "linkedin")), picks_per_site=3, enabled=True,
            updated_at=_FIXED_TS,
        )
        self._scans: dict[str, Scan] = {}
        self._candidates: dict[str, Candidate] = {}
        self._urls: set[str] = set()
        self._scan_ids = (f"scan-{n}" for n in itertools.count(1))
        self._cand_ids = (f"cand-{n}" for n in itertools.count(1))

    def get_settings(self) -> ScanSettings:
        return self._settings

    def update_settings(self, *, search_titles, sites_enabled, picks_per_site,
                        enabled) -> ScanSettings:
        self._settings = ScanSettings(
            search_titles=list(search_titles), sites_enabled=list(sites_enabled),
            picks_per_site=picks_per_site, enabled=enabled, updated_at=_FIXED_TS,
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_fake_scan_store.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/fake_scan_store.py tests/unit/test_fake_scan_store.py
git commit -m "test(scan): in-memory FakeScanStore [F3]"
```

---

## Task 4: Settings endpoints + router registration (F1)

**Files:**
- Create: `src/jobhunter/web/routes/scan.py`
- Modify: `src/jobhunter/web/api.py:208-218` (register router)
- Test: `tests/unit/test_scan_settings_api.py`

**Interfaces:**
- Consumes: `FakeScanStore` (Task 3), `ScanStore` (Task 2).
- Produces: `router`, `get_store` (overridable dependency); `GET/PUT /api/scan/settings`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_scan_settings_api.py
import pytest
from fastapi.testclient import TestClient
from jobhunter.web.api import create_app
from jobhunter.web.routes.scan import get_store
from tests.fake_scan_store import FakeScanStore

@pytest.fixture
def client():
    app = create_app()
    store = FakeScanStore()
    app.dependency_overrides[get_store] = lambda: store
    return TestClient(app)

def test_get_settings_returns_defaults(client):
    r = client.get("/api/scan/settings")
    assert r.status_code == 200
    assert r.json()["enabled"] is True

def test_put_settings_saves(client):
    r = client.put("/api/scan/settings", json={
        "search_titles": ["Architect"], "sites_enabled": ["linkedin"],
        "picks_per_site": 5, "enabled": False,
    })
    assert r.status_code == 200
    assert r.json()["picks_per_site"] == 5
    assert client.get("/api/scan/settings").json()["enabled"] is False

def test_put_settings_rejects_empty_titles(client):
    r = client.put("/api/scan/settings", json={
        "search_titles": [], "sites_enabled": ["indeed"],
        "picks_per_site": 3, "enabled": True,
    })
    assert r.status_code == 422

def test_put_settings_rejects_unknown_site(client):
    r = client.put("/api/scan/settings", json={
        "search_titles": ["Dev"], "sites_enabled": ["monster"],
        "picks_per_site": 3, "enabled": True,
    })
    assert r.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_scan_settings_api.py -v`
Expected: FAIL — `ModuleNotFoundError: jobhunter.web.routes.scan`.

- [ ] **Step 3: Write `src/jobhunter/web/routes/scan.py`**

```python
"""Job Scan API (spec 2026-06-26). Thin routes; storage injected via get_store."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from jobhunter.scan import ScanStore, validate_settings
from jobhunter.scan_store_pg import PostgresScanStore

router = APIRouter()


def get_store() -> ScanStore:
    """Production store. Overridden in tests via app.dependency_overrides."""
    return PostgresScanStore.from_env()


class SettingsRequest(BaseModel):
    search_titles: list[str]
    sites_enabled: list[str]
    picks_per_site: int = Field(ge=1, le=10)
    enabled: bool


@router.get("/api/scan/settings")
def get_settings(store: ScanStore = Depends(get_store)) -> dict[str, Any]:
    return store.get_settings().to_dict()


@router.put("/api/scan/settings")
def put_settings(
    payload: SettingsRequest, store: ScanStore = Depends(get_store)
) -> dict[str, Any]:
    try:
        validate_settings(
            payload.search_titles, payload.sites_enabled, payload.picks_per_site
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return store.update_settings(
        search_titles=payload.search_titles,
        sites_enabled=payload.sites_enabled,
        picks_per_site=payload.picks_per_site,
        enabled=payload.enabled,
    ).to_dict()


__all__ = ["router", "get_store"]
```

- [ ] **Step 4: Register the router in `src/jobhunter/web/api.py`**

Add import near the other route imports (after line 48):
```python
from jobhunter.web.routes.scan import router as scan_router
```
Add registration alongside the others (after `app.include_router(applications_router)`):
```python
    app.include_router(scan_router)
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/unit/test_scan_settings_api.py -v`
Expected: PASS (4 tests). The unknown-site test passes via the `validate_settings` 422; the pydantic `Field(ge=1, le=10)` returns 422 for out-of-range picks (also acceptable per AC).

- [ ] **Step 6: Commit**

```bash
git add src/jobhunter/web/routes/scan.py src/jobhunter/web/api.py tests/unit/test_scan_settings_api.py
git commit -m "feat(scan): GET/PUT /api/scan/settings + router wiring [F1]"
```

> NOTE: `PostgresScanStore` (imported by `scan.py`) is written in Task 5; until then the import resolves only because tests override `get_store`. Implement Task 5 before any non-overridden run. If subagents run tasks strictly in order, this is fine because Task 4 tests never call the real store. To avoid an import error, you MAY write a stub `scan_store_pg.py` with the class signature in this task and flesh it out in Task 5 — but the cleaner path is to do Task 5 immediately after.

---

## Task 5: `PostgresScanStore`

**Files:**
- Create: `src/jobhunter/scan_store_pg.py`
- Test: covered indirectly (DB integration tests are out of scope for the hard gate; the fake covers logic). Add a light import test.

**Interfaces:**
- Consumes: `scan.py` dataclasses.
- Produces: `PostgresScanStore` implementing `ScanStore`; `from_env()` classmethod.

- [ ] **Step 1: Write the import/smoke test**

```python
# tests/unit/test_scan_store_pg_import.py
from jobhunter.scan import ScanStore
from jobhunter.scan_store_pg import PostgresScanStore

def test_postgres_scan_store_is_a_scan_store():
    # structural check: all Protocol methods exist
    for m in ("get_settings", "update_settings", "known_urls", "record_scan",
              "list_candidates", "get_candidate", "set_candidate_status",
              "list_scans"):
        assert hasattr(PostgresScanStore, m)
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/test_scan_store_pg_import.py -v`
Expected: FAIL — `ModuleNotFoundError: jobhunter.scan_store_pg`.

- [ ] **Step 3: Write `src/jobhunter/scan_store_pg.py`**

```python
"""Supabase/Postgres ScanStore (psycopg v3, sync). Connection per op."""

from __future__ import annotations

import builtins
import os
import uuid
from typing import Any, Self

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from jobhunter.scan import (
    Candidate, CandidateInput, Scan, ScanSettings, validate_candidate_status,
)

_ISO = "YYYY-MM-DD\"T\"HH24:MI:SS\"Z\""


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return False
    return True


def _ts(col: str, alias: str) -> str:
    return f"to_char({col} at time zone 'UTC', '{_ISO}') as {alias}"


class PostgresScanStore:
    def __init__(self, db_url: str) -> None:
        self._db_url = db_url

    @classmethod
    def from_env(cls) -> Self:
        db_url = os.environ.get("SUPABASE_DB_URL")
        if not db_url:
            raise RuntimeError("SUPABASE_DB_URL is not set")
        return cls(db_url)

    def _connect(self) -> psycopg.Connection[dict[str, Any]]:
        return psycopg.connect(self._db_url, row_factory=dict_row)

    # ---- settings ----
    def get_settings(self) -> ScanSettings:
        with self._connect() as conn:
            row = conn.execute(
                f"select search_titles, sites_enabled, picks_per_site, enabled, "
                f"{_ts('updated_at','updated_at')} from scan_settings where id = true"
            ).fetchone()
            assert row is not None
            return _row_to_settings(row)

    def update_settings(self, *, search_titles, sites_enabled, picks_per_site,
                        enabled) -> ScanSettings:
        with self._connect() as conn:
            row = conn.execute(
                f"""
                update scan_settings
                set search_titles = %s, sites_enabled = %s,
                    picks_per_site = %s, enabled = %s, updated_at = now()
                where id = true
                returning search_titles, sites_enabled, picks_per_site, enabled,
                          {_ts('updated_at','updated_at')}
                """,
                (list(search_titles), list(sites_enabled), picks_per_site, enabled),
            ).fetchone()
            assert row is not None
            conn.commit()
            return _row_to_settings(row)

    # ---- scans / candidates ----
    def known_urls(self) -> builtins.list[str]:
        with self._connect() as conn:
            rows = conn.execute("select url from scan_candidates").fetchall()
            return [r["url"] for r in rows]

    def record_scan(self, *, started_at, finished_at, status, site_summary,
                    candidates) -> tuple[Scan, int, int]:
        with self._connect() as conn:
            scan_row = conn.execute(
                f"""
                insert into scans (started_at, finished_at, status, site_summary)
                values (%s, %s, %s, %s)
                returning id::text as id,
                          {_ts('started_at','started_at')},
                          {_ts('finished_at','finished_at')},
                          status, site_summary,
                          {_ts('created_at','created_at')}
                """,
                (started_at, finished_at, status, Jsonb(site_summary)),
            ).fetchone()
            assert scan_row is not None
            scan_id = scan_row["id"]
            new = skipped = 0
            for ci in candidates:
                inserted = conn.execute(
                    """
                    insert into scan_candidates
                        (scan_id, site, url, title, company, location, jd_text,
                         fit_reason, fit_score)
                    values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    on conflict (url) do nothing
                    returning id
                    """,
                    (scan_id, ci.site, ci.url, ci.title, ci.company, ci.location,
                     ci.jd_text, ci.fit_reason, ci.fit_score),
                ).fetchone()
                if inserted is None:
                    skipped += 1
                else:
                    new += 1
            conn.commit()
            return _row_to_scan(scan_row), new, skipped

    def list_candidates(self, *, status=None, scan_id=None) -> builtins.list[Candidate]:
        clauses, params = [], []
        if status is not None:
            clauses.append("status = %s")
            params.append(status)
        if scan_id is not None and _is_uuid(scan_id):
            clauses.append("scan_id = %s")
            params.append(scan_id)
        where = f"where {' and '.join(clauses)}" if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"select {_cand_cols()} from scan_candidates {where} "
                "order by created_at desc, id asc",
                tuple(params),
            ).fetchall()
            return [_row_to_cand(r) for r in rows]

    def get_candidate(self, candidate_id) -> Candidate | None:
        if not _is_uuid(candidate_id):
            return None
        with self._connect() as conn:
            row = conn.execute(
                f"select {_cand_cols()} from scan_candidates where id = %s",
                (candidate_id,),
            ).fetchone()
            return _row_to_cand(row) if row else None

    def set_candidate_status(self, candidate_id, *, status, slug=None) -> Candidate | None:
        validate_candidate_status(status)
        if not _is_uuid(candidate_id):
            return None
        with self._connect() as conn:
            row = conn.execute(
                f"""
                update scan_candidates
                set status = %s, slug = coalesce(%s, slug)
                where id = %s
                returning {_cand_cols()}
                """,
                (status, slug, candidate_id),
            ).fetchone()
            if row is None:
                return None
            conn.commit()
            return _row_to_cand(row)

    def list_scans(self) -> builtins.list[Scan]:
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                select id::text as id,
                       {_ts('started_at','started_at')},
                       {_ts('finished_at','finished_at')},
                       status, site_summary,
                       {_ts('created_at','created_at')}
                from scans order by created_at desc
                """
            ).fetchall()
            return [_row_to_scan(r) for r in rows]


def _cand_cols() -> str:
    return (
        "id::text as id, scan_id::text as scan_id, site, url, title, company, "
        "location, jd_text, fit_reason, fit_score, status, slug, "
        + _ts("created_at", "created_at")
    )


def _row_to_settings(row: dict[str, Any]) -> ScanSettings:
    return ScanSettings(
        search_titles=list(row["search_titles"]),
        sites_enabled=list(row["sites_enabled"]),
        picks_per_site=row["picks_per_site"],
        enabled=row["enabled"],
        updated_at=row["updated_at"],
    )


def _row_to_scan(row: dict[str, Any]) -> Scan:
    return Scan(
        id=row["id"], started_at=row["started_at"], finished_at=row["finished_at"],
        status=row["status"], site_summary=row["site_summary"],
        created_at=row["created_at"],
    )


def _row_to_cand(row: dict[str, Any]) -> Candidate:
    return Candidate(
        id=row["id"], scan_id=row["scan_id"], site=row["site"], url=row["url"],
        title=row["title"], company=row["company"], location=row["location"],
        jd_text=row["jd_text"], fit_reason=row["fit_reason"],
        fit_score=float(row["fit_score"]) if row["fit_score"] is not None else None,
        status=row["status"], slug=row["slug"], created_at=row["created_at"],
    )


__all__ = ["PostgresScanStore"]
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_scan_store_pg_import.py tests/unit/test_scan_settings_api.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/jobhunter/scan_store_pg.py tests/unit/test_scan_store_pg_import.py
git commit -m "feat(scan): PostgresScanStore (psycopg) [F1,F3]"
```

---

## Task 6: Results ingest + dedup + known-urls (F3)

**Files:**
- Modify: `src/jobhunter/web/routes/scan.py`
- Test: `tests/unit/test_scan_results_api.py`

**Interfaces:**
- Consumes: `ScanStore.record_scan`, `ScanStore.known_urls`, `CandidateInput`.
- Produces: `POST /api/scan/results` → `{scan_id, received, new, skipped}`; `GET /api/scan/known-urls` → `{urls: [...]}`. Notification is wired in Task 7 (this task returns counts only).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_scan_results_api.py
import pytest
from fastapi.testclient import TestClient
from jobhunter.web.api import create_app
from jobhunter.web.routes.scan import get_store
from tests.fake_scan_store import FakeScanStore

@pytest.fixture
def store():
    return FakeScanStore()

@pytest.fixture
def client(store):
    app = create_app()
    app.dependency_overrides[get_store] = lambda: store
    return TestClient(app)

def _payload(url="https://jobs.example.com/1"):
    return {
        "started_at": "2026-06-26T01:00:00Z",
        "finished_at": "2026-06-26T01:05:00Z",
        "site_summary": {"indeed": {"status": "ok", "count": 1}},
        "candidates": [{
            "site": "indeed", "url": url, "title": "Dev", "company": "Acme",
            "location": "Remote", "jd_text": "Full JD body",
            "fit_reason": "fits", "fit_score": 0.8,
        }],
    }

def test_results_inserts_new(client):
    r = client.post("/api/scan/results", json=_payload())
    assert r.status_code == 200
    body = r.json()
    assert body["received"] == 1 and body["new"] == 1 and body["skipped"] == 0

def test_results_is_idempotent(client):
    client.post("/api/scan/results", json=_payload())
    r = client.post("/api/scan/results", json=_payload())
    assert r.json()["new"] == 0 and r.json()["skipped"] == 1

def test_results_rejects_unknown_site(client):
    bad = _payload()
    bad["candidates"][0]["site"] = "monster"
    r = client.post("/api/scan/results", json=bad)
    assert r.status_code == 422

def test_known_urls(client):
    client.post("/api/scan/results", json=_payload())
    r = client.get("/api/scan/known-urls")
    assert r.status_code == 200
    assert r.json()["urls"] == ["https://jobs.example.com/1"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/test_scan_results_api.py -v`
Expected: FAIL — 404 (routes not defined yet).

- [ ] **Step 3: Add models + endpoints to `scan.py`**

Add imports at top:
```python
from jobhunter.scan import (
    CandidateInput, ScanStore, validate_settings, validate_site,
)
```
Add models + routes (after the settings routes):
```python
class CandidatePayload(BaseModel):
    site: str
    url: str = Field(min_length=1)
    title: str = Field(min_length=1)
    company: str | None = None
    location: str | None = None
    jd_text: str = Field(min_length=1)
    fit_reason: str | None = None
    fit_score: float | None = None


class ResultsRequest(BaseModel):
    started_at: str | None = None
    finished_at: str | None = None
    status: str = "completed"
    site_summary: dict[str, Any] = Field(default_factory=dict)
    candidates: list[CandidatePayload] = Field(default_factory=list)


@router.get("/api/scan/known-urls")
def known_urls(store: ScanStore = Depends(get_store)) -> dict[str, Any]:
    return {"urls": store.known_urls()}


@router.post("/api/scan/results")
def post_results(
    payload: ResultsRequest, store: ScanStore = Depends(get_store)
) -> dict[str, Any]:
    for c in payload.candidates:
        try:
            validate_site(c.site)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    cands = [
        CandidateInput(
            site=c.site, url=c.url, title=c.title, company=c.company,
            location=c.location, jd_text=c.jd_text, fit_reason=c.fit_reason,
            fit_score=c.fit_score,
        )
        for c in payload.candidates
    ]
    scan, new, skipped = store.record_scan(
        started_at=payload.started_at, finished_at=payload.finished_at,
        status=payload.status, site_summary=payload.site_summary,
        candidates=cands,
    )
    return {
        "scan_id": scan.id, "received": len(cands), "new": new, "skipped": skipped,
    }
```
Add `Depends`/`require_ingest_token`: protect machine endpoints. Import at top of `scan.py`:
```python
from jobhunter.web.api import require_ingest_token
```
> NOTE: to avoid a circular import (`api.py` imports `scan.py`), move `require_ingest_token` into a small `src/jobhunter/web/auth.py` module and import it from both `api.py` and `scan.py`. Do that refactor in this task: create `web/auth.py` with `_LOOPBACK_CLIENT_HOSTS`, `_is_loopback_request`, `require_ingest_token` (cut from `api.py`), then `from jobhunter.web.auth import require_ingest_token` in both files. Re-run the full suite after to confirm nothing broke.

Then add `dependencies=[Depends(require_ingest_token)]` to `known_urls` and `post_results` route decorators.

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_scan_results_api.py -v`
Expected: PASS. (TestClient is treated as loopback, so the token check is bypassed — matching existing `/api/paste` tests.)

- [ ] **Step 5: Run full suite (auth refactor sanity)**

Run: `pytest -q`
Expected: PASS (the `web/auth.py` extraction must not break existing paste tests).

- [ ] **Step 6: Commit**

```bash
git add src/jobhunter/web/routes/scan.py src/jobhunter/web/auth.py src/jobhunter/web/api.py tests/unit/test_scan_results_api.py
git commit -m "feat(scan): POST /api/scan/results dedup + known-urls + auth extraction [F3]"
```

---

## Task 7: Scan notification (F4)

**Files:**
- Modify: `src/jobhunter/notifier.py` (add scan message builder + sender)
- Modify: `src/jobhunter/web/routes/scan.py` (call notify after ingest)
- Test: `tests/unit/test_scan_notification.py`

**Interfaces:**
- Consumes: existing `notifier` httpx pattern + `GCHAT_WEBHOOK_URL` from `RuntimeConfig`.
- Produces: `build_scan_message(*, new_count:int, site_summary:dict, dashboard_url:str)->str`; `notify_scan(webhook_url, message)->None` (non-fatal). Ingest sends a notification only when `new > 0` and a webhook is configured.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_scan_notification.py
from jobhunter.notifier import build_scan_message

def test_message_has_counts_and_dashboard_link_no_job_boards():
    msg = build_scan_message(
        new_count=5,
        site_summary={"indeed": {"status": "ok", "count": 3},
                      "linkedin": {"status": "blocked", "count": 0}},
        dashboard_url="http://127.0.0.1:8765/job-scan",
    )
    assert "5" in msg
    assert "127.0.0.1:8765/job-scan" in msg
    for host in ("indeed.com", "linkedin.com", "jobstreet.com", "onlinejobs.ph"):
        assert host not in msg

def test_message_lists_per_site_counts():
    msg = build_scan_message(
        new_count=3,
        site_summary={"indeed": {"status": "ok", "count": 3}},
        dashboard_url="http://127.0.0.1:8765/job-scan",
    )
    assert "indeed" in msg  # bare identifier, not a hostname
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/test_scan_notification.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_scan_message'`.

- [ ] **Step 3: Add to `notifier.py`**

```python
def build_scan_message(
    *, new_count: int, site_summary: dict[str, Any], dashboard_url: str
) -> str:
    """Discovery notification. Dashboard link only — NEVER job-board hostnames
    (FR44/FR11; test_no_job_board_hostnames_in_jobhunter_source)."""
    parts = [
        f"🔎 Job Scan: {new_count} new candidate{'s' if new_count != 1 else ''}."
    ]
    for site, info in sorted(site_summary.items()):
        status = info.get("status", "?")
        count = info.get("count", 0)
        parts.append(f"• {site}: {status} ({count})")
    parts.append(f"Review on your dashboard: {dashboard_url}")
    return "\n".join(parts)


def notify_scan(webhook_url: str, message: str, *, retries: int = 3) -> None:
    """Fire-and-forget POST to GChat. Failures are logged, never raised."""
    try:
        with httpx.Client(timeout=10.0) as client:
            client.post(webhook_url, json={"text": message})
    except Exception as exc:  # noqa: BLE001 - non-fatal by contract
        logging.getLogger(__name__).warning("scan notification failed: %s", exc)
```
Add `build_scan_message` and `notify_scan` to `__all__`.

- [ ] **Step 4: Wire into `post_results` in `scan.py`**

After computing `new`, before returning:
```python
    if new > 0:
        from jobhunter.notifier import build_scan_message, notify_scan
        from jobhunter.runtime_config import load_runtime_config
        try:
            cfg = load_runtime_config()
            webhook = cfg.gchat_webhook_url
        except Exception:  # noqa: BLE001 - config issues must not fail ingest
            webhook = None
        if webhook:
            notify_scan(
                webhook,
                build_scan_message(
                    new_count=new,
                    site_summary=payload.site_summary,
                    dashboard_url="http://127.0.0.1:8765/job-scan",
                ),
            )
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/unit/test_scan_notification.py tests/unit/test_scan_results_api.py -q`
Expected: PASS. (Ingest tests have no webhook configured → no notify attempt.)

- [ ] **Step 6: Commit**

```bash
git add src/jobhunter/notifier.py src/jobhunter/web/routes/scan.py tests/unit/test_scan_notification.py
git commit -m "feat(scan): GChat scan notification (dashboard link only) [F4]"
```

---

## Task 8: Candidate list + dismiss (F3/F5)

**Files:**
- Modify: `src/jobhunter/web/routes/scan.py`
- Test: `tests/unit/test_scan_candidates_api.py`

**Interfaces:**
- Consumes: `ScanStore.list_candidates`, `list_scans`, `get_candidate`, `set_candidate_status`.
- Produces: `GET /api/scan/candidates?status=&scan_id=`; `GET /api/scan/scans`; `PATCH /api/scan/candidates/{id}` (`{status:"dismissed"}`).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_scan_candidates_api.py
import pytest
from fastapi.testclient import TestClient
from jobhunter.web.api import create_app
from jobhunter.web.routes.scan import get_store
from tests.fake_scan_store import FakeScanStore

@pytest.fixture
def store():
    return FakeScanStore()

@pytest.fixture
def client(store):
    app = create_app()
    app.dependency_overrides[get_store] = lambda: store
    return TestClient(app)

def _seed(client, url="https://jobs.example.com/1"):
    client.post("/api/scan/results", json={
        "site_summary": {}, "candidates": [{
            "site": "indeed", "url": url, "title": "Dev", "company": "Acme",
            "location": "Remote", "jd_text": "JD", "fit_reason": "x",
            "fit_score": 0.5}]})

def test_list_candidates_filters_status(client):
    _seed(client)
    r = client.get("/api/scan/candidates?status=new")
    assert r.status_code == 200 and len(r.json()) == 1

def test_dismiss_candidate(client):
    _seed(client)
    cid = client.get("/api/scan/candidates").json()[0]["id"]
    r = client.patch(f"/api/scan/candidates/{cid}", json={"status": "dismissed"})
    assert r.status_code == 200 and r.json()["status"] == "dismissed"

def test_dismiss_unknown_404(client):
    r = client.patch("/api/scan/candidates/nope", json={"status": "dismissed"})
    assert r.status_code == 404

def test_patch_invalid_status_422(client):
    _seed(client)
    cid = client.get("/api/scan/candidates").json()[0]["id"]
    r = client.patch(f"/api/scan/candidates/{cid}", json={"status": "archived"})
    assert r.status_code == 422

def test_list_scans(client):
    _seed(client)
    r = client.get("/api/scan/scans")
    assert r.status_code == 200 and len(r.json()) == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/test_scan_candidates_api.py -v`
Expected: FAIL — 404s / 405s.

- [ ] **Step 3: Add endpoints to `scan.py`**

```python
from jobhunter.scan import validate_candidate_status


class CandidatePatch(BaseModel):
    status: str


@router.get("/api/scan/candidates")
def list_candidates(
    status: str | None = None, scan_id: str | None = None,
    store: ScanStore = Depends(get_store),
) -> list[dict[str, Any]]:
    if status is not None:
        try:
            validate_candidate_status(status)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return [c.to_dict() for c in store.list_candidates(status=status, scan_id=scan_id)]


@router.get("/api/scan/scans")
def list_scans(store: ScanStore = Depends(get_store)) -> list[dict[str, Any]]:
    return [s.to_dict() for s in store.list_scans()]


@router.patch("/api/scan/candidates/{candidate_id}")
def patch_candidate(
    candidate_id: str, payload: CandidatePatch,
    store: ScanStore = Depends(get_store),
) -> dict[str, Any]:
    try:
        validate_candidate_status(payload.status)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    updated = store.set_candidate_status(candidate_id, status=payload.status)
    if updated is None:
        raise HTTPException(status_code=404, detail="candidate not found")
    return updated.to_dict()
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_scan_candidates_api.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/jobhunter/web/routes/scan.py tests/unit/test_scan_candidates_api.py
git commit -m "feat(scan): list/scans + dismiss candidate endpoints [F3,F5]"
```

---

## Task 9: Generate CV from candidate (F6)

**Files:**
- Modify: `src/jobhunter/web/routes/scan.py`
- Test: `tests/unit/test_scan_generate_api.py`

**Interfaces:**
- Consumes: `ScanStore.get_candidate`, `set_candidate_status`; `run_tailoring` (existing). Injected `run_tailoring` via a `get_tailor` dependency so tests stub it (no real LLM).
- Produces: `POST /api/scan/candidates/{id}/generate` → `{slug, status:"generated"}`; on tailoring failure leaves `status="new"` and surfaces the error.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_scan_generate_api.py
import pytest
from fastapi.testclient import TestClient
from jobhunter.web.api import create_app
from jobhunter.web.routes.scan import get_store, get_tailor
from tests.fake_scan_store import FakeScanStore

class _FakeOutcome:
    def __init__(self, slug): self.slug = slug

@pytest.fixture
def store():
    return FakeScanStore()

@pytest.fixture
def client(store):
    app = create_app()
    app.dependency_overrides[get_store] = lambda: store
    return app, store

def _seed(app):
    from fastapi.testclient import TestClient
    c = TestClient(app)
    c.post("/api/scan/results", json={"site_summary": {}, "candidates": [{
        "site": "indeed", "url": "https://jobs.example.com/1", "title": "Dev",
        "company": "Acme", "location": "Remote", "jd_text": "JD body",
        "fit_reason": "x", "fit_score": 0.5}]})
    return c

def test_generate_success_sets_generated_and_slug(client):
    app, store = client
    app.dependency_overrides[get_tailor] = lambda: (lambda jd_text, url, source: "my-slug")
    c = _seed(app)
    cid = c.get("/api/scan/candidates").json()[0]["id"]
    r = c.post(f"/api/scan/candidates/{cid}/generate")
    assert r.status_code == 200
    assert r.json() == {"slug": "my-slug", "status": "generated"}
    assert c.get("/api/scan/candidates").json()[0]["status"] == "generated"

def test_generate_failure_leaves_new(client):
    app, store = client
    def _boom(jd_text, url, source): raise RuntimeError("spend cap")
    app.dependency_overrides[get_tailor] = lambda: _boom
    c = _seed(app)
    cid = c.get("/api/scan/candidates").json()[0]["id"]
    r = c.post(f"/api/scan/candidates/{cid}/generate")
    assert r.status_code == 502
    assert c.get("/api/scan/candidates").json()[0]["status"] == "new"

def test_generate_unknown_candidate_404(client):
    app, store = client
    app.dependency_overrides[get_tailor] = lambda: (lambda jd_text, url, source: "s")
    from fastapi.testclient import TestClient
    r = TestClient(app).post("/api/scan/candidates/nope/generate")
    assert r.status_code == 404
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/test_scan_generate_api.py -v`
Expected: FAIL — `ImportError: get_tailor` / 404.

- [ ] **Step 3: Add `get_tailor` + endpoint to `scan.py`**

```python
from collections.abc import Callable

TailorFn = Callable[[str, str, str], str]  # (jd_text, url, source) -> slug


def get_tailor() -> TailorFn:
    """Production tailor: runs the existing pipeline, returns the new slug.

    Overridden in tests. Keeps DECISIONS.md §4 — the only LLM path is
    run_tailoring()."""
    def _run(jd_text: str, url: str, source: str) -> str:
        from jobhunter.canonical_cv import read_canonical_cv
        from jobhunter.runtime_config import load_runtime_config
        from jobhunter.tailoring import run_tailoring
        outcome = run_tailoring(
            read_canonical_cv(), jd_text, config=load_runtime_config(),
            jd_source=source, url=url or None,
        )
        return outcome.out_dir.name
    return _run


@router.post("/api/scan/candidates/{candidate_id}/generate")
def generate_from_candidate(
    candidate_id: str,
    store: ScanStore = Depends(get_store),
    tailor: TailorFn = Depends(get_tailor),
) -> dict[str, Any]:
    cand = store.get_candidate(candidate_id)
    if cand is None:
        raise HTTPException(status_code=404, detail="candidate not found")
    try:
        slug = tailor(cand.jd_text, cand.url, cand.site)
    except Exception as exc:  # noqa: BLE001 - leave candidate retryable
        raise HTTPException(status_code=502, detail=f"tailoring failed: {exc}") from exc
    store.set_candidate_status(candidate_id, status="generated", slug=slug)
    return {"slug": slug, "status": "generated"}
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_scan_generate_api.py -v`
Expected: PASS.

- [ ] **Step 5: Run full backend suite**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/jobhunter/web/routes/scan.py tests/unit/test_scan_generate_api.py
git commit -m "feat(scan): generate CV from candidate (reuses run_tailoring) [F6]"
```

---

## Task 10: Frontend API client `scan.ts`

**Files:**
- Create: `src/jobhunter/web/frontend/src/api/scan.ts`

**Interfaces:**
- Produces: types `ScanSettings`, `Candidate`, `Scan`, `SITE_LABEL`; functions `getScanSettings`, `putScanSettings`, `listScans`, `listCandidates`, `dismissCandidate`, `generateFromCandidate`.

- [ ] **Step 1: Write the client**

```typescript
export type Site = "indeed" | "onlinejobs_ph" | "jobstreet" | "linkedin";
export const SITES: Site[] = ["indeed", "onlinejobs_ph", "jobstreet", "linkedin"];
export const SITE_LABEL: Record<Site, string> = {
  indeed: "Indeed",
  onlinejobs_ph: "OnlineJobs PH",
  jobstreet: "JobStreet",
  linkedin: "LinkedIn",
};

export type ScanSettings = {
  search_titles: string[];
  sites_enabled: Site[];
  picks_per_site: number;
  enabled: boolean;
  updated_at: string;
};

export type CandidateStatus = "new" | "generated" | "dismissed";

export type Candidate = {
  id: string;
  scan_id: string;
  site: Site;
  url: string;
  title: string;
  company: string | null;
  location: string | null;
  jd_text: string;
  fit_reason: string | null;
  fit_score: number | null;
  status: CandidateStatus;
  slug: string | null;
  created_at: string;
};

export type Scan = {
  id: string;
  started_at: string | null;
  finished_at: string | null;
  status: string;
  site_summary: Record<string, { status: string; count: number }>;
  created_at: string;
};

async function json<T>(resp: Response, what: string): Promise<T> {
  if (!resp.ok) throw new Error(`${what} failed: ${resp.status}`);
  return resp.json() as Promise<T>;
}

export async function getScanSettings(): Promise<ScanSettings> {
  return json(await fetch("/api/scan/settings"), "getScanSettings");
}

export async function putScanSettings(s: ScanSettings): Promise<ScanSettings> {
  return json(
    await fetch("/api/scan/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(s),
    }),
    "putScanSettings",
  );
}

export async function listScans(): Promise<Scan[]> {
  return json(await fetch("/api/scan/scans"), "listScans");
}

export async function listCandidates(scanId?: string): Promise<Candidate[]> {
  const q = scanId ? `?scan_id=${encodeURIComponent(scanId)}` : "";
  return json(await fetch(`/api/scan/candidates${q}`), "listCandidates");
}

export async function dismissCandidate(id: string): Promise<Candidate> {
  return json(
    await fetch(`/api/scan/candidates/${encodeURIComponent(id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "dismissed" }),
    }),
    "dismissCandidate",
  );
}

export async function generateFromCandidate(
  id: string,
): Promise<{ slug: string; status: string }> {
  return json(
    await fetch(`/api/scan/candidates/${encodeURIComponent(id)}/generate`, {
      method: "POST",
    }),
    "generateFromCandidate",
  );
}
```

- [ ] **Step 2: Build to typecheck**

Run (cwd `src/jobhunter/web/frontend`): `npm run build`
Expected: build succeeds (tsc clean).

- [ ] **Step 3: Commit**

```bash
git add src/jobhunter/web/frontend/src/api/scan.ts
git commit -m "feat(scan-ui): scan API client + types [F1,F5,F6]"
```

---

## Task 11: Settings page "Job Scan" section (F1 UI)

**Files:**
- Modify: `src/jobhunter/web/frontend/src/SettingsPage.tsx`

**Interfaces:**
- Consumes: `getScanSettings`, `putScanSettings`, `SITES`, `SITE_LABEL` from `api/scan`.

- [ ] **Step 1: Add a `JobScanSettings` section component**

Add to `SettingsPage.tsx` (a self-contained section rendered within the existing page; follow the file's existing card/styling classes). Behavior:
- On mount, `getScanSettings()` → populate form state.
- Fields: a textarea or chip-input for `search_titles` (one per line), checkboxes for each site in `SITES` (toggling `sites_enabled`), a number input for `picks_per_site` (1–10), a toggle for `enabled`.
- "Save" calls `putScanSettings(...)`; show success + validation error (the API returns 422 with a `detail` string — surface it).

```tsx
// inside SettingsPage.tsx
import { useEffect, useState } from "react";
import {
  getScanSettings, putScanSettings, SITES, SITE_LABEL,
  type ScanSettings, type Site,
} from "./api/scan";

function JobScanSettingsSection() {
  const [s, setS] = useState<ScanSettings | null>(null);
  const [titles, setTitles] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    getScanSettings().then((data) => {
      setS(data);
      setTitles(data.search_titles.join("\n"));
    });
  }, []);

  if (!s) return null;

  const toggleSite = (site: Site) =>
    setS({
      ...s,
      sites_enabled: s.sites_enabled.includes(site)
        ? s.sites_enabled.filter((x) => x !== site)
        : [...s.sites_enabled, site],
    });

  const save = async () => {
    setMsg(null);
    setErr(null);
    try {
      const next = {
        ...s,
        search_titles: titles.split("\n").map((t) => t.trim()).filter(Boolean),
      };
      const saved = await putScanSettings(next);
      setS(saved);
      setMsg("Saved.");
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  return (
    <section className="mb-stack-lg">
      <h2 className="text-title-lg font-bold mb-stack-sm">Job Scan</h2>
      <label className="block text-label-md mb-1">Search titles (one per line)</label>
      <textarea
        className="w-full border rounded p-2 mb-stack-sm"
        rows={4}
        value={titles}
        onChange={(e) => setTitles(e.target.value)}
      />
      <div className="flex flex-wrap gap-stack-sm mb-stack-sm">
        {SITES.map((site) => (
          <label key={site} className="flex items-center gap-1">
            <input
              type="checkbox"
              checked={s.sites_enabled.includes(site)}
              onChange={() => toggleSite(site)}
            />
            {SITE_LABEL[site]}
          </label>
        ))}
      </div>
      <label className="block text-label-md mb-1">Picks per site</label>
      <input
        type="number"
        min={1}
        max={10}
        className="border rounded p-2 mb-stack-sm w-24"
        value={s.picks_per_site}
        onChange={(e) => setS({ ...s, picks_per_site: Number(e.target.value) })}
      />
      <label className="flex items-center gap-1 mb-stack-sm">
        <input
          type="checkbox"
          checked={s.enabled}
          onChange={(e) => setS({ ...s, enabled: e.target.checked })}
        />
        Scanning enabled
      </label>
      <div>
        <button className="px-4 py-2 bg-primary text-on-primary rounded" onClick={save}>
          Save Job Scan settings
        </button>
        {msg && <span className="ml-3 text-green-600">{msg}</span>}
        {err && <span className="ml-3 text-red-600">{err}</span>}
      </div>
    </section>
  );
}
```
Render `<JobScanSettingsSection />` within the existing `SettingsPage` return (place sensibly among current sections; match surrounding markup/classes).

- [ ] **Step 2: Build**

Run (cwd frontend): `npm run build`
Expected: success.

- [ ] **Step 3: Commit**

```bash
git add src/jobhunter/web/frontend/src/SettingsPage.tsx
git commit -m "feat(scan-ui): Job Scan settings section [F1]"
```

---

## Task 12: JobScanPage + sidebar + route (F5)

**Files:**
- Create: `src/jobhunter/web/frontend/src/JobScanPage.tsx`
- Modify: `src/jobhunter/web/frontend/src/Sidebar.tsx` (add nav item)
- Modify: `src/jobhunter/web/frontend/src/App.tsx` (add route + import)

**Interfaces:**
- Consumes: `listScans`, `listCandidates`, `dismissCandidate`, `generateFromCandidate`, `SITE_LABEL` from `api/scan`.

- [ ] **Step 1: Write `JobScanPage.tsx`**

```tsx
import { useEffect, useState } from "react";
import {
  listScans, listCandidates, dismissCandidate, generateFromCandidate,
  SITE_LABEL, type Scan, type Candidate, type Site,
} from "./api/scan";

export function JobScanPage() {
  const [scans, setScans] = useState<Scan[]>([]);
  const [cands, setCands] = useState<Candidate[]>([]);
  const [busy, setBusy] = useState<string | null>(null);

  const refresh = () => {
    listScans().then(setScans);
    listCandidates().then(setCands);
  };
  useEffect(refresh, []);

  const onGenerate = async (id: string) => {
    setBusy(id);
    try {
      const { slug } = await generateFromCandidate(id);
      window.location.href = `/packages/${slug}`;
    } catch (e) {
      alert(`Generate failed: ${(e as Error).message}`);
      setBusy(null);
    }
  };

  const onDismiss = async (id: string) => {
    await dismissCandidate(id);
    refresh();
  };

  if (scans.length === 0) {
    return (
      <div className="p-gutter">
        <h1 className="text-headline-md font-bold mb-stack-md">Job Scan</h1>
        <p className="text-on-surface-variant">No scans yet.</p>
      </div>
    );
  }

  return (
    <div className="p-gutter">
      <h1 className="text-headline-md font-bold mb-stack-md">Job Scan</h1>
      {scans.map((scan) => {
        const scanCands = cands.filter((c) => c.scan_id === scan.id);
        const bySite: Record<string, Candidate[]> = {};
        for (const c of scanCands) (bySite[c.site] ??= []).push(c);
        return (
          <section key={scan.id} className="mb-stack-lg border-b pb-stack-md">
            <div className="flex items-center gap-stack-sm mb-stack-sm">
              <h2 className="text-title-lg font-bold">{scan.created_at}</h2>
              {Object.entries(scan.site_summary).map(([site, info]) => (
                <span key={site} className="text-label-sm px-2 py-0.5 rounded bg-surface-container-high">
                  {SITE_LABEL[site as Site] ?? site}: {info.status} ({info.count})
                </span>
              ))}
            </div>
            {Object.entries(bySite).map(([site, list]) => (
              <div key={site} className="mb-stack-sm">
                <h3 className="text-title-md font-bold mb-1">{SITE_LABEL[site as Site] ?? site}</h3>
                <div className="grid gap-stack-sm">
                  {list.map((c) => (
                    <div key={c.id} className={`border rounded p-3 ${c.status === "dismissed" ? "opacity-50" : ""}`}>
                      <div className="font-bold">{c.title}</div>
                      <div className="text-on-surface-variant text-body-sm">
                        {c.company ?? "—"} · {c.location ?? "—"}
                        {c.fit_score != null && ` · fit ${c.fit_score}`}
                      </div>
                      {c.fit_reason && <div className="text-body-sm mt-1">{c.fit_reason}</div>}
                      <details className="mt-1">
                        <summary className="cursor-pointer text-body-sm">JD preview</summary>
                        <pre className="whitespace-pre-wrap text-body-sm mt-1">{c.jd_text.slice(0, 800)}</pre>
                      </details>
                      <div className="flex gap-stack-sm mt-2">
                        <a href={c.url} target="_blank" rel="noreferrer" className="text-primary underline text-body-sm">
                          Open posting
                        </a>
                        {c.status === "new" && (
                          <>
                            <button disabled={busy === c.id} className="px-3 py-1 bg-primary text-on-primary rounded text-body-sm" onClick={() => onGenerate(c.id)}>
                              {busy === c.id ? "Generating…" : "Generate CV"}
                            </button>
                            <button className="px-3 py-1 border rounded text-body-sm" onClick={() => onDismiss(c.id)}>
                              Dismiss
                            </button>
                          </>
                        )}
                        {c.status === "generated" && c.slug && (
                          <a href={`/packages/${c.slug}`} className="text-primary underline text-body-sm">
                            View package
                          </a>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </section>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: Add the sidebar nav item**

In `Sidebar.tsx`, add an icon (reuse a simple SVG) and a `NAV_ITEMS` entry:
```tsx
const IconJobScan = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="2" />
    <line x1="16.5" y1="16.5" x2="21" y2="21" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    <line x1="8" y1="11" x2="14" y2="11" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
  </svg>
);
```
Add to `NAV_ITEMS` (after Applications):
```tsx
  { label: "Job Scan", to: "/job-scan", Icon: IconJobScan },
```

- [ ] **Step 3: Add the route in `App.tsx`**

Import: `import { JobScanPage } from "./JobScanPage";`
Add route inside `<Routes>` (before the `*` catch-all):
```tsx
            <Route path="/job-scan" element={<JobScanPage />} />
```

- [ ] **Step 4: Build**

Run (cwd frontend): `npm run build`
Expected: success.

- [ ] **Step 5: Manual verify**

Run `jobhunter`, open `http://127.0.0.1:8765/job-scan`. With a seeded scan (POST a sample to `/api/scan/results` with `example.com` URLs), confirm scans render grouped by site with Generate/Dismiss. Capture a screenshot.

- [ ] **Step 6: Commit**

```bash
git add src/jobhunter/web/frontend/src/JobScanPage.tsx src/jobhunter/web/frontend/src/Sidebar.tsx src/jobhunter/web/frontend/src/App.tsx
git commit -m "feat(scan-ui): Job Scan dashboard page + nav + route [F5,F6]"
```

---

## Task 13: Docs — DECISIONS.md + README

**Files:**
- Modify: `DECISIONS.md` (append a dated entry)
- Modify: `README.md` (Job Scan setup + settings)

- [ ] **Step 1: Append a DECISIONS.md entry** (additive — do not edit §1–§7)

Record: (1) the scanner as an **external ingestion agent** (same category as n8n flows; keeps §4 single-LLM-provider intact); (2) **Supabase reuse** for scan persistence (extends §7); (3) **dashboard-only notifications** preserving the no-job-board-hostname guardrail (FR44/FR11). Reference both spec docs.

- [ ] **Step 2: Update README** with: the Job Scan settings section, the `/api/scan/*` endpoints, and a forward-reference to the F2 (n8n custom-image) plan for the scan engine.

- [ ] **Step 3: Commit**

```bash
git add DECISIONS.md README.md
git commit -m "docs(scan): record external-ingestion-agent decision + setup [F1-F6]"
```

---

## Self-Review (completed during planning)

- **Spec coverage:** F1 → Tasks 4,5,11; F3 → Tasks 1,2,3,5,6,8; F4 → Task 7; F5 → Tasks 8,12; F6 → Tasks 9,10,12. F2 (n8n custom image + workflow + scan prompt + canonical-profile endpoint) is the **separate infra plan** (not in this app-side plan) — note: the `/api/canonical-profile` endpoint that F2 consumes is the one remaining app-side dependency; **add it as Task 6.5 or fold into the F2 plan**. (Decision: implemented in the F2 plan alongside the prompt that consumes it, since its shape is driven by the prompt.)
- **Placeholder scan:** none — all steps carry real code. The one explicit correction note is the stray `//` in the Task 2 docstring (called out inline).
- **Type consistency:** `record_scan` returns `(Scan, int, int)` everywhere; `set_candidate_status(status=, slug=)` consistent across Protocol/fake/pg; `get_tailor` signature `(jd_text, url, source) -> slug` matches test stubs.

> **Open item to resolve at execution:** the `GET /api/canonical-profile` endpoint (condensed CV for ranking) and `canonical_profile.py` are deferred to the F2 plan because their shape is dictated by the scan prompt. If you prefer them app-side-first, add a task mirroring Task 4's structure: `build_canonical_profile(cv) -> dict` (name, label, summary, skill names, recent work titles) + a `GET /api/canonical-profile` route returning it, with a unit test asserting the condensed shape.
