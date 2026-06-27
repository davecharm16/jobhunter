# CLAUDE.md

> ## ⛔ #1 RULE — NEVER tell the user to stop/settle when blocked
> When you hit a blocker, you do **NOT** say "that's good enough", "let's pause",
> or "do it later". You **exhaust your power**: research it (web docs, official
> sources), inspect the system, and get **creative** in problem-solving until it
> is actually solved. Suggesting the user give up on what they asked for is a
> failure. Keep going until the goal works.

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Solo-developer pipeline that tailors a CV + cover letter (+ optional Upwork proposal) to a pasted job description, then runs three drift checks (**fabrication**, **content-loss**, **keyword-stuffing**) that *hold* any package showing drift instead of publishing it. Output lands in `./out/<slug>/`. The web UI is localhost-only, single-user, no auth.

**`DECISIONS.md` is the architectural source of truth** (numbered §1–§7). Read the relevant section before changing runtime, schema, the LLM boundary, persistence, or the web/auth model. Decisions are additive — never rewrite an entry; append a new dated one if overturning.

## Commands

```bash
uv sync --extra web --extra dev          # setup from the lockfile (or: pip install -e ".[web,dev]")
cp .env.example .env                      # fill secrets (see README "Configuration")
jobhunter                                 # boot the app on 127.0.0.1:8765
python scripts/validate_canonical_cv.py   # validate canonical CV against the vendored schema

pytest -q                                          # full suite — the only hard CI gate
pytest tests/unit/test_spend_tracker.py::test_x    # single test
ruff check . && ruff format . && mypy              # advisory in CI (lint backlog)

# Frontend (cwd: src/jobhunter/web/frontend/)
npm ci && npm run build                   # tsc -b && vite build → dist/, served by FastAPI
```

See `README.md` for full setup, the Supabase tracker steps, and CI/release details.

## Architecture (the load-bearing bits)

`src/jobhunter/tailoring.py::run_tailoring()` is the **single orchestrator**; `web/api.py` and everything else wrap it. Flow: sweep held packages → parse JD → classify board → select artifacts → cap-check + tailor (LLM) → **atomic `<slug>.tmp` → `os.replace()` write** → drift checks → notify. Invariants to preserve when editing it:

- **One code path; held-vs-passed is metadata, not branching.** Any `fail` verdict writes `package.held.json` + `drift-report.md` and sets `held=true`. The held-writer is the only post-matcher branch (structurally enforces no-notify-on-fail).
- **Atomic write:** on any failure before the rename, `./out/<slug>/` is never created.
- **`content_loss` + `keyword_stuffing` checks make zero LLM calls** — keep them pure rule-based.
- **Cap check before every LLM call** (`spend_tracker.py`, records to `.cost-ledger.json`).

Each `./out/<slug>/` directory *is* the persistence unit — read endpoints reconstruct state from its files (`metadata.json`, `package.drift.json`, etc.). No app database except the application tracker (DECISIONS.md §7, Supabase/psycopg, the only DB-backed feature).

Single-source boundaries — respect the contract, don't fan the logic out:
- All LLM calls go through `llm_client.py` (one provider at a time, DECISIONS.md §4).
- Canonical CV loads only via `canonical_cv.read_canonical_cv()`; path only from `config.CANONICAL_CV_PATH`.
- JSON Resume schema is vendored and never fetched at runtime (offline paste mode).

Config split: `.env` = secrets (`runtime_config.py`), `config.yaml` = committed tunables (`yaml_config.py`), `prompts/*.vN.md` = versioned templates.

## Hard constraints (DECISIONS.md §5/§6)
Bind `127.0.0.1` only, never `0.0.0.0`. No auth. No outbound submission to any job board — the human always presses submit.

## Workflow Orchestration

### 1. Plan Node Default
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately - don't keep pushing
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity

### 2. Subagent Strategy
- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One tack per subagent for focused execution

### 3. Self-Improvement Loop
- After ANY correction from the user: update tasks/lessons.md with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until mistake rate drops
- Review lessons at session start for relevant project

### 4. Verification Before Done
- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness

### 5. Demand Elegance (Balanced)
- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes - don't over-engineer
- Challenge your own work before presenting it

### 6. Autonomous Bug Fixing
- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, failing tests - then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how

## Task Management

1. *Plan First*: Write plan to tasks/todo.md with checkable items
2. *Verify Plan*: Check in before starting implementation
3. *Track Progress*: Mark items complete as you go
4. *Explain Changes*: High-level summary at each step
5. *Document Results*: Add review section to tasks/todo.md
6. *Capture Lessons*: Update tasks/lessons.md after corrections

## Core Principles

- *Simplicity First*: Make every change as simple as possible. Impact minimal code.
- *No Laziness*: Find root causes. No temporary fixes. Senior developer standards.
- *Minimat Impact*: Changes should only touch what's necessary. Avoid introducing bugs.
- *YAGNI*: Think like a senior dev, embrace the principle of You are not gonna need it. This is to avoid over engineering of things but making things simple as possible 
- *DRY*: Don't repeat yourself, check for every existing or similar code structure or components, check how you can abstract or extend it.
- *ASK WHEN YOU NEED HUMAN HELP*: Clarify with the user if you encounter a problem that you think the user will be able to help. Creative ideas, confirmations, being stuck on a problem. Think of them as your co-worker, ONLY ASK when you exhausted all your brain power and still don't solve it. Explain the context of your approach first and what have you already done for better context alignment.

## Reference docs
- `DECISIONS.md` — architectural decisions (§4 LLM provider, §5/§6 web-only, §7 Supabase tracker).
- `docs/n8n-contract.md` — the `POST /api/paste` ingest contract for n8n scrapers.
- `docs/deployment/` — Oracle Cloud + continuous-deployment topology.
- `docs/canonical-cv-extensions.md` — the `tags` / `highImpact` JSON Resume extensions.
