# Application Tracker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a package-anchored application tracker — an "I Applied" button that records a job, a status lifecycle you can update, notes, a job-posting link, and a kanban overview — backed by Supabase Postgres while CV packages stay on disk.

**Architecture:** React keeps calling `/api/*`. FastAPI gains an `applications` router that reads/writes a Supabase Postgres database (two tables) through a small store module behind a `Protocol` interface, so route logic is unit-tested with an in-memory fake and the real SQL store is tested against a local Postgres. CV/drift artifacts under `./out/` are untouched.

**Tech Stack:** Python 3.11, FastAPI (sync handlers), `psycopg` v3 (synchronous Postgres driver), Supabase (Postgres + CLI for local dev + migrations), pytest + FastAPI `TestClient`, React + TypeScript + React Router + Tailwind.

**Reference spec:** `docs/superpowers/specs/2026-06-07-application-tracker-design.md`

---

## File Structure

**Backend (new):**
- `supabase/migrations/20260607000000_application_tracker.sql` — schema (2 tables + partial unique index).
- `src/jobhunter/application_tracker.py` — domain: `Application` + `StatusChange` dataclasses, `STATUSES` / `INITIAL_STATUS` constants, `validate_status()`, `ApplicationStore` Protocol.
- `src/jobhunter/application_store_pg.py` — `PostgresApplicationStore` (psycopg v3) implementing the Protocol; `from_env()` reads `SUPABASE_DB_URL`.
- `src/jobhunter/web/routes/applications.py` — `APIRouter` with POST/PATCH/GET/GET-one + `get_store` dependency + Pydantic request models.

**Backend (modified):**
- `pyproject.toml` — add `psycopg[binary]>=3.1` to the `web` extra.
- `src/jobhunter/web/api.py` — mount `applications_router`.
- `.env.example` (create if absent) + `README.md` + `DECISIONS.md` — document Supabase.

**Tests (new):**
- `tests/fake_application_store.py` — `FakeApplicationStore` (in-memory, importable via the `.` pythonpath entry).
- `tests/unit/test_application_tracker.py` — domain + fake-store behavior.
- `tests/integration/test_applications_api.py` — route tests via `dependency_overrides` with the fake store.
- `tests/integration/test_application_store_pg.py` — real Postgres store, `skipif` no `TEST_DATABASE_URL`.

**Frontend (new):**
- `src/jobhunter/web/frontend/src/api/applications.ts` — typed client + `ApplicationStatus` type.
- `src/jobhunter/web/frontend/src/ApplicationsPage.tsx` — kanban overview.
- `src/jobhunter/web/frontend/src/components/ApplyControl.tsx` — "I Applied" button → status dropdown + notes.

**Frontend (modified):**
- `src/jobhunter/web/frontend/src/PackagePage.tsx` — render `<ApplyControl>` in the header.
- `src/jobhunter/web/frontend/src/PastePanel.tsx` — optional "Job posting link" input; send `url`.
- `src/jobhunter/web/frontend/src/App.tsx` — add `/applications` route.
- `src/jobhunter/web/frontend/src/Sidebar.tsx` — add "Applications" nav entry.

---

## Task 1: Supabase local dev + schema migration

**Files:**
- Create: `supabase/migrations/20260607000000_application_tracker.sql`
- Create: `.env.example`

- [ ] **Step 1: Initialize Supabase local stack**

Run (Supabase CLI must be installed — `brew install supabase/tap/supabase`):
```bash
cd /Users/davecharmbulaquena/Desktop/job_hunter
supabase init      # accept defaults; creates supabase/ dir + config.toml
supabase start     # boots local Postgres + Studio in Docker; prints a "DB URL"
```
Expected: output includes `DB URL: postgresql://postgres:postgres@127.0.0.1:54322/postgres`. Leave it running.

- [ ] **Step 2: Write the migration SQL**

Create `supabase/migrations/20260607000000_application_tracker.sql`:
```sql
-- Application tracker (spec: 2026-06-07-application-tracker-design.md)
create extension if not exists pgcrypto;  -- gen_random_uuid()

create table if not exists applications (
    id          uuid primary key default gen_random_uuid(),
    slug        text,
    job_title   text not null,
    company     text,
    url         text,
    status      text not null default 'applied'
                check (status in ('applied','interviewing','offer','rejected','withdrawn')),
    notes       text,
    applied_at  timestamptz not null default now(),
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

-- One tracker row per package; many package-less rows (slug null) allowed.
create unique index if not exists applications_slug_unique
    on applications (slug) where slug is not null;

create table if not exists application_status_history (
    id              uuid primary key default gen_random_uuid(),
    application_id  uuid not null references applications(id) on delete cascade,
    from_status     text,
    to_status       text not null,
    changed_at      timestamptz not null default now()
);

create index if not exists ash_application_id_idx
    on application_status_history (application_id);
```

- [ ] **Step 3: Apply the migration locally**

Run:
```bash
supabase db reset    # re-applies all migrations to the local DB
```
Expected: completes without error, mentions `20260607000000_application_tracker`.

- [ ] **Step 4: Verify the schema exists**

Run:
```bash
psql postgresql://postgres:postgres@127.0.0.1:54322/postgres -c "\d applications"
```
Expected: table description listing columns `id, slug, job_title, company, url, status, notes, applied_at, created_at, updated_at`.

- [ ] **Step 5: Add the env var template**

Create `.env.example` (append if it already exists):
```bash
# Supabase Postgres connection for the application tracker.
# Local dev (supabase start): postgresql://postgres:postgres@127.0.0.1:54322/postgres
# Hosted: copy the "Connection string" (URI, session pooler) from your Supabase project settings.
SUPABASE_DB_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres
```
Then create your real `.env` with the same line (do NOT commit `.env`).

- [ ] **Step 6: Commit**

```bash
git add supabase/migrations/20260607000000_application_tracker.sql .env.example supabase/config.toml
git commit -m "feat(db): supabase local stack + application tracker schema migration"
```

---

## Task 2: Domain module — dataclasses, statuses, store Protocol

**Files:**
- Create: `src/jobhunter/application_tracker.py`
- Test: `tests/unit/test_application_tracker.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_application_tracker.py`:
```python
from __future__ import annotations

import pytest

from jobhunter.application_tracker import (
    INITIAL_STATUS,
    STATUSES,
    Application,
    validate_status,
)


def test_initial_status_is_applied():
    assert INITIAL_STATUS == "applied"


def test_statuses_are_the_five_lifecycle_values():
    assert STATUSES == ("applied", "interviewing", "offer", "rejected", "withdrawn")


def test_validate_status_accepts_known_value():
    validate_status("interviewing")  # no raise


def test_validate_status_rejects_unknown_value():
    with pytest.raises(ValueError, match="unknown status"):
        validate_status("ghosted")


def test_application_dataclass_round_trips_to_dict():
    app = Application(
        id="11111111-1111-1111-1111-111111111111",
        slug="20260607T010101Z-acme",
        job_title="Senior Engineer",
        company="Acme",
        url="https://jobs.example/1",
        status="applied",
        notes=None,
        applied_at="2026-06-07T01:01:01Z",
        created_at="2026-06-07T01:01:01Z",
        updated_at="2026-06-07T01:01:01Z",
    )
    d = app.to_dict()
    assert d["job_title"] == "Senior Engineer"
    assert d["status"] == "applied"
    assert d["slug"] == "20260607T010101Z-acme"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_application_tracker.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jobhunter.application_tracker'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/jobhunter/application_tracker.py`:
```python
"""Application-tracker domain types (spec 2026-06-07).

Pure data + the storage interface. No I/O, no SQL, no FastAPI — this module
is import-safe without a database so the route layer can be unit-tested
against an in-memory fake (see tests/fake_application_store.py).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol


STATUSES: tuple[str, ...] = (
    "applied",
    "interviewing",
    "offer",
    "rejected",
    "withdrawn",
)
INITIAL_STATUS = "applied"


def validate_status(status: str) -> None:
    """Raise ValueError if *status* is not a known lifecycle value."""
    if status not in STATUSES:
        raise ValueError(f"unknown status: {status!r} (allowed: {', '.join(STATUSES)})")


@dataclass
class Application:
    id: str
    slug: str | None
    job_title: str
    company: str | None
    url: str | None
    status: str
    notes: str | None
    applied_at: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class StatusChange:
    from_status: str | None
    to_status: str
    changed_at: str

    def to_dict(self) -> dict:
        return asdict(self)


class ApplicationStore(Protocol):
    """Storage interface the route layer depends on."""

    def create(
        self,
        *,
        slug: str | None,
        job_title: str,
        company: str | None,
        url: str | None,
    ) -> Application: ...

    def get(self, app_id: str) -> Application | None: ...

    def get_by_slug(self, slug: str) -> Application | None: ...

    def list(self, *, status: str | None = None) -> list[Application]: ...

    def update(
        self,
        app_id: str,
        *,
        status: str | None = None,
        notes: str | None = None,
    ) -> Application | None: ...

    def history(self, app_id: str) -> list[StatusChange]: ...


__all__ = [
    "STATUSES",
    "INITIAL_STATUS",
    "Application",
    "StatusChange",
    "ApplicationStore",
    "validate_status",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_application_tracker.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/jobhunter/application_tracker.py tests/unit/test_application_tracker.py
git commit -m "feat(tracker): application domain types + status validation + store Protocol"
```

---

## Task 3: In-memory fake store (test double)

**Files:**
- Create: `tests/fake_application_store.py`
- Test: extend `tests/unit/test_application_tracker.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_application_tracker.py`:
```python
from tests.fake_application_store import FakeApplicationStore


def test_fake_store_create_sets_initial_status_and_history():
    store = FakeApplicationStore()
    app = store.create(slug="s1", job_title="Eng", company="Acme", url=None)
    assert app.status == "applied"
    assert app.id
    hist = store.history(app.id)
    assert len(hist) == 1
    assert hist[0].from_status is None
    assert hist[0].to_status == "applied"


def test_fake_store_get_by_slug():
    store = FakeApplicationStore()
    created = store.create(slug="s2", job_title="Eng", company=None, url=None)
    assert store.get_by_slug("s2").id == created.id
    assert store.get_by_slug("missing") is None


def test_fake_store_update_status_appends_history():
    store = FakeApplicationStore()
    app = store.create(slug="s3", job_title="Eng", company=None, url=None)
    updated = store.update(app.id, status="interviewing")
    assert updated.status == "interviewing"
    hist = store.history(app.id)
    assert [h.to_status for h in hist] == ["applied", "interviewing"]


def test_fake_store_update_notes_only_no_history_row():
    store = FakeApplicationStore()
    app = store.create(slug="s4", job_title="Eng", company=None, url=None)
    store.update(app.id, notes="Prep system design")
    assert store.get(app.id).notes == "Prep system design"
    assert len(store.history(app.id)) == 1  # notes-only change adds no history


def test_fake_store_list_filters_by_status():
    store = FakeApplicationStore()
    a = store.create(slug="a", job_title="A", company=None, url=None)
    store.create(slug="b", job_title="B", company=None, url=None)
    store.update(a.id, status="offer")
    assert {x.slug for x in store.list(status="offer")} == {"a"}
    assert len(store.list()) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_application_tracker.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tests.fake_application_store'`.

- [ ] **Step 3: Write minimal implementation**

Create `tests/fake_application_store.py`:
```python
"""In-memory ApplicationStore for fast, DB-free tests.

Importable as `tests.fake_application_store` because pyproject sets
pythonpath = ["src", "."].
"""

from __future__ import annotations

import itertools

from jobhunter.application_tracker import (
    INITIAL_STATUS,
    Application,
    StatusChange,
    validate_status,
)

_FIXED_TS = "2026-06-07T00:00:00Z"


class FakeApplicationStore:
    def __init__(self) -> None:
        self._apps: dict[str, Application] = {}
        self._history: dict[str, list[StatusChange]] = {}
        self._ids = (f"app-{n}" for n in itertools.count(1))

    def create(self, *, slug, job_title, company, url) -> Application:
        app_id = next(self._ids)
        app = Application(
            id=app_id,
            slug=slug,
            job_title=job_title,
            company=company,
            url=url,
            status=INITIAL_STATUS,
            notes=None,
            applied_at=_FIXED_TS,
            created_at=_FIXED_TS,
            updated_at=_FIXED_TS,
        )
        self._apps[app_id] = app
        self._history[app_id] = [
            StatusChange(from_status=None, to_status=INITIAL_STATUS, changed_at=_FIXED_TS)
        ]
        return app

    def get(self, app_id) -> Application | None:
        return self._apps.get(app_id)

    def get_by_slug(self, slug) -> Application | None:
        for app in self._apps.values():
            if app.slug == slug:
                return app
        return None

    def list(self, *, status=None) -> list[Application]:
        apps = list(self._apps.values())
        if status is not None:
            apps = [a for a in apps if a.status == status]
        return sorted(apps, key=lambda a: a.updated_at, reverse=True)

    def update(self, app_id, *, status=None, notes=None) -> Application | None:
        app = self._apps.get(app_id)
        if app is None:
            return None
        if status is not None and status != app.status:
            validate_status(status)
            self._history[app_id].append(
                StatusChange(from_status=app.status, to_status=status, changed_at=_FIXED_TS)
            )
            app.status = status
        if notes is not None:
            app.notes = notes
        app.updated_at = _FIXED_TS
        return app

    def history(self, app_id) -> list[StatusChange]:
        return list(self._history.get(app_id, []))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_application_tracker.py -v`
Expected: PASS (all tests, including the 5 new fake-store tests).

- [ ] **Step 5: Commit**

```bash
git add tests/fake_application_store.py tests/unit/test_application_tracker.py
git commit -m "test(tracker): in-memory fake ApplicationStore + behavior tests"
```

---

## Task 4: Applications router (route logic, tested with the fake)

**Files:**
- Create: `src/jobhunter/web/routes/applications.py`
- Test: `tests/integration/test_applications_api.py`

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_applications_api.py`:
```python
"""Route tests for /api/applications using the in-memory fake store.

The real Postgres store is exercised separately in
test_application_store_pg.py (skipped without TEST_DATABASE_URL).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from jobhunter.web.api import create_app
from jobhunter.web.routes.applications import get_store
from tests.fake_application_store import FakeApplicationStore


@pytest.fixture()
def client_and_store():
    store = FakeApplicationStore()
    app = create_app()
    app.dependency_overrides[get_store] = lambda: store
    return TestClient(app), store


def test_post_creates_application_at_applied(client_and_store):
    client, _ = client_and_store
    resp = client.post(
        "/api/applications",
        json={"slug": "20260607T010101Z-acme", "job_title": "Eng", "company": "Acme", "url": "https://x/1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "applied"
    assert body["job_title"] == "Eng"
    assert body["id"]


def test_post_is_idempotent_on_slug(client_and_store):
    client, _ = client_and_store
    first = client.post("/api/applications", json={"slug": "dup", "job_title": "Eng"}).json()
    resp = client.post("/api/applications", json={"slug": "dup", "job_title": "Eng"})
    assert resp.status_code == 200  # existing returned, not duplicated
    assert resp.json()["id"] == first["id"]


def test_patch_updates_status(client_and_store):
    client, _ = client_and_store
    app = client.post("/api/applications", json={"slug": "s", "job_title": "Eng"}).json()
    resp = client.patch(f"/api/applications/{app['id']}", json={"status": "interviewing"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "interviewing"


def test_patch_rejects_unknown_status(client_and_store):
    client, _ = client_and_store
    app = client.post("/api/applications", json={"slug": "s", "job_title": "Eng"}).json()
    resp = client.patch(f"/api/applications/{app['id']}", json={"status": "ghosted"})
    assert resp.status_code == 422


def test_patch_missing_application_is_404(client_and_store):
    client, _ = client_and_store
    resp = client.patch("/api/applications/nope", json={"notes": "x"})
    assert resp.status_code == 404


def test_get_lists_and_filters(client_and_store):
    client, _ = client_and_store
    a = client.post("/api/applications", json={"slug": "a", "job_title": "A"}).json()
    client.post("/api/applications", json={"slug": "b", "job_title": "B"})
    client.patch(f"/api/applications/{a['id']}", json={"status": "offer"})
    assert len(client.get("/api/applications").json()) == 2
    offers = client.get("/api/applications?status=offer").json()
    assert [x["slug"] for x in offers] == ["a"]


def test_get_one_includes_history(client_and_store):
    client, _ = client_and_store
    app = client.post("/api/applications", json={"slug": "s", "job_title": "Eng"}).json()
    client.patch(f"/api/applications/{app['id']}", json={"status": "interviewing"})
    body = client.get(f"/api/applications/{app['id']}").json()
    assert body["status"] == "interviewing"
    assert [h["to_status"] for h in body["history"]] == ["applied", "interviewing"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/integration/test_applications_api.py -v`
Expected: FAIL — `ImportError` on `jobhunter.web.routes.applications`.

- [ ] **Step 3: Write minimal implementation**

Create `src/jobhunter/web/routes/applications.py`:
```python
"""Application tracker API (spec 2026-06-07).

Mirrors the existing route style: a module-level `APIRouter`, sync handlers,
no business logic beyond shaping requests/responses. Storage is injected via
the `get_store` dependency so tests override it with an in-memory fake and
production uses the Supabase-backed PostgresApplicationStore.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from jobhunter.application_store_pg import PostgresApplicationStore
from jobhunter.application_tracker import ApplicationStore, validate_status


router = APIRouter()


def get_store() -> ApplicationStore:
    """Production store. Overridden in tests via app.dependency_overrides."""
    return PostgresApplicationStore.from_env()


class CreateApplicationRequest(BaseModel):
    job_title: str = Field(min_length=1)
    slug: str | None = None
    company: str | None = None
    url: str | None = None


class UpdateApplicationRequest(BaseModel):
    status: str | None = None
    notes: str | None = None


@router.post("/api/applications", status_code=201)
def create_application(
    payload: CreateApplicationRequest,
    response: "Any" = None,  # placeholder to satisfy signature; replaced below
    store: ApplicationStore = Depends(get_store),
) -> dict[str, Any]:
    # Idempotency: if this package is already tracked, return the existing row (200).
    if payload.slug:
        existing = store.get_by_slug(payload.slug)
        if existing is not None:
            from fastapi import Response

            return _ok_existing(existing)
    app = store.create(
        slug=payload.slug,
        job_title=payload.job_title,
        company=payload.company,
        url=payload.url,
    )
    return app.to_dict()


def _ok_existing(app) -> dict[str, Any]:
    raise HTTPException(status_code=200, detail=app.to_dict())  # replaced in Step 3b


@router.patch("/api/applications/{app_id}")
def update_application(
    app_id: str,
    payload: UpdateApplicationRequest,
    store: ApplicationStore = Depends(get_store),
) -> dict[str, Any]:
    if payload.status is not None:
        try:
            validate_status(payload.status)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    updated = store.update(app_id, status=payload.status, notes=payload.notes)
    if updated is None:
        raise HTTPException(status_code=404, detail="application not found")
    return updated.to_dict()


@router.get("/api/applications")
def list_applications(
    status: str | None = None,
    store: ApplicationStore = Depends(get_store),
) -> list[dict[str, Any]]:
    if status is not None:
        try:
            validate_status(status)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    return [a.to_dict() for a in store.list(status=status)]


@router.get("/api/applications/{app_id}")
def get_application(
    app_id: str,
    store: ApplicationStore = Depends(get_store),
) -> dict[str, Any]:
    app = store.get(app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="application not found")
    body = app.to_dict()
    body["history"] = [h.to_dict() for h in store.history(app_id)]
    return body


__all__ = ["router", "get_store"]
```

- [ ] **Step 3b: Fix the idempotency 200-response (clean implementation)**

The `_ok_existing` placeholder above abuses HTTPException. Replace the `create_application` handler and delete `_ok_existing` with this correct version that returns a 200 for the existing row and 201 for a new one using an explicit `Response`:
```python
from fastapi import Response


@router.post("/api/applications")
def create_application(
    payload: CreateApplicationRequest,
    response: Response,
    store: ApplicationStore = Depends(get_store),
) -> dict[str, Any]:
    if payload.slug:
        existing = store.get_by_slug(payload.slug)
        if existing is not None:
            response.status_code = 200
            return existing.to_dict()
    app = store.create(
        slug=payload.slug,
        job_title=payload.job_title,
        company=payload.company,
        url=payload.url,
    )
    response.status_code = 201
    return app.to_dict()
```
Remove the old `@router.post(..., status_code=201)` handler and the `_ok_existing` function entirely.

- [ ] **Step 4: Mount the router**

Modify `src/jobhunter/web/api.py`. Near the other route imports add:
```python
from jobhunter.web.routes.applications import router as applications_router
```
In `create_app()`, after `app.include_router(spend_router)` (currently line ~216) add:
```python
    app.include_router(applications_router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/integration/test_applications_api.py -v`
Expected: PASS (7 tests). Note: `PostgresApplicationStore.from_env()` is never called in these tests because `get_store` is overridden, so no DB is needed.

- [ ] **Step 6: Commit**

```bash
git add src/jobhunter/web/routes/applications.py src/jobhunter/web/api.py tests/integration/test_applications_api.py
git commit -m "feat(api): /api/applications router (create/update/list/get) with injectable store"
```

---

## Task 5: Postgres store implementation

**Files:**
- Create: `src/jobhunter/application_store_pg.py`
- Modify: `pyproject.toml`
- Test: `tests/integration/test_application_store_pg.py`

- [ ] **Step 1: Add the psycopg dependency**

Modify `pyproject.toml` — in the `web` optional-dependencies list add `"psycopg[binary]>=3.1",`:
```toml
web = [
    "fastapi[all]>=0.110",
    "uvicorn[standard]>=0.27",
    "weasyprint>=62.0",
    "markdown>=3.6",
    "psycopg[binary]>=3.1",
]
```
Run: `pip install -e ".[web,dev]"`
Expected: psycopg installs successfully.

- [ ] **Step 2: Write the failing test**

Create `tests/integration/test_application_store_pg.py`:
```python
"""Real Postgres ApplicationStore tests.

Skipped unless TEST_DATABASE_URL is set, e.g.:
    TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres \\
        python -m pytest tests/integration/test_application_store_pg.py -v

Each test runs in a transaction-isolated, truncated schema.
"""

from __future__ import annotations

import os

import pytest

DB_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="TEST_DATABASE_URL not set")


@pytest.fixture()
def store():
    from jobhunter.application_store_pg import PostgresApplicationStore

    s = PostgresApplicationStore(DB_URL)
    with s._connect() as conn:  # noqa: SLF001 — test-only cleanup
        conn.execute("truncate application_status_history, applications cascade")
        conn.commit()
    return s


def test_create_then_get(store):
    app = store.create(slug="pg1", job_title="Eng", company="Acme", url="https://x/1")
    assert app.status == "applied"
    fetched = store.get(app.id)
    assert fetched.slug == "pg1"
    assert fetched.company == "Acme"


def test_get_by_slug(store):
    app = store.create(slug="pg2", job_title="Eng", company=None, url=None)
    assert store.get_by_slug("pg2").id == app.id
    assert store.get_by_slug("missing") is None


def test_create_writes_initial_history(store):
    app = store.create(slug="pg3", job_title="Eng", company=None, url=None)
    hist = store.history(app.id)
    assert len(hist) == 1 and hist[0].from_status is None and hist[0].to_status == "applied"


def test_update_status_appends_history(store):
    app = store.create(slug="pg4", job_title="Eng", company=None, url=None)
    store.update(app.id, status="interviewing")
    assert [h.to_status for h in store.history(app.id)] == ["applied", "interviewing"]


def test_update_notes_only_keeps_single_history_row(store):
    app = store.create(slug="pg5", job_title="Eng", company=None, url=None)
    store.update(app.id, notes="Prep")
    assert store.get(app.id).notes == "Prep"
    assert len(store.history(app.id)) == 1


def test_list_filters_by_status(store):
    a = store.create(slug="pga", job_title="A", company=None, url=None)
    store.create(slug="pgb", job_title="B", company=None, url=None)
    store.update(a.id, status="offer")
    assert {x.slug for x in store.list(status="offer")} == {"pga"}
    assert len(store.list()) == 2


def test_update_missing_returns_none(store):
    assert store.update("00000000-0000-0000-0000-000000000000", status="offer") is None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres python -m pytest tests/integration/test_application_store_pg.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jobhunter.application_store_pg'`.

- [ ] **Step 4: Write minimal implementation**

Create `src/jobhunter/application_store_pg.py`:
```python
"""Supabase/Postgres-backed ApplicationStore (psycopg v3, synchronous).

Connection string comes from SUPABASE_DB_URL. A connection is opened per
operation (single-user app, low volume) — no pool needed. Status changes and
the matching history row are written in one transaction.
"""

from __future__ import annotations

import os

import psycopg
from psycopg.rows import dict_row

from jobhunter.application_tracker import (
    INITIAL_STATUS,
    Application,
    StatusChange,
    validate_status,
)

_ISO = "YYYY-MM-DD\"T\"HH24:MI:SS\"Z\""  # render timestamptz as ISO-8601 Z in SQL


def _iso_cols(prefix: str = "") -> str:
    p = f"{prefix}." if prefix else ""
    return (
        f"{p}id::text as id, {p}slug, {p}job_title, {p}company, {p}url, "
        f"{p}status, {p}notes, "
        f"to_char({p}applied_at at time zone 'UTC', '{_ISO}') as applied_at, "
        f"to_char({p}created_at at time zone 'UTC', '{_ISO}') as created_at, "
        f"to_char({p}updated_at at time zone 'UTC', '{_ISO}') as updated_at"
    )


def _row_to_app(row: dict) -> Application:
    return Application(
        id=row["id"],
        slug=row["slug"],
        job_title=row["job_title"],
        company=row["company"],
        url=row["url"],
        status=row["status"],
        notes=row["notes"],
        applied_at=row["applied_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class PostgresApplicationStore:
    def __init__(self, db_url: str) -> None:
        self._db_url = db_url

    @classmethod
    def from_env(cls) -> "PostgresApplicationStore":
        db_url = os.environ.get("SUPABASE_DB_URL")
        if not db_url:
            raise RuntimeError("SUPABASE_DB_URL is not set")
        return cls(db_url)

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self._db_url, row_factory=dict_row)

    def create(self, *, slug, job_title, company, url) -> Application:
        with self._connect() as conn:
            row = conn.execute(
                f"""
                insert into applications (slug, job_title, company, url, status)
                values (%s, %s, %s, %s, %s)
                returning {_iso_cols()}
                """,
                (slug, job_title, company, url, INITIAL_STATUS),
            ).fetchone()
            conn.execute(
                "insert into application_status_history (application_id, from_status, to_status) "
                "values (%s, null, %s)",
                (row["id"], INITIAL_STATUS),
            )
            conn.commit()
            return _row_to_app(row)

    def get(self, app_id) -> Application | None:
        with self._connect() as conn:
            row = conn.execute(
                f"select {_iso_cols()} from applications where id = %s", (app_id,)
            ).fetchone()
            return _row_to_app(row) if row else None

    def get_by_slug(self, slug) -> Application | None:
        with self._connect() as conn:
            row = conn.execute(
                f"select {_iso_cols()} from applications where slug = %s", (slug,)
            ).fetchone()
            return _row_to_app(row) if row else None

    def list(self, *, status=None) -> list[Application]:
        with self._connect() as conn:
            if status is not None:
                rows = conn.execute(
                    f"select {_iso_cols()} from applications where status = %s "
                    "order by updated_at desc",
                    (status,),
                ).fetchall()
            else:
                rows = conn.execute(
                    f"select {_iso_cols()} from applications order by updated_at desc"
                ).fetchall()
            return [_row_to_app(r) for r in rows]

    def update(self, app_id, *, status=None, notes=None) -> Application | None:
        with self._connect() as conn:
            current = conn.execute(
                "select status from applications where id = %s", (app_id,)
            ).fetchone()
            if current is None:
                return None
            if status is not None and status != current["status"]:
                validate_status(status)
                conn.execute(
                    "insert into application_status_history (application_id, from_status, to_status) "
                    "values (%s, %s, %s)",
                    (app_id, current["status"], status),
                )
            row = conn.execute(
                f"""
                update applications
                set status = coalesce(%s, status),
                    notes  = coalesce(%s, notes),
                    updated_at = now()
                where id = %s
                returning {_iso_cols()}
                """,
                (status, notes, app_id),
            ).fetchone()
            conn.commit()
            return _row_to_app(row)

    def history(self, app_id) -> list[StatusChange]:
        with self._connect() as conn:
            rows = conn.execute(
                "select from_status, to_status, "
                f"to_char(changed_at at time zone 'UTC', '{_ISO}') as changed_at "
                "from application_status_history where application_id = %s "
                "order by changed_at asc, id asc",
                (app_id,),
            ).fetchall()
            return [
                StatusChange(
                    from_status=r["from_status"],
                    to_status=r["to_status"],
                    changed_at=r["changed_at"],
                )
                for r in rows
            ]


__all__ = ["PostgresApplicationStore"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres python -m pytest tests/integration/test_application_store_pg.py -v`
Expected: PASS (7 tests). Without `TEST_DATABASE_URL` they SKIP.

- [ ] **Step 6: Run the full backend suite (nothing regressed)**

Run: `python -m pytest -q`
Expected: all prior tests still pass; the pg tests skip (no `TEST_DATABASE_URL` in the default invocation).

- [ ] **Step 7: Commit**

```bash
git add src/jobhunter/application_store_pg.py pyproject.toml tests/integration/test_application_store_pg.py
git commit -m "feat(tracker): Postgres-backed ApplicationStore (psycopg v3) + DB integration tests"
```

---

## Task 6: Frontend API client

**Files:**
- Create: `src/jobhunter/web/frontend/src/api/applications.ts`

- [ ] **Step 1: Write the client module**

Create `src/jobhunter/web/frontend/src/api/applications.ts`:
```typescript
export type ApplicationStatus =
  | "applied"
  | "interviewing"
  | "offer"
  | "rejected"
  | "withdrawn";

export const STATUS_ORDER: ApplicationStatus[] = [
  "applied",
  "interviewing",
  "offer",
  "rejected",
  "withdrawn",
];

export const STATUS_LABEL: Record<ApplicationStatus, string> = {
  applied: "Applied",
  interviewing: "Interviewing",
  offer: "Offer",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
};

export type Application = {
  id: string;
  slug: string | null;
  job_title: string;
  company: string | null;
  url: string | null;
  status: ApplicationStatus;
  notes: string | null;
  applied_at: string;
  created_at: string;
  updated_at: string;
};

export async function createApplication(input: {
  slug?: string;
  job_title: string;
  company?: string | null;
  url?: string | null;
}): Promise<Application> {
  const resp = await fetch("/api/applications", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!resp.ok) throw new Error(`createApplication failed: ${resp.status}`);
  return resp.json();
}

export async function updateApplication(
  id: string,
  patch: { status?: ApplicationStatus; notes?: string },
): Promise<Application> {
  const resp = await fetch(`/api/applications/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!resp.ok) throw new Error(`updateApplication failed: ${resp.status}`);
  return resp.json();
}

export async function listApplications(
  status?: ApplicationStatus,
): Promise<Application[]> {
  const qs = status ? `?status=${status}` : "";
  const resp = await fetch(`/api/applications${qs}`);
  if (!resp.ok) throw new Error(`listApplications failed: ${resp.status}`);
  return resp.json();
}

// Find the tracked application for a package slug, or null. Used by the
// package page to decide whether to show "I Applied" or the status control.
export async function findApplicationBySlug(
  slug: string,
): Promise<Application | null> {
  const all = await listApplications();
  return all.find((a) => a.slug === slug) ?? null;
}
```

- [ ] **Step 2: Typecheck**

Run:
```bash
cd src/jobhunter/web/frontend && npm run build
```
Expected: build succeeds (no TS errors). If `build` is not defined, run `npx tsc --noEmit`.

- [ ] **Step 3: Commit**

```bash
git add src/jobhunter/web/frontend/src/api/applications.ts
git commit -m "feat(ui): applications API client + status types"
```

---

## Task 7: "I Applied" control on the package page

**Files:**
- Create: `src/jobhunter/web/frontend/src/components/ApplyControl.tsx`
- Modify: `src/jobhunter/web/frontend/src/PackagePage.tsx`

- [ ] **Step 1: Build the control component**

Create `src/jobhunter/web/frontend/src/components/ApplyControl.tsx`:
```tsx
import { useEffect, useState } from "react";
import {
  Application,
  ApplicationStatus,
  STATUS_LABEL,
  STATUS_ORDER,
  createApplication,
  findApplicationBySlug,
  updateApplication,
} from "../api/applications";

type Props = {
  slug: string;
  jobTitle: string;
  company: string | null;
  url: string | null;
};

export function ApplyControl({ slug, jobTitle, company, url }: Props) {
  const [app, setApp] = useState<Application | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [notes, setNotes] = useState("");

  useEffect(() => {
    findApplicationBySlug(slug)
      .then((found) => {
        setApp(found);
        setNotes(found?.notes ?? "");
      })
      .finally(() => setLoading(false));
  }, [slug]);

  async function onApply() {
    setBusy(true);
    try {
      const created = await createApplication({
        slug,
        job_title: jobTitle,
        company,
        url,
      });
      setApp(created);
      setNotes(created.notes ?? "");
    } finally {
      setBusy(false);
    }
  }

  async function onStatus(status: ApplicationStatus) {
    if (!app) return;
    setBusy(true);
    try {
      setApp(await updateApplication(app.id, { status }));
    } finally {
      setBusy(false);
    }
  }

  async function onSaveNotes() {
    if (!app) return;
    setBusy(true);
    try {
      setApp(await updateApplication(app.id, { notes }));
    } finally {
      setBusy(false);
    }
  }

  if (loading) return null;

  if (!app) {
    return (
      <button
        type="button"
        onClick={onApply}
        disabled={busy}
        className="bg-primary text-on-primary text-body-md font-medium py-stack-sm px-stack-lg rounded-lg hover:bg-primary-container disabled:opacity-50 transition-colors"
      >
        {busy ? "Tracking..." : "I Applied"}
      </button>
    );
  }

  return (
    <div className="flex flex-col gap-stack-sm bg-surface-container-low border border-outline-variant rounded-lg p-stack-md">
      <div className="flex items-center gap-stack-sm">
        <span className="text-label-md text-on-surface-variant">Status</span>
        <select
          value={app.status}
          onChange={(e) => onStatus(e.target.value as ApplicationStatus)}
          disabled={busy}
          className="bg-surface border border-outline-variant rounded-lg px-stack-sm py-stack-xs text-body-md text-on-surface"
        >
          {STATUS_ORDER.map((s) => (
            <option key={s} value={s}>
              {STATUS_LABEL[s]}
            </option>
          ))}
        </select>
      </div>
      <textarea
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        onBlur={onSaveNotes}
        placeholder="What to prepare for..."
        className="w-full h-20 bg-surface border border-outline-variant rounded-lg p-stack-sm text-body-md text-on-surface resize-none"
      />
    </div>
  );
}
```

- [ ] **Step 2: Render it in the package header**

Modify `src/jobhunter/web/frontend/src/PackagePage.tsx`. Add the import at the top with the other imports:
```tsx
import { ApplyControl } from "./components/ApplyControl";
```
In the header section (where the "View drift diagnostics" / "Held" buttons render — near the title block), add the control. Use the slug from the route params and the already-derived title/company/url from `metadata`:
```tsx
<ApplyControl
  slug={slug}
  jobTitle={metadata?.job_title ?? metadata?.parsed_jd?.job_title ?? slug}
  company={metadata?.company_name ?? null}
  url={metadata?.url ?? null}
/>
```
(Use whatever the local variables for slug and metadata are already named in this file — `slug` comes from `useParams`, `metadata` from the `GET /api/package/{slug}` payload.)

- [ ] **Step 3: Typecheck/build**

Run:
```bash
cd src/jobhunter/web/frontend && npm run build
```
Expected: build succeeds.

- [ ] **Step 4: Manual verification**

Run the app (`python -m jobhunter.cli web` or the project's documented run command, with `SUPABASE_DB_URL` set and `supabase start` running). Open a package page, click **I Applied**, confirm the button becomes a status dropdown + notes box, change status, reload — state persists.

- [ ] **Step 5: Commit**

```bash
git add src/jobhunter/web/frontend/src/components/ApplyControl.tsx src/jobhunter/web/frontend/src/PackagePage.tsx
git commit -m "feat(ui): 'I Applied' control with status dropdown + notes on package page"
```

---

## Task 8: Applications kanban overview

**Files:**
- Create: `src/jobhunter/web/frontend/src/ApplicationsPage.tsx`
- Modify: `src/jobhunter/web/frontend/src/App.tsx`
- Modify: `src/jobhunter/web/frontend/src/Sidebar.tsx`

- [ ] **Step 1: Build the kanban page**

Create `src/jobhunter/web/frontend/src/ApplicationsPage.tsx`:
```tsx
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Application,
  ApplicationStatus,
  STATUS_LABEL,
  STATUS_ORDER,
  listApplications,
  updateApplication,
} from "./api/applications";

export function ApplicationsPage() {
  const [apps, setApps] = useState<Application[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listApplications()
      .then(setApps)
      .finally(() => setLoading(false));
  }, []);

  async function move(app: Application, status: ApplicationStatus) {
    const updated = await updateApplication(app.id, { status });
    setApps((prev) => prev.map((a) => (a.id === app.id ? updated : a)));
  }

  if (loading) return <div className="p-gutter text-on-surface-variant">Loading…</div>;

  return (
    <div className="p-gutter flex flex-col gap-stack-lg">
      <header>
        <h1 className="text-headline-lg font-headline-lg text-on-surface">Applications</h1>
        <p className="text-body-md text-on-surface-variant">
          Every job you’ve applied to, by stage.
        </p>
      </header>

      {apps.length === 0 ? (
        <div className="border border-outline-variant rounded-xl p-gutter text-on-surface-variant">
          No tracked applications yet. Generate a package and click “I Applied”.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 xl:grid-cols-5 gap-stack-md">
          {STATUS_ORDER.map((status) => {
            const column = apps.filter((a) => a.status === status);
            return (
              <section key={status} className="flex flex-col gap-stack-sm">
                <h2 className="text-label-md font-medium text-on-surface-variant flex items-center justify-between">
                  <span>{STATUS_LABEL[status]}</span>
                  <span className="text-on-surface-variant/60">{column.length}</span>
                </h2>
                <div className="flex flex-col gap-stack-sm">
                  {column.map((app) => (
                    <article
                      key={app.id}
                      className="bg-surface-container-lowest border border-outline-variant rounded-lg p-stack-md flex flex-col gap-stack-xs"
                    >
                      <div className="text-body-md font-medium text-on-surface">{app.job_title}</div>
                      {app.company && (
                        <div className="text-body-sm text-on-surface-variant">{app.company}</div>
                      )}
                      {app.url && (
                        <a
                          href={app.url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-body-sm text-primary hover:underline truncate"
                        >
                          Job posting ↗
                        </a>
                      )}
                      {app.notes && (
                        <p className="text-body-sm text-on-surface-variant line-clamp-3">{app.notes}</p>
                      )}
                      <div className="flex items-center justify-between pt-stack-xs">
                        {app.slug ? (
                          <Link
                            to={`/packages/${encodeURIComponent(app.slug)}`}
                            className="text-label-md text-primary hover:underline"
                          >
                            Open package
                          </Link>
                        ) : (
                          <span />
                        )}
                        <select
                          value={app.status}
                          onChange={(e) => move(app, e.target.value as ApplicationStatus)}
                          className="bg-surface border border-outline-variant rounded px-stack-xs py-[2px] text-label-md text-on-surface"
                        >
                          {STATUS_ORDER.map((s) => (
                            <option key={s} value={s}>
                              {STATUS_LABEL[s]}
                            </option>
                          ))}
                        </select>
                      </div>
                    </article>
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Add the route**

Modify `src/jobhunter/web/frontend/src/App.tsx`. Add the import:
```tsx
import { ApplicationsPage } from "./ApplicationsPage";
```
In the `<Routes>` block (alongside `/scans`, `/drift`), add:
```tsx
<Route path="/applications" element={<ApplicationsPage />} />
```

- [ ] **Step 3: Add the sidebar entry**

Modify `src/jobhunter/web/frontend/src/Sidebar.tsx`. Follow the existing nav-item pattern (the file defines entries with a path, label, and an icon component). Add an entry:
```tsx
{ to: "/applications", label: "Applications", icon: <IconApplications /> }
```
Add a small inline `IconApplications` SVG next to the other icon components in that file (reuse the existing icon style — `viewBox="0 -960 960 960"`, `className="w-6 h-6 fill-current"`). Example glyph (a checklist/briefcase):
```tsx
function IconApplications() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -960 960 960" aria-hidden="true" className="w-6 h-6 fill-current">
      <path d="M320-280h320v-80H320v80Zm0-160h320v-80H320v80ZM240-80q-33 0-56.5-23.5T160-160v-640q0-33 23.5-56.5T240-880h280l240 240v480q0 33-23.5 56.5T680-80H240Zm240-520v-200H240v640h440v-440H480ZM240-800v200-200 640-640Z" />
    </svg>
  );
}
```
(Match the exact registration shape the file already uses — if it maps over an array of `{to,label,icon}`, add to that array; if it lists `<NavLink>`s inline, add another `<NavLink>`.)

- [ ] **Step 4: Build**

Run:
```bash
cd src/jobhunter/web/frontend && npm run build
```
Expected: build succeeds.

- [ ] **Step 5: Manual verification**

Run the app. Click **Applications** in the sidebar → `/applications` shows five columns. A job you marked applied appears under "Applied". Change its column via the card dropdown; reload — it stays.

- [ ] **Step 6: Commit**

```bash
git add src/jobhunter/web/frontend/src/ApplicationsPage.tsx src/jobhunter/web/frontend/src/App.tsx src/jobhunter/web/frontend/src/Sidebar.tsx
git commit -m "feat(ui): applications kanban overview + sidebar/route wiring"
```

---

## Task 9: Job-posting link on the paste form

**Files:**
- Modify: `src/jobhunter/web/frontend/src/PastePanel.tsx`

The backend already accepts `url` on `POST /api/paste` (`PasteRequest.url`) and threads it into `metadata.json` — only the browser form omits it. This task adds the input and sends it.

- [ ] **Step 1: Add the URL field and send it**

Modify `src/jobhunter/web/frontend/src/PastePanel.tsx`:

1. Add a state hook near the existing `useState` calls:
```tsx
const [url, setUrl] = useState("");
```
2. Add an input above the submit row (below the textarea):
```tsx
<input
  type="url"
  value={url}
  onChange={(e) => setUrl(e.target.value)}
  disabled={busy}
  placeholder="Job posting link (optional)"
  className="w-full bg-surface-container-low border border-outline-variant rounded-lg p-stack-md text-body-md text-on-surface placeholder:text-on-surface-variant focus:border-primary focus:outline-none transition-colors"
/>
```
3. Include `url` in the POST body (only when non-empty):
```tsx
body: JSON.stringify({
  jd_text: jdText,
  source: "browser",
  ...(url.trim() ? { url: url.trim() } : {}),
}),
```

- [ ] **Step 2: Build**

Run:
```bash
cd src/jobhunter/web/frontend && npm run build
```
Expected: build succeeds.

- [ ] **Step 3: Manual verification**

Paste a JD with a link, click **Begin Tailoring**. On the resulting package page, the link is available (`metadata.url`), and clicking **I Applied** carries that URL into the tracker card (visible on `/applications`).

- [ ] **Step 4: Commit**

```bash
git add src/jobhunter/web/frontend/src/PastePanel.tsx
git commit -m "feat(ui): optional job-posting link field on paste form (wires existing url field)"
```

---

## Task 10: Docs + decision record

**Files:**
- Modify: `DECISIONS.md`
- Modify: `README.md`

- [ ] **Step 1: Record the architecture decision**

Append a new section to `DECISIONS.md`:
```markdown
## §7: Supabase for application-tracker state (2026-06-07)

Supersedes the §6 "no new persistence layer / no database" rule **for mutable
application-tracker state only**. §6's revisit trigger (§3: the per-application
`./out/<slug>/` write pattern degrades under mutable state) fired: status,
status history, notes, and the job link are mutable, queryable, relational
data — a poor fit for write-once JSON sidecars.

- **Store:** Supabase Postgres. Tables `applications` + `application_status_history`
  (migration `supabase/migrations/20260607000000_application_tracker.sql`).
- **Access:** server-side from FastAPI via `psycopg` v3, connection string in
  `SUPABASE_DB_URL`. The React app does NOT talk to Supabase directly (no anon
  key / RLS — single-user app).
- **Unchanged:** CV/drift artifacts stay on disk under `./out/<slug>/`. A tracker
  row references a package by nullable `slug`; package-less rows are allowed for
  future "save without tailoring".
- **Consequence:** the tracker requires a network connection + credentials.
  Package *generation* still works offline; only tracking needs the DB.
```
(Replace the stray non-ASCII word "страдает" with "degrades" — do not copy it literally.)

- [ ] **Step 2: Document setup in the README**

Add a "Application tracker (Supabase)" subsection to `README.md` covering:
```markdown
### Application tracker (Supabase)

The application tracker stores status/history in Supabase Postgres.

**Local dev:**
1. Install the Supabase CLI and run `supabase start` (boots local Postgres on `:54322`).
2. `supabase db reset` applies the migration in `supabase/migrations/`.
3. Set `SUPABASE_DB_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres` in `.env`.

**Hosted:** create a Supabase project, run `supabase db push` to apply migrations,
and set `SUPABASE_DB_URL` to the project's connection string (URI).

**Run the DB-backed tests:**
`TEST_DATABASE_URL=$SUPABASE_DB_URL python -m pytest tests/integration/test_application_store_pg.py`
```

- [ ] **Step 3: Commit**

```bash
git add DECISIONS.md README.md
git commit -m "docs: record Supabase tracker decision (§7) + README setup"
```

---

## Task 11: Full-suite verification

- [ ] **Step 1: Backend suite (DB tests skip)**

Run: `python -m pytest -q`
Expected: all pass; `test_application_store_pg.py` skips.

- [ ] **Step 2: Backend suite WITH the database**

Run (local supabase running):
```bash
TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres python -m pytest -q
```
Expected: all pass, including the 7 pg-store tests.

- [ ] **Step 3: Lint + types**

Run: `ruff check src tests && mypy src/jobhunter/application_tracker.py src/jobhunter/application_store_pg.py src/jobhunter/web/routes/applications.py`
Expected: no errors. Fix any surfaced.

- [ ] **Step 4: Frontend build**

Run: `cd src/jobhunter/web/frontend && npm run build`
Expected: succeeds.

- [ ] **Step 5: End-to-end smoke**

With `supabase start` running and `SUPABASE_DB_URL` set, launch the app. Paste a JD with a link → generate → **I Applied** → set status to **Interviewing** → add notes → open `/applications` and confirm the card sits in the Interviewing column with its link and notes. Reload to confirm persistence.

- [ ] **Step 6: Final commit (if any cleanup)**

```bash
git add -A && git commit -m "chore: application tracker verification fixes" || echo "nothing to commit"
```

---

## Self-Review notes

- **Spec coverage:** "I Applied" button (Task 7), status updates (Tasks 4/5/7), notes / "what to prepare for" (Tasks 4/5/7), kanban overview (Task 8), job-posting link (Task 9), Supabase server-side store with nullable slug (Tasks 1/5), status history (Tasks 2/5), DECISIONS update (Task 10). All spec sections map to a task.
- **Status-name consistency:** the five values `applied/interviewing/offer/rejected/withdrawn` are identical across the SQL `check` constraint (Task 1), `STATUSES` (Task 2), `ApplicationStatus`/`STATUS_ORDER` (Task 6), and every UI dropdown.
- **Interface consistency:** `ApplicationStore` Protocol methods (`create/get/get_by_slug/list/update/history`) match the fake (Task 3), the Postgres store (Task 5), and route usage (Task 4).
- **Deferred-in-plan items now decided:** psycopg (sync) over asyncpg; status dropdown over drag-and-drop.
- **Known follow-ups (out of v1 scope):** package-less "save job" entry point (schema already supports it); wiring `interview_reached`/interview-conversion stat to the tracker; drag-and-drop kanban.
```
