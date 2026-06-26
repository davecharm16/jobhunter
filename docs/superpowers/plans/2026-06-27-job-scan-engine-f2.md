# Job Scan Engine (F2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the external scan engine that the app-side already waits for — an n8n workflow on Railway that runs `claude -p` + Playwright MCP to scrape Indeed/OnlineJobs PH/JobStreet/LinkedIn for the configured titles, picks the top 3 per site against the canonical CV, captures full JDs, and POSTs results to the app's `/api/scan/results`.

**Architecture:** The scanner is an **external ingestion agent** (DECISIONS.md §8), in the same category as the existing n8n `/api/paste` flows. A custom Docker image (Playwright base + n8n + Claude Code CLI + Playwright MCP) runs on Railway. An n8n workflow (Cron + manual Webhook trigger) fetches scan inputs from the app, runs Claude headless to scrape+rank+capture, validates Claude's JSON, and POSTs it back. The app does the deterministic, tested part; the browser/anti-bot mess lives here, outside the app's test boundary.

**Tech Stack:** n8n (self-hosted Docker on Railway), Docker (Playwright `jammy` base image), Claude Code CLI (`@anthropic-ai/claude-code`, headless `-p`), Playwright MCP (`@playwright/mcp`), FastAPI app (Python) for the two new ingestion-support endpoints.

**Spec:** `docs/superpowers/specs/2026-06-26-job-scan-design.md` (§ the n8n workflow + custom image). **North star:** `docs/superpowers/specs/2026-06-26-job-scan-feature-overview.md` → **F2** (US/AC/DOD). Cite `[F2]` + AC numbers in commits.

## Global Constraints

- **The scanner is external; the APP keeps one LLM provider (DECISIONS.md §4).** Claude-in-n8n's LLM usage is upstream. Do **not** add Playwright/Claude-Code/httpx to the app's `pyproject` — `tests/unit/test_secret_hygiene` forbids them as direct deps. Browser deps live ONLY in the Docker image.
- **No job-board hostnames in app source/tests.** Site identifiers are bare (`indeed`, `onlinejobs_ph`, `jobstreet`, `linkedin`). The scan *prompt* (`prompts/job_scan.v1.md`) MAY name the sites/URLs — prompts are data, not source, and are not covered by `test_no_job_board_hostnames_in_jobhunter_source` (which scans Python source). **Verify this assumption in Task 2** by running the suite after adding the prompt; if the guard test trips on `prompts/`, keep site *search URLs* out of the committed prompt and inject them from n8n instead.
- **Picks per site = 3** (read from `scan_settings.picks_per_site`, default 3). The engine must honor the live setting, not hardcode.
- **Auth:** the engine POSTs to `/api/scan/results` and GETs `/api/scan/known-urls` with `Authorization: Bearer <INGEST_TOKEN>` (same token contract as `docs/n8n-contract.md`). UI endpoints (`/api/scan/settings`, `/api/canonical-profile`) are loopback in-app, but the engine reaches them over the network — so **the engine's reads of settings/profile also need the network path**; expose them as token-guarded OR have n8n call them from the same trusted origin. **Decision:** make `/api/canonical-profile` token-guarded (machine endpoint) and have n8n send the Bearer token on all four calls. (Settings/known-urls/profile reads + results write all carry the token.)
- **The app must be reachable from Railway.** Same requirement as the existing `/api/paste` n8n flows. Use the deployed public base URL (`APP_BASE_URL`). For pre-deploy testing, a tunnel (`cloudflared tunnel --url http://127.0.0.1:8765`) gives a temporary public URL. This is a prerequisite, not a code task.
- **Tests:** app-side tasks (1, 2) are TDD with `.venv/bin/python -m pytest`. Infra tasks (3–6) are **build-verify** (no unit tests possible); each lists explicit manual verification. The 5 pre-existing `.env`-driven integration failures are known/unrelated — add no new ones.
- **Anti-bot reality:** Railway is a datacenter IP; Indeed/LinkedIn/JobStreet actively block. Treat per-site `blocked`/`empty` as normal states the workflow reports, never a hard failure. A residential proxy may be needed later — flagged, not solved here.

## Prerequisites (not code — verify before Task 4)

- **P1.** App deployed at a public `APP_BASE_URL` (or a `cloudflared` tunnel for testing).
- **P2.** `INGEST_TOKEN` value known and identical on app (`.env`) and n8n (workflow env `INGEST_SHARED_TOKEN`).
- **P3.** A Claude Code **OAuth token** for the scanner, so it runs on your Claude **subscription** (Pro/Max) rather than a metered API key. Mint it once on your machine: `claude setup-token` (requires a Pro/Max/Team/Enterprise plan; prints a ~1-year token to stdout — it is not saved for you). Store it as `CLAUDE_CODE_OAUTH_TOKEN` on the n8n service. **Critical:** `ANTHROPIC_API_KEY` must NOT be set in the n8n container — if it is, it takes precedence and the API key (metered billing) is used instead of your subscription. (Subscription usage counts against your Pro/Max plan's usage limits. Docs: https://code.claude.com/docs/en/authentication.md)
- **P4.** Railway project lets you deploy a **custom Dockerfile** for the n8n service (Railway supports Dockerfile builds).

---

## File Structure

| File | Responsibility |
|------|----------------|
| `src/jobhunter/canonical_profile.py` | `build_canonical_profile(cv) -> dict` — condensed CV for ranking. Pure, unit-tested. |
| `src/jobhunter/web/routes/scan.py` (modify) | Add token-guarded `GET /api/canonical-profile`. |
| `tests/unit/test_canonical_profile.py` | Unit tests for the projection. |
| `tests/unit/test_canonical_profile_api.py` | Endpoint test (shape + auth wiring). |
| `prompts/job_scan.v1.md` | Versioned scan prompt Claude runs (loaded via `prompts.load_prompt`). |
| `tests/unit/test_job_scan_prompt.py` | Asserts the prompt loads and contains the contract tokens. |
| `deploy/n8n/Dockerfile` | Custom n8n image: Playwright base + n8n + Claude Code + Playwright MCP. |
| `deploy/n8n/mcp.json` | Playwright MCP config passed to `claude -p --mcp-config`. |
| `deploy/n8n/run-scan.sh` | The Execute Command script: assembles flags, runs `claude -p`, emits JSON to stdout. |
| `deploy/n8n/job-scan-workflow.json` | Exported n8n workflow (from Task 5, via n8n-mcp). |
| `docs/deployment/n8n-scan-engine.md` | Build/deploy/wire instructions + the workflow design + anti-bot notes. |
| `docs/n8n-contract.md` (modify) | Add the scan-results contract reference (points to `/api/scan/results`). |

---

## Task 1 [TDD, app]: Canonical-profile projection + endpoint

**Files:**
- Create: `src/jobhunter/canonical_profile.py`
- Create: `tests/unit/test_canonical_profile.py`
- Create: `tests/unit/test_canonical_profile_api.py`
- Modify: `src/jobhunter/web/routes/scan.py`

**Interfaces:**
- Consumes: `canonical_cv.read_canonical_cv() -> dict` (existing); `require_ingest_token` (existing, `jobhunter.web.auth`).
- Produces: `build_canonical_profile(cv: dict) -> dict` returning `{name, label, summary, skills: list[str], recent_titles: list[str]}`; `GET /api/canonical-profile` (Bearer `INGEST_TOKEN`) returning that dict.

- [ ] **Step 1: Write the failing projection test**

```python
# tests/unit/test_canonical_profile.py
from jobhunter.canonical_profile import build_canonical_profile

def test_projection_extracts_core_fields():
    cv = {
        "basics": {"name": "Dave", "label": "Solutions Designer", "summary": "Builds things."},
        "skills": [{"name": "Mobile"}, {"name": "Solutions Design"}],
        "work": [
            {"position": "Solutions Designer", "name": "Stratpoint"},
            {"position": "Mobile Dev", "name": "Acme"},
        ],
    }
    p = build_canonical_profile(cv)
    assert p["name"] == "Dave"
    assert p["label"] == "Solutions Designer"
    assert p["summary"] == "Builds things."
    assert p["skills"] == ["Mobile", "Solutions Design"]
    assert p["recent_titles"] == ["Solutions Designer @ Stratpoint", "Mobile Dev @ Acme"]

def test_projection_tolerates_missing_sections():
    p = build_canonical_profile({"basics": {"name": "X"}})
    assert p["name"] == "X"
    assert p["label"] == ""
    assert p["summary"] == ""
    assert p["skills"] == []
    assert p["recent_titles"] == []

def test_projection_caps_lengths():
    cv = {
        "basics": {"name": "N"},
        "skills": [{"name": f"s{i}"} for i in range(50)],
        "work": [{"position": f"p{i}", "name": "c"} for i in range(20)],
    }
    p = build_canonical_profile(cv)
    assert len(p["skills"]) == 30
    assert len(p["recent_titles"]) == 8
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_canonical_profile.py -v`
Expected: FAIL — `ModuleNotFoundError: jobhunter.canonical_profile`.

- [ ] **Step 3: Implement `src/jobhunter/canonical_profile.py`**

```python
"""Condensed canonical-CV projection for the external scan engine's ranking.

Pure function — no I/O. The scan prompt embeds this so Claude can judge fit
without shipping the entire CV. Kept small to bound prompt size."""

from typing import Any

_MAX_SKILLS = 30
_MAX_TITLES = 8


def build_canonical_profile(cv: dict[str, Any]) -> dict[str, Any]:
    basics = cv.get("basics") or {}
    skills = [
        s.get("name", "")
        for s in (cv.get("skills") or [])
        if isinstance(s, dict) and s.get("name")
    ][:_MAX_SKILLS]
    titles = []
    for w in (cv.get("work") or [])[:_MAX_TITLES]:
        if not isinstance(w, dict):
            continue
        position = w.get("position", "")
        company = w.get("name", "")
        if position or company:
            titles.append(f"{position} @ {company}".strip(" @"))
    return {
        "name": basics.get("name", ""),
        "label": basics.get("label", ""),
        "summary": basics.get("summary", ""),
        "skills": skills,
        "recent_titles": titles,
    }


__all__ = ["build_canonical_profile"]
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/test_canonical_profile.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Write the failing endpoint test**

```python
# tests/unit/test_canonical_profile_api.py
from fastapi.testclient import TestClient
from jobhunter.web.api import create_app

def test_canonical_profile_endpoint_returns_projection(monkeypatch):
    import jobhunter.web.routes.scan as scan_routes
    monkeypatch.setattr(
        scan_routes, "read_canonical_cv",
        lambda: {"basics": {"name": "Dave", "label": "SD", "summary": "s"},
                 "skills": [{"name": "Mobile"}], "work": []},
    )
    client = TestClient(create_app())  # TestClient is loopback -> token bypassed
    r = client.get("/api/canonical-profile")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Dave"
    assert body["skills"] == ["Mobile"]
```

- [ ] **Step 6: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_canonical_profile_api.py -v`
Expected: FAIL — 404 (route not defined).

- [ ] **Step 7: Add the endpoint to `src/jobhunter/web/routes/scan.py`**

Add imports near the top (extend existing import groups):
```python
from jobhunter.canonical_cv import read_canonical_cv
from jobhunter.canonical_profile import build_canonical_profile
```
Add the route (place near `known_urls`, since both are machine endpoints):
```python
@router.get("/api/canonical-profile", dependencies=[Depends(require_ingest_token)])
def canonical_profile() -> dict[str, Any]:
    return build_canonical_profile(read_canonical_cv())
```

- [ ] **Step 8: Run both new tests + full suite**

Run: `.venv/bin/python -m pytest tests/unit/test_canonical_profile.py tests/unit/test_canonical_profile_api.py -v`
Expected: PASS.
Run: `.venv/bin/python -m pytest -q`
Expected: only the 5 known pre-existing failures.

- [ ] **Step 9: Lint + commit**

```bash
.venv/bin/python -m ruff check src/jobhunter/canonical_profile.py src/jobhunter/web/routes/scan.py tests/unit/test_canonical_profile.py tests/unit/test_canonical_profile_api.py
git add src/jobhunter/canonical_profile.py src/jobhunter/web/routes/scan.py tests/unit/test_canonical_profile.py tests/unit/test_canonical_profile_api.py
git commit -m "feat(scan): canonical-profile projection + GET /api/canonical-profile [F2]"
```

---

## Task 2 [TDD-light, app]: The scan prompt

**Files:**
- Create: `prompts/job_scan.v1.md`
- Create: `tests/unit/test_job_scan_prompt.py`

**Interfaces:**
- Consumes: `prompts.load_prompt("job_scan")` (existing loader; reads `prompts/job_scan.v<N>.md`).
- Produces: a versioned prompt the n8n workflow injects runtime data into. It uses **placeholder tokens** the workflow replaces: `{{SEARCH_TITLES}}`, `{{SITES_ENABLED}}`, `{{PICKS_PER_SITE}}`, `{{CANONICAL_PROFILE}}`, `{{KNOWN_URLS}}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_job_scan_prompt.py
from jobhunter.prompts import load_prompt

def test_job_scan_prompt_loads_and_has_contract_tokens():
    p = load_prompt("job_scan")
    assert p.version == "v1"
    body = p.text if hasattr(p, "text") else p.body  # loader exposes the template text
    for token in ("{{SEARCH_TITLES}}", "{{SITES_ENABLED}}", "{{PICKS_PER_SITE}}",
                  "{{CANONICAL_PROFILE}}", "{{KNOWN_URLS}}"):
        assert token in body
    # the output contract Claude must emit
    for field in ("site", "url", "title", "company", "location", "jd_text",
                  "fit_reason", "fit_score", "site_summary", "candidates"):
        assert field in body
```

> NOTE: confirm the loader's text attribute name first — open `src/jobhunter/prompts.py` and check whether the loaded object exposes `.text` or `.body` (the `@dataclass` around line 44 defines it). Use the real attribute in the test; the `hasattr` fallback above is a safety net, not a license to skip checking.

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_job_scan_prompt.py -v`
Expected: FAIL — `PromptNotFound` / no `job_scan` template.

- [ ] **Step 3: Create `prompts/job_scan.v1.md`**

```markdown
# Job Scan — discovery agent

You are an automated job-discovery agent. Using the Playwright browser tools
available to you, search the enabled job sites for roles matching the search
titles, pick the best-fitting roles for THIS candidate, capture each full job
description, and return a single JSON object. You never apply to anything — you
only discover and report.

## Inputs

- Search titles: {{SEARCH_TITLES}}
- Sites enabled: {{SITES_ENABLED}}
- Picks per site: {{PICKS_PER_SITE}}
- Already-seen job URLs (DO NOT return any of these): {{KNOWN_URLS}}
- Candidate profile (rank fit against this):
{{CANONICAL_PROFILE}}

## Procedure

For EACH enabled site:
1. For each search title, open the site's job search and run the query.
2. Skip any listing whose URL is in the already-seen list BEFORE opening it.
3. From the remaining listings, rank by fit to the candidate profile and select
   the top {{PICKS_PER_SITE}}.
4. Open each selected listing and scrape the FULL job-description text.
5. If the site blocks you, shows a login/CAPTCHA wall, or returns nothing,
   record that site's status as `blocked` or `empty` and move on — do NOT fail
   the whole run.

Pace yourself like a human (small delays, no rapid-fire navigation).

## Output — return ONLY this JSON, nothing else

{
  "started_at": "<ISO-8601 UTC when you began>",
  "finished_at": "<ISO-8601 UTC when you finished>",
  "site_summary": {
    "<site>": {"status": "ok|blocked|empty", "count": <int>}
  },
  "candidates": [
    {
      "site": "<one of the enabled site identifiers>",
      "url": "<canonical listing URL>",
      "title": "<job title>",
      "company": "<company or null>",
      "location": "<location or null>",
      "jd_text": "<full job description text>",
      "fit_reason": "<one sentence: why this fits the candidate>",
      "fit_score": <number 0..1>
    }
  ]
}

Use the exact site identifiers from "Sites enabled". Return at most
{{PICKS_PER_SITE}} candidates per site. Emit valid JSON with no surrounding
prose or markdown fences.
```

- [ ] **Step 4: Run the test + full suite (verify the no-hostname guard does NOT trip on prompts)**

Run: `.venv/bin/python -m pytest tests/unit/test_job_scan_prompt.py -v`
Expected: PASS.
Run: `.venv/bin/python -m pytest -k "job_board_hostname" -q`
Expected: PASS (the guard scans Python source, not `prompts/`). If it FAILS, the prompt must not contain literal job-board hostnames — this prompt doesn't (sites are injected at runtime), so it should pass; if a future edit adds a hostname, move it to the n8n injection layer.

- [ ] **Step 5: Commit**

```bash
git add prompts/job_scan.v1.md tests/unit/test_job_scan_prompt.py
git commit -m "feat(scan): versioned job_scan.v1 prompt for the engine [F2]"
```

---

## Task 3 [BUILD-VERIFY, infra]: Custom n8n Docker image

**Files:**
- Create: `deploy/n8n/Dockerfile`
- Create: `deploy/n8n/mcp.json`
- Create: `deploy/n8n/run-scan.sh`

**Interfaces:**
- Produces: a Docker image runnable as the n8n service, containing `n8n`, `claude` (Claude Code CLI), and a Playwright MCP reachable via `--mcp-config`. `run-scan.sh` is the script the n8n Execute Command node calls.

- [ ] **Step 1: Create `deploy/n8n/Dockerfile`**

```dockerfile
# Playwright base = Node + Chromium + all browser OS deps preinstalled (Debian).
# We layer n8n + Claude Code CLI + the Playwright MCP on top. This avoids the
# Alpine/Chromium pain of extending the stock n8nio/n8n image.
FROM mcr.microsoft.com/playwright:v1.49.0-jammy

ENV N8N_PORT=5678 \
    NODE_ENV=production \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# n8n, Claude Code CLI, Playwright MCP (global)
RUN npm install -g n8n@latest @anthropic-ai/claude-code @playwright/mcp \
    && npm cache clean --force

# Scan assets baked into the image (the workflow references these paths).
RUN mkdir -p /opt/scan
COPY deploy/n8n/mcp.json /opt/scan/mcp.json
COPY deploy/n8n/run-scan.sh /opt/scan/run-scan.sh
COPY prompts/job_scan.v1.md /opt/scan/job_scan.v1.md
RUN chmod +x /opt/scan/run-scan.sh

EXPOSE 5678
CMD ["n8n", "start"]
```

> NOTE: pin the Playwright tag (`v1.49.0-jammy`) to a real, current tag — check https://mcr.microsoft.com/ for the latest `playwright:*-jammy`. The MCP and base browser version should be compatible (Playwright MCP drives the base image's Chromium).

- [ ] **Step 2: Create `deploy/n8n/mcp.json`**

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["-y", "@playwright/mcp@latest", "--headless", "--browser", "chromium"]
    }
  }
}
```

- [ ] **Step 3: Create `deploy/n8n/run-scan.sh`**

```bash
#!/usr/bin/env bash
# Invoked by the n8n Execute Command node. Reads the fully-assembled prompt on
# stdin (n8n pipes it in), runs Claude headless with the Playwright MCP, and
# prints Claude's result JSON to stdout for n8n to parse.
#
# Auth (set on the n8n service): CLAUDE_CODE_OAUTH_TOKEN (runs on your Claude
# subscription). Do NOT set ANTHROPIC_API_KEY in this container — it overrides
# the OAuth token. The `claude` CLI reads CLAUDE_CODE_OAUTH_TOKEN from the env.
set -euo pipefail

PROMPT="$(cat)"   # n8n writes the assembled prompt to stdin

claude -p "$PROMPT" \
  --mcp-config /opt/scan/mcp.json \
  --allowedTools "mcp__playwright__*" \
  --permission-mode bypassPermissions \
  --output-format json
```

> NOTE: Claude Code CLI flags evolve. In Task 4, after the image builds, run
> `docker run --rm <image> claude -p --help` and reconcile these flag names
> (`--mcp-config`, `--allowedTools`, `--permission-mode`, `--output-format`).
> Adjust `run-scan.sh` to the installed version's exact flags. `--output-format
> json` makes Claude wrap its reply in an envelope with a `result` field — the
> n8n parse node (Task 5) extracts the inner JSON from that.

- [ ] **Step 4: Build the image locally and smoke-test the toolchain**

Run (from repo root, where the Dockerfile's COPY paths resolve):
```bash
docker build -f deploy/n8n/Dockerfile -t jobhunter-n8n-scan:dev .
docker run --rm jobhunter-n8n-scan:dev node -e "console.log('node ok')"
docker run --rm jobhunter-n8n-scan:dev claude --version
docker run --rm jobhunter-n8n-scan:dev sh -lc 'ls /opt/scan && which n8n'
```
Expected: image builds; `claude --version` prints a version; `/opt/scan` lists `mcp.json`, `run-scan.sh`, `job_scan.v1.md`; `n8n` resolves.

- [ ] **Step 5: Smoke-test Claude + Playwright MCP end-to-end (cheap, no job sites)**

```bash
docker run --rm -e CLAUDE_CODE_OAUTH_TOKEN="$CLAUDE_CODE_OAUTH_TOKEN" jobhunter-n8n-scan:dev \
  sh -lc 'echo "Use the Playwright tools to open https://example.com and return ONLY the page <h1> text as JSON {\"h1\":\"...\"}." | /opt/scan/run-scan.sh'
```
Expected: JSON output containing the example.com heading (proves Claude can drive Playwright MCP headless in the image, authenticated via your subscription token). If it errors on flags, fix per the Task 3 NOTE and re-run. (Mint `CLAUDE_CODE_OAUTH_TOKEN` first with `claude setup-token` and export it in your shell.)

- [ ] **Step 6: Commit**

```bash
git add deploy/n8n/Dockerfile deploy/n8n/mcp.json deploy/n8n/run-scan.sh
git commit -m "feat(scan-engine): custom n8n image (Playwright + Claude Code + MCP) [F2]"
```

---

## Task 4 [BUILD-VERIFY, infra]: Deploy the image + configure the n8n service on Railway

**Files:** none (Railway configuration). Records settings in `docs/deployment/n8n-scan-engine.md` (written in Task 7).

- [ ] **Step 1: Point the Railway n8n service at the custom Dockerfile**

In the Railway n8n service settings, set the build to use `deploy/n8n/Dockerfile` (Railway → service → Settings → Build → Dockerfile path), with the repo as build context (so the `COPY deploy/n8n/...` and `COPY prompts/...` paths resolve). Trigger a deploy.

- [ ] **Step 2: Set the n8n service environment variables**

On the Railway n8n service add:
- `CLAUDE_CODE_OAUTH_TOKEN` = the token from `claude setup-token` (P3) — runs the scanner on your Claude subscription.
- **Do NOT set `ANTHROPIC_API_KEY`** on this service — it would override the OAuth token and switch to metered API billing.
- `INGEST_SHARED_TOKEN` = the same value as the app's `INGEST_TOKEN` (P2).
- `APP_BASE_URL` = the app's public base URL (P1), e.g. `https://<app-host>`.
- Keep n8n's existing persistence env (DB/encryption key) unchanged.

- [ ] **Step 3: Verify the deployed container has the toolchain**

In the Railway n8n service shell (or a one-off command):
```bash
claude --version && ls /opt/scan && node -v
```
Expected: versions print; `/opt/scan` holds the three files. n8n UI loads normally.

- [ ] **Step 4: Reconcile Claude CLI flags on the deployed image**

```bash
claude -p --help
```
Confirm the flags in `run-scan.sh` match this version; if not, update `run-scan.sh`, rebuild/redeploy, and re-verify. (Commit any flag fix with `fix(scan-engine): reconcile claude CLI flags [F2]`.)

---

## Task 5 [BUILD-VERIFY, infra]: Build the n8n workflow

**Files:**
- Create: `deploy/n8n/job-scan-workflow.json` (exported after building)

**Build via the n8n-mcp tools** (read its SDK reference + best practices first, per the MCP instructions). The workflow nodes, in order:

- [ ] **Step 1: Triggers (two entry points into a shared path)**
  - **Cron** node — the scheduled run (e.g. daily 08:00 Asia/Manila). Records the schedule.
  - **Webhook** node — path `scan-run`, method POST. This is the URL the app's "Run scan now" button (`N8N_SCAN_TRIGGER_URL`) pings. Both triggers feed the same next node.

- [ ] **Step 2: Fetch inputs from the app (3 HTTP Request nodes, each with `Authorization: Bearer {{$env.INGEST_SHARED_TOKEN}}`)**
  - `GET {{$env.APP_BASE_URL}}/api/scan/settings`
  - `GET {{$env.APP_BASE_URL}}/api/scan/known-urls`
  - `GET {{$env.APP_BASE_URL}}/api/canonical-profile`
  - If `settings.enabled` is false, short-circuit (IF node → No-Op) so a disabled scan records nothing (F1 AC4).

- [ ] **Step 3: Assemble the prompt (Code node)**
  Read `/opt/scan/job_scan.v1.md`, replace the tokens with the fetched values:
  `{{SEARCH_TITLES}}` ← settings.search_titles, `{{SITES_ENABLED}}` ← settings.sites_enabled, `{{PICKS_PER_SITE}}` ← settings.picks_per_site, `{{CANONICAL_PROFILE}}` ← JSON.stringify(profile), `{{KNOWN_URLS}}` ← JSON.stringify(urls). Output the assembled prompt string.

- [ ] **Step 4: Execute Command node**
  Command: `/opt/scan/run-scan.sh`, with the assembled prompt piped to **stdin**. (Execute Command supports passing input; if the n8n version can't pipe stdin easily, write the prompt to a temp file in a prior node and `cat <file> | /opt/scan/run-scan.sh`.) Capture stdout.

- [ ] **Step 5: Parse + validate (Code node)**
  Parse Claude's `--output-format json` envelope, extract the inner result JSON (the `result` field), `JSON.parse` it, and validate it has `site_summary` + `candidates[]` with the required fields. On parse failure, throw (the run errors in n8n; nothing partial is POSTed).

- [ ] **Step 6: POST results (HTTP Request node)**
  `POST {{$env.APP_BASE_URL}}/api/scan/results` with `Authorization: Bearer {{$env.INGEST_SHARED_TOKEN}}` and the validated JSON body.

- [ ] **Step 7: Validate + export the workflow**
  Use the n8n-mcp validation tool; fix any node errors. Then export the workflow JSON to `deploy/n8n/job-scan-workflow.json` and commit:
  ```bash
  git add deploy/n8n/job-scan-workflow.json
  git commit -m "feat(scan-engine): n8n scan workflow (cron + manual webhook) [F2]"
  ```

- [ ] **Step 8: Manual single-run verification**
  Trigger the workflow manually in n8n (Execute Workflow). Watch each node: settings/known-urls/profile fetched (200), prompt assembled, Execute Command returns JSON, parse passes, POST returns `{received, new, skipped}`. Confirm new candidates appear on the app's `/job-scan` dashboard. Expect some sites `blocked`/`empty` — that's normal.

---

## Task 6 [BUILD-VERIFY, wire + e2e]: Connect the button + full loop

**Files:** none (config) — app `.env`.

- [ ] **Step 1: Get the webhook URL**
  Copy the Webhook node's production URL from n8n (e.g. `https://<n8n-host>/webhook/scan-run`).

- [ ] **Step 2: Set it on the app**
  Add to the app's `.env`: `N8N_SCAN_TRIGGER_URL=https://<n8n-host>/webhook/scan-run`. Restart the app.

- [ ] **Step 3: End-to-end test via the button**
  On `/job-scan`, click **Run scan now (3 per site)**. Expected: the alert "Scan started…", the n8n workflow fires (visible in n8n executions), and after it completes new candidates appear on refresh. If a `GCHAT_WEBHOOK_URL` is set, a dashboard-link notification arrives.

- [ ] **Step 4: Verify dedup across runs**
  Run the scan twice. The second run's POST should report `new` < total (already-seen URLs skipped, both at the agent skip-list layer and the DB UNIQUE layer). Confirm no duplicate cards.

---

## Task 7 [docs]: Deployment + contract docs

**Files:**
- Create: `docs/deployment/n8n-scan-engine.md`
- Modify: `docs/n8n-contract.md`

- [ ] **Step 1: Write `docs/deployment/n8n-scan-engine.md`**
  Cover: the custom image (what it layers + why the Playwright base), the Railway build/Dockerfile setting, the required n8n env vars (`ANTHROPIC_API_KEY`, `INGEST_SHARED_TOKEN`, `APP_BASE_URL`), the workflow node-by-node design, how to set `N8N_SCAN_TRIGGER_URL` on the app, the Claude-CLI-flag reconciliation step, and the anti-bot reality (datacenter IP; `blocked`/`empty` normal; residential proxy as a future option).

- [ ] **Step 2: Update `docs/n8n-contract.md`**
  Add a short section noting that the scan engine POSTs to `/api/scan/results` (and GETs `/api/scan/known-urls` + `/api/canonical-profile`) under the same `Authorization: Bearer ${INGEST_SHARED_TOKEN}` contract, linking to the design spec and the deployment doc.

- [ ] **Step 3: Commit**

```bash
git add docs/deployment/n8n-scan-engine.md docs/n8n-contract.md
git commit -m "docs(scan-engine): deployment + contract for the n8n scan engine [F2]"
```

---

## Self-Review (completed during planning)

- **Spec coverage (F2 ACs):** AC1 n8n Cron + fetch inputs + claude-p + POST → Tasks 4/5; AC2 custom image runs `claude -p` + Playwright MCP → Task 3; AC3 per-site search, skip known URLs, rank top-N, scrape full JD → the prompt (Task 2) + workflow (Task 5); AC4 single JSON payload (summary + candidates[]) → Task 2 output contract + Task 5 parse/POST; AC5 blocked/empty is normal, other sites still complete → prompt Step 5 + workflow; AC6 Bearer `INGEST_TOKEN` on the POST → Task 5 Step 6. F2 DOD (custom image documented, workflow exported + checked in, versioned prompt, documented manual test, anti-bot acknowledged) → Tasks 3/5/2/5-8/7.
- **App-side support the engine consumes:** `GET /api/canonical-profile` was the one open app-side dependency flagged at the end of the app-side plan — implemented here in Task 1 (token-guarded, since the engine reads it over the network).
- **Placeholder scan:** the two explicit "verify against installed version" notes (Claude CLI flags, Playwright base tag, loader attribute name) are real verification steps with exact commands, not deferred work.
- **Type/consistency:** the prompt's output JSON fields exactly match `POST /api/scan/results`'s `ResultsRequest`/`CandidatePayload` (site, url, title, company, location, jd_text, fit_reason, fit_score; site_summary; started_at/finished_at). The token env name is `INGEST_SHARED_TOKEN` on n8n = `INGEST_TOKEN` on the app (per `docs/n8n-contract.md`).

## Risks / open items (carried from the design spec)

- **Anti-bot on Railway datacenter IP** — Indeed/LinkedIn/JobStreet may return `blocked` often. Mitigations beyond stealth/pacing (residential proxy, persistent logged-in profile volume) are deferred; flagged here so a mostly-`blocked` first run is read as "expected," not "broken."
- **Image size / Railway memory** — the Playwright base + Chromium is large; confirm the Railway plan has headroom (Task 4).
- **Claude CLI non-interactive tool permissions** — `--permission-mode bypassPermissions` (== `--dangerously-skip-permissions`) is required for headless MCP tool use. Confirmed against the docs (2026-06); still re-verify on the installed image version (Task 3/4 notes).
- **Cost / quota per run** — each scan is a multi-step agentic Claude run with browser tool calls; tokens add up. Because the scanner uses your **Claude subscription** (`CLAUDE_CODE_OAUTH_TOKEN`), each run draws on your **Pro/Max usage limits** — the *same* quota you use for coding. A frequent Cron cadence could eat into that; tune the schedule and `picks_per_site` accordingly. (This is separate from the app's `MONTHLY_SPEND_CAP_USD`, which guards only the app's own `run_tailoring`.)
