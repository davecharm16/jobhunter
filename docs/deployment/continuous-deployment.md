# Continuous deployment

## Flow

```
push to main
  → CI: backend tests + frontend build + docker build  (must pass)
  → CI publish job: build image, push ghcr.io/davecharm16/jobhunter:main (+:sha)
  → VM: Watchtower (polls every 5 min) sees the new :main digest
  → Watchtower pulls it and recreates the `jobhunter` container
```

You push code; ~5–10 minutes later the VM is running it. No SSH needed.

## What survives an update

Updates recreate the **container**, never the **volumes**:

| State | Volume | Survives update |
|---|---|---|
| Tailored packages (`out/`) | `jobhunter-out` | ✅ |
| Spend ledger (`.cost-ledger.json`) | `jobhunter-ledger` | ✅ |
| TLS certificates | `caddy-data` | ✅ (avoids LE rate limits) |

Secrets come from `.env` on the VM (never baked into the image), so updates
don't touch them. Downtime per update is a few seconds while the container
restarts — fine for an n8n receiver (n8n retries).

## Manual deploy (fallback)

If you disable Watchtower or want to deploy immediately:

```bash
cd ~/jobhunter
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

## Rollback

Images are tagged by commit SHA. To pin a known-good build, set the app image in
`docker-compose.prod.yml` to `ghcr.io/davecharm16/jobhunter:<sha>` and
`docker compose -f docker-compose.prod.yml up -d`. Switch back to `:main` to
resume auto-updates.

## Updating your CV / config

`canonical-cv.json` and `config.yaml` are baked into the image. Edit them, commit,
push to `main` — CI rebuilds and Watchtower rolls it out like any code change.
