# Architectural Decisions — jobhunter

This file records the foundational, hard-to-reverse decisions that every later story inherits. New entries should be additive — do not silently rewrite history. If a decision is overturned, leave the original entry and add a follow-up entry below it referencing the trigger.

---

## 1. Runtime / Language

**Decision:** Python (>= 3.11).

**Rationale.** Per PRD line 357 ("Python or TypeScript are the leading candidates — both have mature LLM SDKs, good markdown tooling, and easy n8n integration. Final choice depends on which the author can move fastest in for a solo nights-and-weekends build"), the deciding factor is solo-build velocity. Python wins here for three concrete reasons relevant to this project: (a) the JSON Resume validation ecosystem (`jsonschema`) is first-class and zero-friction, with no build step between writing a script and running it; (b) downstream stories (Epics 3–5: atomic claim extraction, semantic equivalence, keyword density) lean on text-processing and NLP libraries where Python has the deeper free/local toolbox; (c) the v1 pipeline is sequential and runs locally on the author's machine — Node's async strengths buy nothing here, and Python's stdlib + `pathlib` makes the filesystem-only persistence model (no DB in v1) ergonomic.

**Rejected alternative.** TypeScript (Node >= 20) with `ajv` for schema validation. Rejected because it would add a build step (`tsc`) and a `dist/` directory to every smoke test for no payoff at this stage; the LLM SDK and n8n integration story is equally good in both, so velocity tiebreakers win.

**Revisit if:**
- The chosen LLM SDK becomes unreliable or significantly behind on features in Python compared to its TypeScript counterpart.
- n8n integration ergonomics (Epic 7) break down because the internal `/post-ingest` endpoint surface (Story 2.11) is materially easier to author in Node.
- The fabrication-drift work (Epic 3) needs a JS-only NLP library that has no Python equivalent.

---

## 2. Canonical-CV Schema

**Decision:** JSON Resume v1.0.0 as the working assumption.
Schema URL of record: `https://github.com/jsonresume/resume-schema/blob/v1.0.0/schema.json`.
The schema is **vendored** into the repo at `schemas/jsonresume-v1.0.0.json` so that validation runs offline (per PRD NFR13 — paste mode must always work, including without a network).

**Sample location.** The canonical CV lives at the repo root as `canonical-cv.json`. The path is exposed to all code through the single constant `CANONICAL_CV_PATH` defined in `src/jobhunter/config.py`. No code anywhere else in the repo may hard-code the path.

**Reader contract (FR4).** Exactly one function — `jobhunter.canonical_cv.read_canonical_cv()` — loads the canonical CV. It re-reads from disk on every invocation (no in-process or on-disk caching). All downstream stories (1.3, 1.5, 2.1, 2.3, 3.1, 3.2, 4.1, 5.1) consume the CV through this function.

**Fall-back criterion (verbatim).** Fall back to minimal custom YAML if JSON Resume cannot cleanly represent the `tags` and `highImpact` per-entry extensions required by Epic 2 Story 2.1 (FR2, FR3).

**Note on extensions.** Story 1.1's sample uses pure JSON Resume v1.0.0 with **no** extensions. The `tags` and `highImpact` per-entry fields land in Story 2.1; that story is the first chance the fall-back criterion above could trigger.

**Binary-format rejection (Story 1.3, FR5).** `read_canonical_cv()` rejects any path ending in `.pdf`, `.docx`, or `.doc` (case-insensitive) by raising `UnsupportedCanonicalCVFormat` **before** any read attempt. The decision is path-extension-only — no MIME detection, no `python-docx`/`pdfminer`/`pypdf` dependency — because parsing the binary formats is the opposite of what FR5 asks for. The canonical CV must stay a diffable text format (JSON today; markdown or YAML once the fall-back criterion above fires).

---

## 3. Revisit Triggers (cross-cutting)

A future story should reopen the decisions above (and prepend a new dated entry, not edit the originals) if **any** of the following hold:

- **Runtime/language:** a chosen SDK (LLM, n8n bridge) is materially worse or absent in the current runtime.
- **Schema:** Story 2.1 cannot cleanly extend JSON Resume with `tags` + `highImpact` at the entry level without resorting to schema escape hatches (e.g. `additionalProperties: true` everywhere, or stuffing JSON-in-strings).
- **Persistence model:** filesystem-only persistence (no DB) starts losing data or producing race conditions under the per-application `./out/<slug>/` write pattern from Story 1.5.

---

## 4. LLM Provider

**Decision:** Anthropic Claude via the official `anthropic` Python SDK, model `claude-haiku-4-5`. The provider boundary is encapsulated in `src/jobhunter/llm_client.py` — `tailor()` is the only public entry, and the pricing constants (`INPUT_PRICE_PER_MTOK = $1.00`, `OUTPUT_PRICE_PER_MTOK = $5.00`) are pinned at the module level. Per-call cost is computed from the SDK's reported `Usage(input_tokens, output_tokens)` and quantized to six decimal places using `Decimal` (never float). Pricing captured on 2026-05-23; revisit if Anthropic publishes new public list prices.

**Rationale.** Tied to PRD constraints:
- **NFR-Cost (< $0.25 per application).** Haiku 4.5 is well below the per-application target for a single tailoring call: a typical run (1–2KB canonical CV + 2–4KB JD + 3–5KB tailored output) lands well under a cent. The hard monthly cap (`MONTHLY_SPEND_CAP_USD`) plus the pre-call cap check in `spend_tracker.check_cap_or_raise()` (Story 1.5 AC3) backstops the math.
- **NFR-Performance (< 60s per-call timeout).** Haiku's typical first-byte and end-to-end latency on a ~5–10KB total payload is well below the 60s timeout. The timeout is wired to the SDK's `timeout=` constructor kwarg and overridable via the `LLM_CALL_TIMEOUT_SECONDS` env var.
- **Reliability path for AC6 (structured output).** Anthropic's tool-use API with `tool_choice={"type": "tool", "name": "emit_tailored_artifacts"}` forces the model to emit a strict JSON schema (two required string fields). This is the load-bearing reliability mechanism — free-form JSON in prose is a known parsing-failure mode.
- **NFR-Integration ("provider switch must be a config change, not a code rewrite").** Isolating the SDK to a single ~120-LoC module (`llm_client.py`) with one public function means an OpenAI swap is a single-file rewrite + a `pyproject.toml` pin change, not a multi-file refactor.

**Rejected alternative.** OpenAI `gpt-4o-mini` via the `openai` SDK. Comparable cost and quality. Rejected because there is no strong technical signal to prefer one over the other for this workload, and the author's pre-existing toolchain leans Anthropic. **One provider at a time** (PRD NFR-Integration): the project must never carry pins for two LLM SDKs simultaneously.

**Revisit if:**
- Anthropic raises Haiku pricing >2× during walking-skeleton work or removes the model.
- The chosen model fails AC6 (malformed/missing tool-use response) at greater than ~5% of calls during smoke testing.
- Epic 2's prompt-template versioning (Story 2.9) surfaces a feature gap (e.g. another provider gains a notably stronger structured-output mode or significantly cheaper tier for our payload shape).
- The Anthropic SDK becomes incompatible with the pinned Python 3.11+ runtime.

---

## 5. Local Web UI (added to v1 scope on 2026-05-23)

**Decision (overturns prior v1 non-scope position).** A local-only web UI is added to v1 scope. The original Product Brief and PRD listed "Web review UI with auth/state" as v1 non-scope; that position is overturned by this entry. The web UI is **localhost-only**, **single-user**, **no auth**, and ships as a `jobhunter web` subcommand that boots a FastAPI backend on `127.0.0.1` plus a static frontend bundle.

**Design source of truth.** Stitch project `14722049854544467629` ("Drift-Checked Job Hunter"). Frozen export at `design_guidelines/stitch-export/`:
- `design.md` — design tokens (Inter typography, deep navy + vibrant blue palette, 8px base grid, soft 0.25rem corners) + component guidance.
- `html/*.html` — five HTML mockups, one per screen, source of truth for layout + Tailwind classes.
- `screenshots/*.png` — pixel reference per screen.
- `INDEX.md` — screen-to-epic mapping + dev-story usage rules.

Re-export with the Stitch MCP and overwrite this directory if the Stitch source changes. Do **not** hand-edit files inside `stitch-export/` — they are a build artifact, not a working file.

**Rationale.** Three concrete reasons the original position is no longer correct:
- **Drift report UX.** The fabrication, content-loss, and keyword-stuffing drift checks (Epics 3, 4, 5) produce structured JSON (`package.drift.json`) that is genuinely hard to read as text. A drift diagnostics screen with claim→source traceability arrows, per-entry highlighting, and density heatmaps is a meaningfully better review surface than the `.md` + `.json` files alone.
- **Held-queue ergonomics.** `jobhunter status` + `jobhunter override <slug>` (Stories 6.3, 6.4) work, but a queue dashboard with batch view + drift summary + one-click approve compresses the human-review step from "open three files in editor" to "skim and click."
- **Shareable-with-peers path.** The brief's vision extension #3 ("Standalone drift-check CLI" + "Shareable peer packaging") is materially easier to deliver if the UI exists — peers don't need to learn the CLI semantics.

**Hard constraints (do not violate in any Epic 8 story).**
- **Bind to `127.0.0.1` only.** Never `0.0.0.0`. No exposing the server to the LAN, no port-forwarding default. A localhost-only `app.py`/FastAPI launcher; if any future story wants LAN/internet exposure, this entry must be reopened first.
- **No auth in v1.** Single-user, single-machine. No login screen, no session cookies, no JWT. If the deployment story changes (Epic 9+), revisit.
- **No outbound submission.** "Approve" buttons call the same `override` logic the CLI uses. Never POST to a job board. The human-presses-submit rule (PRD non-negotiable) survives into the UI unchanged.
- **No new persistence layer.** Backend reads `_bmad-output/implementation-artifacts/sprint-status.yaml` and the per-package sidecar JSON files (Story 2.10) directly. No database, no Redis, no separate state store.
- **One LLM SDK.** UI does not introduce any new LLM call paths. Tailoring still goes through `src/jobhunter/llm_client.py` (PRD NFR-Integration).
- **Design tokens come from `design.md`.** Component code references CSS variables generated from the design system; no ad-hoc hex codes or pixel values in component source.

**Architecture (high-level).**
- **Backend:** FastAPI in `src/jobhunter/web/api.py`. Wraps existing CLI logic — no business logic in route handlers. Exposes read endpoints (`/queue`, `/package/<slug>`, `/canonical-cv`) + action endpoints (`/override/<slug>`).
- **Frontend:** Static bundle in `src/jobhunter/web/frontend/`. React + Vite + Tailwind. Tailwind config generated from `design_guidelines/stitch-export/design.md` so design tokens stay in lockstep with Stitch.
- **Launcher:** `jobhunter web` subcommand (added to existing argparse in `cli.py`). Binds to `127.0.0.1:8765` by default; port overridable via `JOBHUNTER_WEB_PORT` env. Logs the URL to stderr.
- **Build step:** `pyproject.toml` `[project.optional-dependencies] web = [...]`; frontend build is `npm run build` producing static assets the FastAPI app serves.

**Rejected alternative.** Hosted multi-tenant SaaS web app (the original brief's v2 "shareable" framing). Rejected because the brief's "personal-first, NOT a VC pitch" stance still holds — adding auth, multi-tenancy, payments, and PII handling at v1 is the scope-explosion path. Local-only keeps the property that the user's canonical CV and tailored outputs never leave their machine (except for the LLM call, which is opt-in via API key).

**Revisit if:**
- The `127.0.0.1` binding becomes a blocker for a documented user workflow (e.g. iPad reviewing on the same LAN). If so: add a `--bind` flag, require explicit user opt-in, do **not** change the default.
- A peer-sharing story (v2+) requires multi-user state. That work needs a fresh ADR entry — do not silently bolt auth onto this design.
- Tailwind/Stitch design-token sync becomes a maintenance burden severe enough that a different frontend stack would pay for itself.
- The FastAPI + static bundle combo's startup latency exceeds 3s on the author's machine.

---

## 6. Web-only architecture (supersedes CLI-first stance from §1 and §5, on 2026-05-23)

**Decision (overturns CLI-first architecture).** The v1 product surface is a **web app only**. There is no CLI subcommand surface (`jobhunter paste`, `jobhunter status`, `jobhunter override`, `jobhunter stats`) — these are replaced by HTTP endpoints (`POST /api/paste`, `GET /api/queue`, `POST /api/override/<slug>`, `GET /api/stats`) that the React frontend invokes. The `jobhunter` command takes **no subcommands**; it boots a FastAPI server on `127.0.0.1:8765` and (optionally) opens the browser. This entry supersedes the CLI-centric framing in §1 (which assumed a CLI tool was the primary surface) and reshapes §5 (the Local Web UI now IS the app, not a layer over the CLI).

**Triggering context.** §5 added a "Local Web UI" as a parallel surface on top of the CLI on 2026-05-23. Within the same day, mid-orchestration on Epic 2, the author noticed that every CLI subcommand stub being planned (`jobhunter status`, `jobhunter override`, `jobhunter stats`) was already going to be re-implemented as an HTTP endpoint inside Epic 8 — i.e. the same logic was being scheduled twice across the backlog. Cheaper to pivot before any of Epic 2 lands than to build CLI + UI in parallel and reconcile later.

**Architecture.**
- **Backend:** FastAPI in `src/jobhunter/web/api.py`. Routes wrap the existing core modules (`canonical_cv.py`, `llm_client.py`, `spend_tracker.py` — all built in Epic 1 and untouched by this pivot). No business logic in route handlers.
- **Frontend:** Static bundle in `src/jobhunter/web/frontend/`. React + Vite + Tailwind. Tailwind config consumes design tokens from `design_guidelines/stitch-export/design.md` so design tokens stay in lockstep with Stitch.
- **Launcher:** Bare `jobhunter` command (no subcommands). Boots uvicorn on `127.0.0.1:8765`, logs URL to stderr, opens default browser via `webbrowser.open` (best-effort, non-blocking). Port overridable via `JOBHUNTER_WEB_PORT` env.
- **No CLI surface beyond the launcher.** No argparse subcommands. The `jobhunter paste` / `status` / `override` / `stats` symbols listed in earlier PRD drafts are deleted, not aliased — there is one entry point and it is a web server.

**What survives from Epic 1 unchanged.** The Epic 1 core modules — canonical-CV reader (§2 reader contract still load-bearing), LLM client + spend tracker (§4), `./out/<slug>/` package writer, JSON Resume schema validation — are pure Python modules with no CLI assumptions baked in. They survive the pivot as-is. The 189 passing tests for those modules survive. Only the argparse entrypoint tests and the `jobhunter paste` stdin/file glue from Stories 1.2/1.4/1.5 need to be replaced.

**Story 1.6 (new) carries the pivot.** Epic 1 reopens with a single follow-up story that:
- Replaces the argparse CLI scaffold (Story 1.2) with a FastAPI app + uvicorn launcher.
- Replaces `jobhunter paste` stdin/file glue (Story 1.4) with `POST /api/paste`.
- Wraps the existing tailoring + package-write logic (Story 1.5) in the new route handler — same code, new entrypoint.
- Scaffolds a minimal React + Vite + Tailwind frontend with design tokens wired from `design.md` and a sidebar-shell landing page matching the Stitch dashboard layout.

**Epic 8 dissolves; UI scatters into the feature epics.** Carrying "the web UI" as a separate epic to the end of v1 was correct under the old hybrid architecture but is wrong under web-only — every feature epic now ships an end-to-end vertical slice (backend route + frontend surface) as one shipping unit. Concrete redistribution:
- Settings & Canonical CV editor (Stitch screen 02) → Epic 2 (uses tagging schema + high-impact flag, which Epic 2 introduces).
- JD Pipeline & Tailoring (Stitch screen 04) → Epic 2 (uses parsed JD + tailored artifacts).
- Drift Check Diagnostics (Stitch screen 05) → built incrementally across Epics 3 → 4 → 5, one drift-check section per epic.
- Dashboard / held queue (Stitch screen 01) → Epic 6 (uses held-queue state + override action).
- Job Alerts & Automated Scans (Stitch screen 03) → Epic 7 (uses n8n flow state).

**Hard constraints (carried forward from §5, unchanged).**
- **Bind to `127.0.0.1` only.** Never `0.0.0.0`. A startup check rejects non-loopback binding. No LAN exposure, no port-forwarding default.
- **No auth in v1.** Single-user, single-machine. No login screen, no session cookies, no JWT.
- **No outbound submission.** The "Approve" button calls the same override code path that the queue-release logic uses internally. Never POSTs to a job board. PRD non-negotiable FR44 (no auto-submit) is now enforced *structurally* — there is no second code path that could regress it.
- **No new persistence layer.** Backend reads `_bmad-output/implementation-artifacts/sprint-status.yaml` and the per-package sidecar JSON files (Story 2.10) directly. No database, no Redis, no separate state store.
- **One LLM SDK.** UI does not introduce any new LLM call paths. Tailoring still goes through `src/jobhunter/llm_client.py` (§4, PRD NFR-Integration).
- **Design tokens come from `design.md`.** Component code references CSS variables generated from the design system; no ad-hoc hex codes or pixel values in component source.

**Rejected alternatives.**
- **(B) Web-first + thin CLI shim** — FastAPI primary, `jobhunter paste <file>` etc. as thin curl-equivalents. Rejected because a thin shim still requires CLI tests, argument parsing, and a parallel surface to document. The author can use `curl` or `httpie` directly if terminal entry is ever needed; carrying a CLI client to maintain just for one user is overhead.
- **(C) Keep CLI-first; UI as Epic 8** — the original §5 framing. Rejected because the duplicate-surface tax compounds across Epics 2-7; pivoting now is cheap (one Epic 1 follow-up story) while pivoting later means rewriting 12+ CLI-surface stories.

**Revisit if:**
- The `127.0.0.1` binding becomes a documented blocker (e.g. iPad reviewing on the same LAN). Add a `--bind` flag with explicit user opt-in; do not change the default.
- A scripting need for the author surfaces that `curl` + `httpie` cannot meet ergonomically. At that point, reopen this entry and consider a thin CLI shim (option B above).
- The FastAPI + static bundle combo's startup latency exceeds 3s on the author's machine.
- A peer-sharing or hosted variant becomes a v2+ direction. That work needs a fresh ADR — do not silently bolt auth onto this single-user design.

---

*Last updated: 2026-05-23 (§6 added — web-only architecture; supersedes CLI-first stance from §1 and §5).*

---

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
