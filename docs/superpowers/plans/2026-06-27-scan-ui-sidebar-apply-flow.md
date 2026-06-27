# Plan: Sequential per-site scan UI + Sidebar fix + Generate→Apply flow

Three work-streams. Each ships independently. Stream A's backend is **partially
coded already** (uncommitted on `feat/job-scan`) — noted below; building is PAUSED
pending approval.

---

## Stream A — Per-site sequential scan with a workflow-style UI
**Goal:** scan sites **one at a time**, each site **posts its results the moment it
finishes**, so a blocked/slow site never delays or sacrifices the working ones.
Show it in Job Scan as a **workflow/pipeline** (4 site steps with live status) +
dynamic elapsed time.

**Resilience (the key requirement):**
- Each site is its own n8n node with **Continue-On-Fail** → a failing site does NOT
  stop the chain; the next site still runs.
- `run-scan.sh` (per-site) **exits 0 with `{status: blocked/error}`** instead of
  crashing → a block is a normal result, not a node failure.
- **Incremental posting** → each finished site is already saved before any later
  site runs, so nothing earlier can be lost.

**Backend (✅ already coded, uncommitted):**
- ✅ migration `scan_status.per_site jsonb` + `current_scan_id`.
- ✅ `ScanStatus.per_site`; store `append_site_results` (creates the scan on first
  site, appends candidates + dedup, updates `per_site[site]`).
- ✅ pg `mark_scan_running` resets per_site/current_scan_id.

**Backend (⬜ still to do):**
- pg `mark_scan_completed` finalizes the scan row; `get_scan_status` returns per_site.
- Fake store: per_site + `append_site_results` + reset (for tests).
- Endpoints: `POST /api/scan/site-results {site, site_status, candidates}`,
  `POST /api/scan/complete`, `GET /api/scan/status` (+per_site). Tests.

**Engine — needs n8n image rebuild (stops any running scan):**
- `run-scan.sh`: single-site mode (`--site`), exit-0-on-failure with blocked JSON,
  finite wait ceiling, stream logs to stderr, proxy rotates per site.
- Workflow: 4 sequential per-site nodes, each Continue-On-Fail → Run Claude (--site)
  → Parse → `POST /api/scan/site-results`; final node → `POST /api/scan/complete`.

**Frontend — workflow-style UI:**
- JobScanPage renders the 4 sites as a **sequential pipeline/stepper** from
  `scan_status.per_site`: `queued → scanning… → ✓ N found / blocked / error`,
  polled every 5s.
- **Dynamic elapsed time:** `<60s → "Ns"`, `≥60s → "Mm Ss"`.

---

## Stream B — Sidebar fix  (NEED DETAIL FROM YOU)
A mobile hamburger + slide-in drawer shipped earlier (PR #10). You say it still
needs fixing. **What's wrong now?** (doesn't open on mobile / overlaps content /
desktop layout off / links don't close it / other). I'll investigate + fix once I
know the symptom.

---

## Stream C — Generate → Application flow (the "I Applied" gap)
**Problem (confirmed by exploration):** applications are created ONLY by manually
clicking "I Applied" on `/packages/<slug>`. Approving an override is filesystem-only
(never touches the tracker). If you approve and leave the page, the job is **never
tracked** — exactly what bit you.

**Proposed fix:** auto-track every tailored job.
- New status **`to_apply`** (a kanban column *before* `applied`).
- On generate/approve (`POST /api/paste`, `/api/scan/candidates/{id}/generate`,
  `/api/override/{slug}`) → **auto-create an application** (status `to_apply`),
  idempotent by slug.
- Package page: button becomes **"Mark as Applied"** (`to_apply → applied`).
- ApplicationsPage: add the `to_apply` column.
- migration: add `to_apply` to the status CHECK; domain STATUSES; tests.

**Result:** nothing is ever lost — tailored jobs show up in the tracker
immediately; "Applied" is one click that can't be missed.

---

## Stream D — Associate + re-download generated CV/cover from an application  (PLAN, per user)
**Problem:** after tailoring + applying, you can't see that a job already has
generated artifacts, and you can't re-download the CV/cover later ("walang balikan").

**Key fact:** the link basically already exists — `applications.slug` → the package
in `./out/<slug>/` (or `./out/_overridden/<slug>/`), and `/api/package/<slug>` +
`/api/package/<slug>/download/<file>` already serve them. The EC2 `jobhunter-out`
volume persists across deploys, so the files survive. **The gap is purely that the
ApplicationsPage never surfaces them.**

**Plan (mostly frontend):**
- ApplicationsPage cards: when `app.slug` is set, show **"View package"**
  (→ `/packages/<slug>`) + **"Download CV"** / **"Download Cover"** links
  (→ the existing download endpoints). So every tracked job links back to its artifacts.
- Ensure `job_title`/`company` are stored on the application (already passed by
  ApplyControl) so the card is readable.
- **Durability decision (need your call):**
  - **(a) Rely on the persisted `./out` volume** (simplest — files already persist;
    just surface download links). ✅ recommended.
  - **(b) Snapshot the CV + cover *text/PDF* into the application record / a durable
    store** at apply-time — survives even if `./out` is wiped, but stores large blobs.
- (Optional) On a fresh generation for a slug that already has an application, keep
  the link so re-generations are still reachable.

## Bug — "fix issues" shows even after approving (Stream C-adjacent)
After approving an override, the package page still shows the held / "fix issues"
state. Likely the PackagePage doesn't **refetch** the package after the override
POST succeeds, so it keeps the stale `held=true` metadata. Fix: re-fetch (or update
state to held=false) after a successful override → the held UI disappears and the
"I Applied / Mark as Applied" action shows. Folds into Stream C.

## Open questions
1. **Sidebar:** what exactly is broken right now?
2. **Apply flow:** go with auto-create + new `to_apply` status (recommended), or
   keep manual but just make the "I Applied" button unmissable?
3. **Order:** A (scan UI) → C (apply flow) → B (sidebar)? Or reprioritize?

## Status: PLAN — awaiting your answers + "build". Nothing deployed; running scan
(exec 31, old loop) will be replaced when we rebuild the engine.
