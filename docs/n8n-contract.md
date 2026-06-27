# n8n ingest contract (Story 7.1)

This is the canonical JSON contract every scheduled n8n flow in Epic 7 uses to hand JDs off to the Job Hunter core pipeline. Stories 7.2 (Upwork), 7.3 (OnlineJobs.ph), and 7.4 (LinkedIn email) all copy this shape — one contract, one auth check, one body shape.

## Endpoint

`POST /api/paste`

The Story 7.1 spec text refers to this endpoint as `/ingest`; that name is its pre-pivot identifier. Post-pivot (DECISIONS.md §6) the endpoint lives at `/api/paste` because the same handler serves the browser paste UI and the n8n channel adapters. The body shape and auth model below are identical across both callers — there is no separate `/ingest` route.

## Authentication

The route applies the `require_ingest_token` dependency from Story 2.11:

- **Loopback callers** (`127.0.0.1`, `::1`, `localhost`, FastAPI `TestClient`) bypass the token check. The browser paste UI binds to `127.0.0.1` and so never needs to send a token.
- **Non-loopback callers** (i.e. every n8n flow that talks to the pipeline over a real network hop) MUST present `Authorization: Bearer <token>`. The server compares the presented token against the `INGEST_TOKEN` environment variable via constant-time compare.

The shared secret is stored in the project's `.env` file under the key `INGEST_TOKEN` (see `.env.example`). The Story 7.1 spec text uses the name `INGEST_SHARED_TOKEN`; that is the same key — the post-pivot environment variable is named `INGEST_TOKEN` to align with Story 2.11's tests and runtime config loader. n8n flows reference it as the workflow-level environment variable `INGEST_SHARED_TOKEN` (mapped by the hosting platform), so the on-server `INGEST_TOKEN` and the on-n8n `INGEST_SHARED_TOKEN` carry the same value.

`.env` is `.gitignore`'d (FR41) and the token value never appears in a flow JSON committed to the repo.

## Request headers

| Header          | Value                                | Notes                                     |
| --------------- | ------------------------------------ | ----------------------------------------- |
| `Authorization` | `Bearer ${INGEST_SHARED_TOKEN}`      | Required for non-loopback callers (401).  |
| `Content-Type`  | `application/json`                   | Required.                                 |

## Request body

```json
{
  "jd_text": "Full JD text or markdown...",
  "source": "upwork",
  "url": "https://example.com/job/123",
  "discovered_at": "2026-05-24T10:15:00Z"
}
```

### Required fields

| Field     | Type   | Constraint    | Description                                                                                       |
| --------- | ------ | ------------- | ------------------------------------------------------------------------------------------------- |
| `jd_text` | string | `min_length=1`, non-whitespace | Raw JD body as plain text or markdown.                                            |
| `source`  | string | non-empty     | One of `"upwork"`, `"onlinejobs_ph"`, `"linkedin_email"` (n8n flows) or `"browser"` (paste UI).   |

### Optional fields

| Field           | Type   | Description                                                                                       |
| --------------- | ------ | ------------------------------------------------------------------------------------------------- |
| `url`           | string | Canonical job-posting URL or the email's job-link URL. Surfaced to `metadata.url`.                |
| `discovered_at` | string | ISO-8601 UTC fetch timestamp set by the n8n flow. Surfaced to `metadata.discovered_at`.           |
| `source_board`  | string | Optional override consumed by `board_classifier` when set (Story 2.4).                            |
| `metadata`      | object | Free-form per-channel context (e.g. `posting_id`). Not validated by the route.                    |

## Source-to-metadata mapping

The `source` body field maps to `metadata.json` as follows:

| Body `source`         | `metadata.jd_source` |
| --------------------- | -------------------- |
| `"browser"`           | `"paste"`            |
| `"upwork"`            | `"upwork"`           |
| `"onlinejobs_ph"`     | `"onlinejobs_ph"`    |
| `"linkedin_email"`    | `"linkedin_email"`   |

The `browser -> paste` mapping is intentional — `"paste"` predates Epic 7 and is preserved on the browser path so the existing dashboard / stats aggregations keep their key.

## Response

`200 OK` with the standard paste response shape (see `PasteResponse` in `src/jobhunter/web/api.py`).

## Error responses

| Status | Cause                                                                | Body (`detail` key)                                |
| ------ | -------------------------------------------------------------------- | -------------------------------------------------- |
| 401    | Non-loopback caller missing / wrong `Authorization` header.          | `missing_ingest_token` / `invalid_ingest_token`.   |
| 401    | Non-loopback caller and server has no `INGEST_TOKEN` configured.     | `ingest_token_not_configured_on_server`.           |
| 422    | Pydantic body validation failed (missing `jd_text` / `source`).      | Pydantic's standard validation-error payload.      |
| 400    | `jd_text` was empty / whitespace-only after Pydantic.                | `jd_text is empty or whitespace-only`.             |
| 402    | Monthly LLM spend cap reached (NFR15).                               | `{"error": "monthly_spend_cap_reached", ...}`.     |
| 502    | LLM call failed or returned an unusable response.                    | `LLM call failed: ...` / `LLM response was ...`.   |

The Story 7.1 spec text calls for a 400 on a malformed payload; Pydantic returns 422 for missing top-level fields. Both are surface-level "machine-readable error key" responses per AC2 wording — the relevant signal is the structured `detail` key, not the exact 4xx code.

## Example: browser paste UI (loopback, no token)

```bash
curl -X POST http://127.0.0.1:8000/api/paste \
  -H 'Content-Type: application/json' \
  -d '{"jd_text": "Senior Python role...", "source": "browser"}'
```

## Example: n8n flow (non-loopback, bearer token)

```bash
curl -X POST "${INGEST_BASE_URL}/api/paste" \
  -H "Authorization: Bearer ${INGEST_SHARED_TOKEN}" \
  -H 'Content-Type: application/json' \
  -d '{
    "jd_text": "Senior Python role...",
    "source": "upwork",
    "url": "https://www.upwork.com/jobs/~01abcdef",
    "discovered_at": "2026-05-24T10:15:00Z"
  }'
```

## FR11 — no platform login allowed

FR11 forbids logging into the user's Upwork, OnlineJobs.ph, or LinkedIn account on the user's behalf. Every n8n flow in Epic 7 MUST:

- contain no credentials, OAuth tokens, or session cookies for Upwork, LinkedIn, or OnlineJobs.ph,
- use no browser-automation node (Puppeteer, Selenium, headless Chromium) against any of those three sites,
- restrict LinkedIn ingest to email parsing only — never a site fetch against `linkedin.com`.

The reference auth-test flow at `n8n/auth-test.json` carries this rule verbatim in its top-of-file `notes` field. Channel flows (Stories 7.2, 7.3, 7.4) copy that note block.

## Hosting agnosticism

The reference flow uses only `HTTP Request`, `Cron` (or manual trigger), and standard transform nodes. No `Execute Command` node, no filesystem-only nodes. The same JSON imports cleanly into self-hosted n8n and n8n cloud after setting two environment variables:

- `INGEST_BASE_URL` — base URL of the Job Hunter pipeline (e.g. `https://jobhunter.example.com`).
- `INGEST_SHARED_TOKEN` — value of the `.env` `INGEST_TOKEN` on the server.

---

## Scan engine endpoints (F2)

The external scan engine (n8n on Railway, `deploy/n8n/Dockerfile`) calls three
additional endpoints under the **same** `Authorization: Bearer ${INGEST_SHARED_TOKEN}`
contract:

| Method | Path | Auth required | Purpose |
|--------|------|---------------|---------|
| GET | `/api/scan/settings` | no (public) | Fetch `search_titles`, `sites_enabled`, `picks_per_site`, `enabled` |
| GET | `/api/scan/known-urls` | yes — Bearer | Fetch already-seen URLs (dedup skip-list) |
| GET | `/api/canonical-profile` | yes — Bearer | Fetch condensed CV profile for Claude's fit ranking |
| POST | `/api/scan/results` | yes — Bearer | Deliver `{site_summary, candidates[]}` from a completed scan |

The engine sends `INGEST_SHARED_TOKEN` (equal to the app's `INGEST_TOKEN`) on all
calls for consistency; `/api/scan/settings` is currently unguarded and will
accept the request regardless.

**`POST /api/scan/results` body shape** (matches `ResultsRequest` /
`CandidatePayload` in `src/jobhunter/web/routes/scan.py`):

```json
{
  "started_at": "2026-06-27T00:00:00Z",
  "finished_at": "2026-06-27T00:05:00Z",
  "status": "completed",
  "site_summary": {
    "indeed": {"status": "ok", "count": 3},
    "linkedin": {"status": "blocked", "count": 0}
  },
  "candidates": [
    {
      "site": "indeed",
      "url": "https://example.com/job/123",
      "title": "Solutions Designer",
      "company": "Acme Corp",
      "location": "Remote",
      "jd_text": "Full job description text...",
      "fit_reason": "Matches mobile + solutions design background.",
      "fit_score": 0.87
    }
  ]
}
```

**Response:** `{"scan_id": "<uuid>", "received": 3, "new": 2, "skipped": 1}`

For the full deployment runbook, image specification, and workflow node design,
see `docs/deployment/n8n-scan-engine.md`.  
For the design rationale and data model, see
`docs/superpowers/specs/2026-06-26-job-scan-design.md`.
