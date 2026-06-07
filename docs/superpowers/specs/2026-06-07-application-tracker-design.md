# Application Tracker — Design Spec

**Date:** 2026-06-07
**Status:** Approved design, pending implementation plan
**Author:** Dave Charm Bulaquena (with Claude)

## Problem

Today a job's life in Job Hunter *ends* the moment its package is generated. You
paste a JD, the pipeline produces a tailored CV + cover letter under
`./out/<slug>/`, and that's it — there is no "I applied," no "they replied," no
"interview Tuesday." There is no mutable, user-set application status anywhere in
the system (only drift verdicts, which are write-once pipeline output).

We want to:

1. Mark a generated package as **applied** and **track it** through a lifecycle.
2. **Update its status** over time and keep notes on *what to prepare for*.
3. See an **overview** of every tracked application and where each one stands.
4. Capture the **job-posting link** when pasting a JD, carried into the tracker.

## Key decisions

- **Persistence: Supabase (hosted Postgres).** This formally retires the
  `DECISIONS.md §6` "no new persistence layer / no database, local-only" rule —
  which §3 explicitly listed as a revisit trigger ("the per-application
  `./out/<slug>/` write pattern starts losing data / producing race conditions").
  Mutable, queryable, relational application state is a poor fit for write-once
  JSON sidecars; a real DB is the right tool. The on-disk filesystem layout is
  fine for **write-once documents** (CVs, drift reports) and stays unchanged.
- **Integration shape: FastAPI ↔ Supabase, server-side.** The React app keeps
  calling `/api/*` exactly as it does today. Secrets stay on the server. The
  frontend's data-access model does not fork. The React app does **not** talk to
  Supabase directly (no anon key / RLS in a single-user app).
- **Packages stay on disk.** Supabase holds only the application tracker. A
  tracker row *references* a package by `slug` when one exists.
- **Local dev without hosted creds.** Build against a local Supabase stack
  (`supabase start` → local Postgres + Studio in Docker). Migrations are SQL
  files checked into the repo. When the hosted project is created, only
  `SUPABASE_DB_URL` in `.env` changes — no code change.

## Architecture

```
React (calls /api/* — unchanged)
        │
        ▼
     FastAPI
     ├── Supabase Postgres  ← application tracker state (status, history, url, notes)
     └── ./out/<slug>/      ← CV / cover-letter / drift artifacts (on disk, unchanged)
```

## Data model

Two tables in Supabase Postgres.

### `applications`

| column        | type        | notes                                              |
|---------------|-------------|----------------------------------------------------|
| `id`          | uuid (pk)   | `gen_random_uuid()`                                |
| `slug`        | text, null  | references a `./out/<slug>/` package when present; **nullable** so package-less jobs (future option B) drop in with no schema change |
| `job_title`   | text        |                                                    |
| `company`     | text, null  |                                                    |
| `url`         | text, null  | job-posting link                                   |
| `status`      | text        | one of the lifecycle values below; default `applied` |
| `notes`       | text, null  | free text — *"what to prepare for"*                |
| `applied_at`  | timestamptz | when "I Applied" was first clicked                 |
| `created_at`  | timestamptz | row creation, default `now()`                      |
| `updated_at`  | timestamptz | bumped on every update (trigger or app-level)      |

A **partial unique index** on `slug WHERE slug IS NOT NULL` prevents tracking the
same package twice while still allowing many package-less rows (all `NULL`).

### `application_status_history`

| column           | type        | notes                                  |
|------------------|-------------|----------------------------------------|
| `id`             | uuid (pk)   |                                        |
| `application_id` | uuid (fk)   | → `applications.id`, on delete cascade |
| `from_status`    | text, null  | null for the first (creation) row      |
| `to_status`      | text        |                                        |
| `changed_at`     | timestamptz | default `now()`                        |

Every status change appends one row, giving a per-job timeline.

## Status lifecycle

```
Applied → Interviewing → Offer → Rejected
                              ↘ Withdrawn
```

Allowed values: `applied`, `interviewing`, `offer`, `rejected`, `withdrawn`.
"I Applied" creates the row at `applied`. Transitions are not rigidly enforced in
v1 (the user can set any status) — the history table records whatever path was
taken. (`screening` can be added later as one more enum value with no structural
change.)

## API endpoints

New router `src/jobhunter/web/routes/applications.py`, mounted under `/api`,
following the existing route/handler conventions.

- **`POST /api/applications`** — body `{slug?, job_title, company?, url?}`.
  Creates a tracked application at status `applied`, stamps `applied_at`, writes
  the first `application_status_history` row (`from_status=null`,
  `to_status=applied`). Returns the created row. Called by the "I Applied"
  button. Idempotency: if `slug` is provided and already tracked, return the
  existing row (409 or 200-with-existing — decide in plan).
- **`PATCH /api/applications/{id}`** — body `{status?, notes?}`. Updates status
  and/or notes. On a status change, appends a history row and bumps
  `updated_at`. Returns the updated row.
- **`GET /api/applications`** — list all tracked applications, optional
  `?status=` filter. Feeds the overview board. Returns rows ordered by
  `updated_at desc`.
- **`GET /api/applications/{id}`** — single application with its status history
  (for a detail/timeline view, if needed).

## Frontend

### "I Applied" entry point
- A button on the **package page** (`/packages/<slug>`) and optionally on the
  dashboard **queue card**.
- Click → `POST /api/applications` with the package's `slug`, `job_title`,
  `company`, and `url`.
- Once tracked, the button is replaced by a compact **status control**: a
  dropdown (`Applied / Interviewing / Offer / Rejected / Withdrawn`) + a **notes**
  textarea, both wired to `PATCH /api/applications/{id}`.

### Applications overview (new)
- New sidebar entry **"Applications"** and route **`/applications`**.
- **Kanban board**: one column per status; each tracked job is a card showing
  job title, company, link, last-updated, and a notes preview.
- Moving a card between columns issues a `PATCH` status change. (v1 may use a
  dropdown on the card instead of drag-and-drop if DnD is too heavy — decide in
  plan.)

### Job-posting link capture
- The **paste form** (`PastePanel`) gains an optional **"Job posting link"**
  input.
- The `url` is sent to `/api/paste` (the field already exists in `PasteRequest`
  and `PackageMetadata` — currently only populated by the n8n path), so the
  package's `metadata.json` records it and the package page can display it.
- When "I Applied" is clicked, that same `url` rides into the tracker row.

## Scope for v1

- **Package-anchored only**: you always generate a package first, then click
  "I Applied." Every tracked job has a `slug`.
- **Package-less stashing (option B) is explicitly out of v1** but the schema's
  nullable `slug` + partial unique index mean it drops in later with no schema
  migration — only a new entry point (e.g. a "Save job" form).
- No auth / RLS (single-user app, server-side DB access only).
- No drag-and-drop required for v1 if it adds risk; a status dropdown on each
  card satisfies the "update status" requirement.

## Out of scope

- Auto-scan / n8n workflows (not working yet; untouched here).
- Migrating existing `./out/` packages into the tracker (tracker starts empty;
  you click "I Applied" going forward).
- Multi-user, auth, sharing.
- Reminders / calendar / interview scheduling.

## Risks & notes

- **Online dependency.** Tracking data now requires a network connection and
  Supabase credentials. Given the existing Oracle Cloud deployment, this makes
  tracker state a single source of truth across local + deployed, rather than
  trapped in one machine's `./out/`. The app's *package generation* still works
  offline; only the tracker needs the DB.
- **`DECISIONS.md` update required.** Add a new section documenting the Supabase
  adoption and superseding the §6 "no database" rule for tracker state.
- **Two sources of truth** (disk packages + DB tracker) linked by `slug` — keep
  the link loose: a deleted package should not break a tracker row, and a tracker
  row should not assume the package still exists.
- **Connection management.** Decide in the plan: direct Postgres driver
  (`asyncpg`/SQLAlchemy) vs `supabase-py`. Lean `asyncpg` + a small data-access
  module for a clean FastAPI fit, server-side only.
