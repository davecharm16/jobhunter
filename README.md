# jobhunter

Solo-developer pipeline for tailoring a CV + cover letter to a pasted job description, with three downstream drift checks (fabrication, content-loss, keyword-stuffing) that hold any package showing drift instead of publishing it. Runs locally, filesystem-only, no database in v1.

The canonical source of truth for the applicant's profile is a single file in version control (`canonical-cv.json`), validated against the [JSON Resume](https://jsonresume.org) v1.0.0 schema. See [`DECISIONS.md`](./DECISIONS.md) for the foundational runtime + schema decisions.

## Getting started

Requires Python ≥ 3.11.

```bash
# 1. Create and activate a virtualenv.
python3 -m venv .venv
source .venv/bin/activate

# 2. Install in editable mode (pulls in jsonschema and dotenv support).
pip install -e .

# 3. Copy local runtime configuration placeholders and fill in private values.
cp .env.example .env

# 4. Validate the canonical CV against the vendored JSON Resume v1.0.0 schema.
#    Exits 0 on success, non-zero with a human-readable error on failure.
python scripts/validate_canonical_cv.py

# 5. (Optional) Install dev deps and run the test suite.
pip install -e ".[dev]"
pytest
```

The validator reads from the vendored schema at `schemas/jsonresume-v1.0.0.json` and never touches the network — paste mode must keep working offline (PRD NFR13).

## Configuration

Copy `.env.example` to `.env`, then replace the placeholder `LLM_API_KEY` and `MONTHLY_SPEND_CAP_USD` values for your local machine. `LLM_API_KEY` must be a valid API key for the chosen provider (Anthropic by default — see [`DECISIONS.md`](./DECISIONS.md) §4). The optional `LLM_CALL_TIMEOUT_SECONDS` env var overrides the default 60-second per-call timeout. `.env` and local dotenv variants are ignored by git; keep secrets out of commits.

Running `jobhunter` boots a local FastAPI server on `127.0.0.1:8765` and (best-effort) opens the default browser. The web app validates local secrets and the monthly LLM spend cap, then tailors a CV and cover letter against the canonical CV. Job Hunter only writes local files and never submits to Upwork, LinkedIn, OnlineJobs PH, or any job board (`DECISIONS.md` §6).

```bash
# Install web extras and launch:
pip install -e ".[web,dev]"
jobhunter                # binds 127.0.0.1:8765, opens browser
jobhunter --port 9000    # override port
jobhunter --no-browser   # do not open the browser
```

Paste a job description into the dashboard textarea and click "Tailor this JD". The browser POSTs the JD to `/api/paste`; on success the server writes `cv.md` and `cover-letter.md` into a per-application directory under `./out/<slug>/` and records the call's cost in `./.cost-ledger.json` (both gitignored). On any failure before the LLM response is validated, no `./out/<slug>/` directory is created.

The canonical CV must be a text format (JSON Resume v1.0.0 today; markdown or YAML if the fall-back criterion in [`DECISIONS.md`](./DECISIONS.md) §2 fires). `.pdf`, `.docx`, and `.doc` paths are rejected by extension before any read attempt — Job Hunter never parses binary CV formats.

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

### Job Scan (automated candidate discovery)

Job Scan is a scheduled discovery pipeline: an external scan engine periodically
searches configured job boards, picks the best-fit roles against your canonical
CV, and files them as de-duplicated candidates. You review them on the **Job
Scan** dashboard page and hit **Generate CV** to run the full tailoring pipeline
— no copy-paste required.

**Settings** live in the UI at `/settings` under "Job Scan": search titles,
enabled sites (Indeed, OnlineJobs PH, JobStreet, LinkedIn), picks per site
(1–10), and a master on/off toggle. Settings are stored in the Supabase
`scan_settings` table (same project as the application tracker).

**App-side endpoints** (`/api/scan/*`):

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `GET`/`PUT` | `/api/scan/settings` | session | Read / save scan settings |
| `POST` | `/api/scan/results` | Bearer `INGEST_TOKEN` | Ingest a scan run (dedup by URL) |
| `GET` | `/api/scan/known-urls` | Bearer `INGEST_TOKEN` | Skip-list for the scanner |
| `GET` | `/api/scan/scans` | session | List all scans (newest first) |
| `GET` | `/api/scan/candidates` | session | List candidates (filterable by status) |
| `PATCH` | `/api/scan/candidates/{id}` | session | Dismiss a candidate |
| `POST` | `/api/scan/candidates/{id}/generate` | session | One-click Generate CV |
| `POST` | `/api/scan/run` | session | Manually trigger a scan via the n8n engine (`N8N_SCAN_TRIGGER_URL`) |

The two machine endpoints (`results`, `known-urls`) use the existing
`INGEST_TOKEN` Bearer token (same as the n8n `/api/paste` flows). Set
`INGEST_TOKEN` in `.env`.

**Supabase setup** (in addition to the application tracker steps above):
the migration `supabase/migrations/20260626000000_job_scan.sql` creates
`scan_settings`, `scans`, and `scan_candidates`. Run `supabase db reset`
locally or `supabase db push` on hosted after pulling this migration.

> **Scan engine (F2) is a separate component.** The app side only ingests
> results — it does not schedule or run browser automation. The scan engine
> (n8n custom image with Claude Code + Playwright MCP on Railway) is documented
> in the F2 implementation plan. See
> `docs/superpowers/specs/2026-06-26-job-scan-feature-overview.md` for the full
> feature spec and architecture diagram.

## Reproducible installs (uv)

`uv.lock` pins the full dependency graph (web + dev extras). For a byte-for-byte
reproducible environment:

```bash
uv sync --extra web --extra dev   # creates .venv from the lock
uv run pytest                     # run anything inside the locked env
```

Plain `pip install -e ".[web,dev]"` still works for casual use; the lockfile is
the source of truth when reproducibility matters (CI, Docker, onboarding).

## CI

`.github/workflows/ci.yml` runs on every push to `main` and every PR:

- **Backend** — installs the WeasyPrint system libraries, then runs Ruff (lint +
  format), mypy, and `pytest`. `pytest` is the hard gate; Ruff/mypy start
  **advisory** because the existing tree carries a lint/format backlog. To make
  them blocking: run a one-time `ruff check --fix && ruff format`, commit it,
  then delete the `continue-on-error:` lines.
- **Frontend** — `npm ci`, `tsc -b` typecheck, `npm run build`.
- **Docker** — builds the production image so Dockerfile breakage fails CI.

`.github/workflows/release.yml` runs on `v*` tags: builds the frontend, then the
sdist + wheel, asserts the frontend + fonts are bundled, and attaches the
artifacts to a GitHub Release.

## Deploy

Two supported targets, both using the single all-in-one image (Caddy + uvicorn):

- **Local / private** (this section) — `docker compose up`, reachable at
  `http://127.0.0.1:8080` behind basic-auth. Good behind Tailscale/VPN.
- **Oracle Cloud (always-free, public HTTPS, 24/7, push-to-deploy)** — see
  [`docs/deployment/oracle-cloud.md`](./docs/deployment/oracle-cloud.md) and
  [`docs/deployment/continuous-deployment.md`](./docs/deployment/continuous-deployment.md).

> ⚠️ Job Hunter runs on *your* LLM key + spend cap and trusts whoever clears
> Caddy basic-auth. Use a strong password; never expose n8n's admin UI publicly.

How it stays safe: the image runs Caddy + uvicorn together (supervisord). Caddy
is the public front door (basic-auth, plus TLS when given a domain) and
reverse-proxies to uvicorn on `127.0.0.1:8765`, so the app only ever sees
loopback traffic — the browser path needs no token and no frontend change.

```bash
cp .env.example .env                 # fill LLM_API_KEY, MONTHLY_SPEND_CAP_USD

# Add Caddy credentials to .env (compose auto-loads .env for ${...}):
echo "CADDY_BASIC_AUTH_USER=dave" >> .env
echo "CADDY_BASIC_AUTH_HASH=$(docker run --rm caddy caddy hash-password --plaintext 'change-me')" >> .env

docker compose up --build            # http://127.0.0.1:8080  (basic-auth)
```

State persists in Docker named volumes — `jobhunter-out` (tailored packages) and
`jobhunter-ledger` (spend ledger). `canonical-cv.json` and `config.yaml` are
bind-mounted (local) or baked into the image (cloud). Secrets are injected as
container env (`env_file: .env`) — no `.env` is baked into the image.

**Packaging caveat:** the wheel bundles the frontend `dist/` and fonts, but the
JSON Resume schema, `canonical-cv.json`, and `config.yaml` live at the repo root
and are read via `PROJECT_ROOT`. A bare `pip install` of the wheel must run from
a checkout; the Docker image sidesteps this by copying the whole repo.

## Repo layout

```
.
├── DECISIONS.md              # foundational decisions (runtime, schema)
├── canonical-cv.json         # canonical CV (JSON Resume v1.0.0)
├── pyproject.toml
├── schemas/
│   └── jsonresume-v1.0.0.json   # vendored — do NOT fetch at runtime
├── scripts/
│   └── validate_canonical_cv.py
├── src/jobhunter/
│   ├── __init__.py
│   ├── cli.py                # `jobhunter` launcher (web-only; no subcommands)
│   ├── config.py             # CANONICAL_CV_PATH, PROJECT_ROOT
│   ├── runtime_config.py     # dotenv secrets + monthly cap loader
│   ├── canonical_cv.py       # read_canonical_cv() — FR4 single reader
│   ├── llm_client.py         # anthropic SDK wrapper + cost computation
│   ├── slug.py               # ./out/<slug>/ deterministic slug helper
│   ├── spend_tracker.py      # .cost-ledger.json + monthly cap enforcement
│   ├── tailoring.py          # cap-check → LLM → atomic artifact write
│   └── web/                  # FastAPI app + React/Vite/Tailwind frontend
│       ├── api.py            # /healthz + /api/paste
│       └── frontend/         # Vite project; `npm run build` → dist/
├── out/                      # (gitignored) per-application <slug>/ packages
├── .cost-ledger.json         # (gitignored) cumulative monthly LLM spend
└── tests/
    ├── conftest.py
    ├── unit/                 # config, reader, slug, spend tracker, llm client
    └── integration/          # CLI entry stub, paste JD ingest, tailoring
```

## Status

Stories 1.1–1.5 (walking-skeleton runtime + canonical-CV reader hardening + JD ingest + single-call tailoring writing `./out/<slug>/`) complete. Story 1.6 (web-only pivot — FastAPI app + minimal React/Vite/Tailwind frontend) lands the bare `jobhunter` launcher. See `_bmad-output/implementation-artifacts/sprint-status.yaml` for sprint progress.
