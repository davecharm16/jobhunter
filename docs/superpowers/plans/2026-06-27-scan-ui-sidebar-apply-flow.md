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

**Scrape bounds (prompt logic — keeps runs short & predictable):**
- For each keyword, only paginate **search-results pages 1, 2, 3** (no deep /
  infinite scrolling). Collect the listings from those pages.
- From that bounded set, **rank by fit to the candidate background** and keep the
  top N (picks_per_site). This caps the work per keyword → faster per-site runs,
  far less chance of Claude deferring (which is what hung the all-sites run).
- Goes into `prompts/job_scan.v1.md` (baked → ships with the n8n rebuild).

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

## Stream E — Bug: PDF download loses hyperlinks  (NEW, user-reported)
**Symptom:** in the downloaded CV PDF, the contact line **GitHub / LinkedIn /
Portfolio** renders as plain text — the URLs are NOT clickable hyperlinks.
**Note:** the CV markdown DOES contain proper `[Portfolio](https://…)`,
`[GitHub](https://…)`, `[LinkedIn](https://…)` links — so the bug is in the
**markdown → HTML → PDF** path (WeasyPrint): either the markdown→HTML step isn't
converting those `[text](url)` links to `<a href>` (e.g. the header line is
rendered as plain text), or WeasyPrint isn't emitting the link annotations.
**Plan to fix:**
- Find the PDF generation (search `weasyprint` / the pdf module + the cv template /
  markdown→HTML renderer). Confirm whether the rendered HTML has `<a href>` for
  those links.
- Ensure the markdown link syntax is converted to anchors AND that WeasyPrint
  keeps them clickable (it supports `<a href>` link annotations natively).
- Add a test: render a CV with the contact links → assert the produced HTML (or
  PDF text layer) contains `<a href="https://github.com/...">` etc.
- Applies to the cover letter PDF too if it has links.

## ===== 2026-06-28 FINDINGS + FIX PLAN (the per-site scan + extract-jd) =====

### What we proved
- **OLD single-node workflow (`lFU4bsgLyUO4Evxj`) executes fine** — exec 37 ran in
  5s on the live worker. So n8n + the worker are healthy, and the new `run-scan.sh`
  (`--site` version) IS deployed (old workflow called it without `--site` → it hit
  the "no site → error" path and returned instantly).
- **NEW 19-node per-site workflow (`v3z6nCpZS0k9iuK2`) does NOT execute** — every
  trigger (32/33/35/36/39) sticks at the webhook with `runData={}`, even on a freed
  worker, even after restart + re-publish. n8n accepts the trigger, creates the
  execution, but never runs the body. Connections are correct. **n8n simply won't
  run this particular big workflow.** Not zombies, not jam, not the prompt.

### Decision: wire the WORKING idea — per-site loop INSIDE run-scan.sh (single node)
Stop fighting the 19-node workflow. The old single-node workflow runs reliably, so
move the per-site logic into `run-scan.sh`:
- **`run-scan.sh` (no `--site`):** loop the enabled sites; for EACH site →
  scan (bounded to pages 1–3, finite bg-wait, stealth, proxy rotate) → extract
  `{site_status, candidates}` → **`curl POST /api/scan/site-results`** (incremental:
  each site saved as it finishes; a blocked site can't sink the others) → next.
  Finally **`curl POST /api/scan/complete`**. (This keeps the new per-site UI working
  because `per_site` populates.)
- **Workflow:** use the OLD single-node workflow; simplify it to
  `triggers → Get Settings → Enabled? → Known URLs → Profile → Build Inputs →
  Run Claude Scan`. **Remove the Parse + Post nodes** (run-scan.sh self-posts).
  Re-activate it (it's the one n8n actually runs).
- **Env on n8n service:** `SCAN_APP_BASE` (app URL) + `SCAN_APP_AUTH`
  (`Basic <base64 dave:pw>` for Caddy) so run-scan.sh can curl the app. (1 env var;
  not committed.)
- **Prompt (user's point):** each loop iteration sets `sites_enabled=[that one site]`,
  so the existing "for EACH enabled site" naturally does exactly one site. Tighten
  the wording so it's unambiguous for a single-site run.
- Needs an n8n image rebuild (run-scan.sh) + the old-workflow edit.

### Bug — extract-jd `spawn E2BIG` (screenshot → JD)
Root cause: the image base64 is embedded into the n8n shell command; a real
screenshot's base64 exceeds Linux's **128KB single-argument limit** (`MAX_ARG_STRLEN`)
→ `spawn E2BIG`. (My 19KB test image passed; a real screenshot doesn't.)
**Fix (frontend, robust + quick, app-only deploy):** in `fileToDownscaledBase64`,
step quality/size down in a loop until the base64 is **< ~90KB** (safely under the
limit) — guarantees any screenshot fits.
**Optional hardening:** an n8n write-file node so the image never goes through the
command arg at all.

## Stream F — Fix the package/recovery flow (drift-fail dead-ends + findability)  [PLAN]
User pain: after many generations, drift-failed packages show "Fix Issues" but it
doesn't fix; can't find past generations; can't re-download; duplicate cards.

**Findings (from RCA):**
- "Fix Issues" → `/packages/<slug>/drift` (read-only diagnostics). The real fixes
  (Regenerate / Approve override) are on `/packages/<slug>` — one extra click away.
- Dashboard pipeline shows only the 10 most recent (queue.py `_RECENT_LIMIT=10`);
  older held packages disappear from view.
- `/drift` (Drift Checks page) ALREADY lists ALL generations (held/passed/overridden)
  with download — but it's not discoverable from the dashboard.
- Regenerate creates a NEW slug and leaves the old held package → duplicate cards.
- `job_title` "Salary Php 25 000…" = JD parser misread the salary line as the title.

**Plan (ordered by value):**
1. **"Fix Issues" → `/packages/<slug>`** (the page with Regenerate/Override), not the
   drift page. One click to actually fix. (Tiny frontend change in PipelineCard.)
2. **Surface history**: rename/expose "Drift Checks" as **"Generations / History"** and
   add a dashboard link "View all N generations" → so past packages are always findable
   + re-downloadable (ties into Stream D snapshot/re-download).
3. **De-dup on regenerate**: when a regenerate succeeds, mark/move the OLD held package
   as superseded (e.g. `metadata.superseded_by = new_slug`, hide it from the queue) so
   you don't get duplicate cards.
4. **Job-title quality**: clean the parsed `job_title` — reject currency/salary-looking
   strings; for scan-generated packages, prefer the scan candidate's title (which is
   usually correct). Optionally allow editing the title.
5. (Optional) After Approve override, a clearer "done — here's your package + download"
   state instead of a filesystem-path note.

This overlaps Stream C (apply unmissable) + Stream D (snapshot + re-download) — together
they make "generate → find → fix/regenerate → apply → re-download" a coherent loop.

## Open questions
1. **Sidebar:** what exactly is broken right now?
2. **Apply flow:** go with auto-create + new `to_apply` status (recommended), or
   keep manual but just make the "I Applied" button unmissable?
3. **Order:** A (scan UI) → C (apply flow) → B (sidebar)? Or reprioritize?

## Status: PLAN — awaiting your answers + "build". Nothing deployed; running scan
(exec 31, old loop) will be replaced when we rebuild the engine.
