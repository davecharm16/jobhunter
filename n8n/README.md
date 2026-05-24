# n8n flows (Epic 7)

Reference n8n flow JSONs for the Job Hunter channel adapters. Every flow posts JDs to the core pipeline via `POST /api/paste` using the shared-secret bearer-token contract documented in `../docs/n8n-contract.md`.

## Flows

| File                | Story | Trigger        | Purpose                                                        |
| ------------------- | ----- | -------------- | -------------------------------------------------------------- |
| `auth-test.json`    | 7.1   | Manual         | Smoke-test auth + body contract. Reference for Stories 7.2-7.4.|

## Environment variables

Every flow expects two workflow-level n8n environment variables:

- `INGEST_BASE_URL` — base URL of the Job Hunter pipeline (e.g. `https://jobhunter.example.com`). No trailing slash.
- `INGEST_SHARED_TOKEN` — value of the server's `.env` `INGEST_TOKEN` (the runtime config loader reads it under the `INGEST_TOKEN` key; see `../docs/n8n-contract.md`).

Tokens never appear in the committed flow JSON — they are referenced as `{{$env.INGEST_SHARED_TOKEN}}` and injected by the n8n runtime.

## FR11 — no platform login

Every flow in this folder carries an FR11 statement in its workflow-level `notes` field. The rule:

- no credentials, OAuth tokens, or session cookies for Upwork, LinkedIn, or OnlineJobs.ph,
- no browser-automation node against any of those sites,
- LinkedIn ingest is email-parse only.

## Hosting agnosticism

Flows use only `HTTP Request`, `Cron` / Manual Trigger, `Function`, and standard transform nodes — no `Execute Command`, no filesystem-only nodes. The same JSON imports cleanly into self-hosted n8n and n8n cloud.
