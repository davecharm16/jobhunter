# Oracle Cloud Continuous Deployment + Public Access Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy Job Hunter to an Oracle Cloud Always-Free VM with a public HTTPS URL and push-to-`main` continuous deployment, so the n8n workflow stays up 24/7 without the user's Mac.

**Architecture:** Replace the two-container Caddy-sidecar with a **single all-in-one image** (Caddy + uvicorn supervised by `supervisord`): Caddy terminates TLS / does basic-auth on the public port and reverse-proxies to uvicorn on `127.0.0.1:8765`, so the app still only ever sees loopback traffic (its loopback-trust auth model is preserved, no source changes). CI builds this image and pushes it to GHCR on every `main` push; **Watchtower** on the VM watches GHCR and auto-recreates the container when a new image lands. A single image (vs. a sidecar sharing a network namespace) is what makes Watchtower's recreate-on-update safe — there is no cross-container netns link to break.

**Tech Stack:** Docker (multi-stage), Caddy 2 (auto-HTTPS via Let's Encrypt), supervisord, GitHub Actions, GitHub Container Registry (GHCR), Watchtower, Oracle Cloud Infrastructure (Always-Free VM), DuckDNS (or any domain).

---

## Why this topology (read before starting)

- **The app refuses non-loopback binds** (`src/jobhunter/cli.py:ensure_loopback`) and **only skips the ingest-token check for loopback clients** (`src/jobhunter/web/api.py:require_ingest_token`). If anything other than a loopback peer reaches uvicorn, the token-less browser SPA breaks.
- Putting **Caddy in the same process space as uvicorn** (one container, Caddy → `127.0.0.1:8765`) means uvicorn always sees a loopback peer. The single network-facing auth boundary becomes **Caddy basic-auth** (over HTTPS in prod). The app's `INGEST_TOKEN` is moot in this topology and stays unset.
- **n8n** authenticates to **Caddy basic-auth** (HTTP Basic on its Request node), POSTing to `https://<domain>/api/paste`. It does NOT use the Bearer token in this topology — Caddy is the boundary. (See `docs/n8n-contract.md` for the body shape, which is unchanged.)
- **State that must survive image updates** lives in Docker volumes: `out/` (tailored packages), `.cost-ledger.json` (monthly spend cap), and Caddy's `/data` (Let's Encrypt certs — persist this or you will hit LE rate limits on every redeploy).

## File Structure

| Path | Responsibility | Action |
|---|---|---|
| `Dockerfile` | All-in-one image: frontend build → python runtime + WeasyPrint libs → Caddy binary + supervisord; runs both processes | Modify |
| `docker/supervisord.conf` | Supervises `jobhunter` (uvicorn, user `app`) + `caddy` (user `root`, binds 80/443) | Create |
| `Caddyfile` | Parameterized site address (`{$CADDY_SITE_ADDRESS::8080}`), basic-auth, reverse-proxy to `127.0.0.1:8765`; baked into image | Modify |
| `docker-compose.yml` | LOCAL run: build image, publish `:8080`, volumes, basic-auth env | Modify (drop sidecar) |
| `docker-compose.prod.yml` | ORACLE run: pull GHCR image, publish `:80`+`:443`, domain TLS, persistent volumes, Watchtower | Create |
| `.github/workflows/ci.yml` | Add `publish` job: build + push image to GHCR on `main` | Modify |
| `docs/deployment/oracle-cloud.md` | VM provisioning → Docker → firewall (both layers) → DNS → secrets → deploy → access runbook | Create |
| `docs/deployment/continuous-deployment.md` | Push→build→GHCR→Watchtower flow, data persistence, rollback, manual fallback, n8n wiring | Create |
| `README.md` | Point the Docker section at the new cloud option | Modify |

---

## Task 1: All-in-one image (Caddy + uvicorn under supervisord)

**Files:**
- Create: `docker/supervisord.conf`
- Modify: `Caddyfile`
- Modify: `Dockerfile`

- [ ] **Step 1: Create the supervisord config**

Create `docker/supervisord.conf`:

```ini
[supervisord]
nodaemon=true
user=root
logfile=/dev/null
logfile_maxbytes=0
pidfile=/tmp/supervisord.pid

# uvicorn (FastAPI). Binds 127.0.0.1:8765 — the CLI refuses non-loopback by
# design. Runs as the unprivileged app user.
[program:jobhunter]
command=jobhunter --no-browser
user=app
environment=HOME="/home/app",JOBHUNTER_WEB_PORT="8765"
autorestart=true
startsecs=3
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0

# Caddy. Runs as root so it can bind 80/443 in prod. Reads the baked Caddyfile;
# cert/data storage goes to /data (mount a volume there to persist certs).
[program:caddy]
command=caddy run --config /etc/caddy/Caddyfile --adapter caddyfile
user=root
environment=XDG_DATA_HOME="/data",XDG_CONFIG_HOME="/config"
autorestart=true
startsecs=3
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0
```

- [ ] **Step 2: Parameterize the Caddyfile**

Replace the entire contents of `Caddyfile` with:

```caddyfile
# Single front door for Job Hunter. Baked into the image; configured by env.
#
# CADDY_SITE_ADDRESS controls the listener + TLS:
#   - ":8080"            -> plain HTTP on :8080 (local dev; Caddy issues no cert)
#   - "jobhunter.duckdns.org" -> public HTTPS on :443 via Let's Encrypt (prod)
# Caddy only provisions TLS for hostname site addresses, so the same file serves
# both modes — no `auto_https off` needed.
#
# Caddy reverse-proxies to uvicorn on loopback, so the app sees a loopback peer
# and its loopback-trust auth model holds. Basic-auth here is the only
# network-facing auth boundary.

{
	admin off
}

{$CADDY_SITE_ADDRESS::8080} {
	# Generate the hash with:
	#   docker run --rm caddy caddy hash-password --plaintext 'your-password'
	basic_auth {
		{$CADDY_BASIC_AUTH_USER} {$CADDY_BASIC_AUTH_HASH}
	}

	reverse_proxy 127.0.0.1:8765
}
```

- [ ] **Step 3: Modify the Dockerfile runtime stage to add Caddy + supervisor**

In `Dockerfile`, the runtime stage currently ends with a `USER app` line and `CMD ["jobhunter", "--no-browser"]`. Replace the apt-install block, the `useradd` block, and the final `ENV`/`EXPOSE`/`CMD` lines so the runtime stage reads as follows (keep the existing `WORKDIR /app`, the `COPY pyproject.toml ...`, `COPY src/ ...`, `COPY --from=frontend ...`, `RUN pip install ...`, and `COPY canonical-cv.json config.yaml ...` / `COPY schemas/ ...` lines exactly as they are between the apt block and the useradd block):

Apt block — add `supervisor` to the install list:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libharfbuzz0b \
        libgdk-pixbuf-2.0-0 \
        libcairo2 \
        libffi8 \
        shared-mime-info \
        fonts-dejavu-core \
        supervisor \
    && rm -rf /var/lib/apt/lists/*

# Caddy: copy the static binary from the official image (no apt repo needed).
COPY --from=caddy:2 /usr/bin/caddy /usr/bin/caddy
```

Replace the `useradd` block, `USER app`, `ENV`, `EXPOSE`, and `CMD` at the end of the file with:

```dockerfile
# Baked config: Caddyfile (front door) + supervisord (process manager).
COPY Caddyfile /etc/caddy/Caddyfile
COPY docker/supervisord.conf /etc/supervisor/supervisord.conf

# Non-root app user for uvicorn; Caddy runs as root for 80/443 + cert storage.
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /app/out /data /config \
    && touch /app/.cost-ledger.json \
    && chown -R app:app /app

# Caddy listens here in prod (TLS) / :8080 in local. EXPOSE is documentation.
EXPOSE 8080 80 443

# supervisord (PID 1) runs uvicorn (loopback) + Caddy (public) together.
CMD ["supervisord", "-c", "/etc/supervisor/supervisord.conf"]
```

- [ ] **Step 4: Build the image**

Run: `docker build -t jobhunter:allinone .`
Expected: build completes (exit 0); final stage installs `supervisor` and copies the `caddy` binary.

- [ ] **Step 5: Smoke-test basic-auth + proxy end to end**

```bash
HASH=$(docker run --rm caddy caddy hash-password --plaintext 'testpass')
docker rm -f jh_t >/dev/null 2>&1
docker run -d --name jh_t -p 8088:8080 \
  -e CADDY_SITE_ADDRESS=:8080 \
  -e CADDY_BASIC_AUTH_USER=dave \
  -e CADDY_BASIC_AUTH_HASH="$HASH" \
  jobhunter:allinone
sleep 5
echo "--- no creds (expect 401) ---"
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8088/healthz
echo "--- with creds (expect 200 + ok json) ---"
curl -s -u dave:testpass http://127.0.0.1:8088/healthz
docker rm -f jh_t >/dev/null 2>&1
```

Expected: first curl prints `401`; second prints `{"status":"ok","version":"0.1.0"}`.

- [ ] **Step 6: Commit**

```bash
git add Dockerfile Caddyfile docker/supervisord.conf
git commit -m "feat(deploy): all-in-one Caddy+uvicorn image via supervisord"
```

---

## Task 2: Simplify the local docker-compose to the single image

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Replace docker-compose.yml**

The current file has two services (`app` + `caddy` sidecar with `network_mode: service:app`). Replace the entire file with the single all-in-one service:

```yaml
# LOCAL run of Job Hunter (production-like, single all-in-one image).
# For plain dev you can still run `jobhunter` from the venv on 127.0.0.1:8765
# with no Docker and no basic-auth. This stack mirrors the cloud topology.
#
# First-run:
#   cp .env.example .env            # fill LLM_API_KEY, MONTHLY_SPEND_CAP_USD
#   touch .cost-ledger.json         # so the bind mount is a file, not a dir
#   # add to .env (compose auto-loads .env for ${...}):
#   #   CADDY_BASIC_AUTH_USER=dave
#   #   CADDY_BASIC_AUTH_HASH=$(docker run --rm caddy caddy hash-password --plaintext 'secret')
#   docker compose up --build      # http://127.0.0.1:8080  (basic-auth)

services:
  app:
    build: .
    image: jobhunter:local
    container_name: jobhunter
    env_file: .env
    environment:
      CADDY_SITE_ADDRESS: ":8080"
      CADDY_BASIC_AUTH_USER: ${CADDY_BASIC_AUTH_USER:?set CADDY_BASIC_AUTH_USER in .env}
      CADDY_BASIC_AUTH_HASH: ${CADDY_BASIC_AUTH_HASH:?run: docker run --rm caddy caddy hash-password}
    ports:
      - "127.0.0.1:8080:8080"
    volumes:
      - ./canonical-cv.json:/app/canonical-cv.json:ro
      - ./config.yaml:/app/config.yaml:ro
      - ./.cost-ledger.json:/app/.cost-ledger.json
      - jobhunter-out:/app/out
    restart: unless-stopped

volumes:
  jobhunter-out:
```

- [ ] **Step 2: Validate compose config**

Run: `CADDY_BASIC_AUTH_USER=dave CADDY_BASIC_AUTH_HASH='x' docker compose config >/dev/null && echo OK`
Expected: prints `OK`.

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "refactor(deploy): single-service local compose for all-in-one image"
```

---

## Task 3: Production compose for Oracle (GHCR image + TLS + Watchtower)

**Files:**
- Create: `docker-compose.prod.yml`

- [ ] **Step 1: Create docker-compose.prod.yml**

```yaml
# ORACLE CLOUD (Always-Free VM) deployment. See docs/deployment/oracle-cloud.md.
#
# Runs the prebuilt GHCR image (no build on the VM — the Always-Free box has too
# little RAM to build the Vite/WeasyPrint image). Watchtower auto-pulls new
# images pushed by CI on `main`.
#
#   docker compose -f docker-compose.prod.yml pull
#   docker compose -f docker-compose.prod.yml up -d
#
# Required in .env on the VM:
#   LLM_API_KEY=...                 MONTHLY_SPEND_CAP_USD=25.00
#   CADDY_SITE_ADDRESS=jobhunter.example.com   # your domain (enables HTTPS)
#   CADDY_BASIC_AUTH_USER=dave
#   CADDY_BASIC_AUTH_HASH=$(docker run --rm caddy caddy hash-password --plaintext 'strong-secret')
#   ACME_EMAIL=you@example.com      # Let's Encrypt contact

services:
  app:
    image: ghcr.io/davecharm16/jobhunter:main
    container_name: jobhunter
    pull_policy: always
    env_file: .env
    environment:
      CADDY_SITE_ADDRESS: ${CADDY_SITE_ADDRESS:?set your domain in .env}
      CADDY_BASIC_AUTH_USER: ${CADDY_BASIC_AUTH_USER:?set in .env}
      CADDY_BASIC_AUTH_HASH: ${CADDY_BASIC_AUTH_HASH:?set in .env}
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - jobhunter-out:/app/out
      - jobhunter-ledger:/ledger
      - caddy-data:/data        # persist Let's Encrypt certs across updates
      - caddy-config:/config
    # Keep the spend ledger on a volume (image path is /app/.cost-ledger.json).
    # Symlink so the app's fixed path resolves onto the persistent volume.
    entrypoint:
      - /bin/sh
      - -c
      - 'ln -sf /ledger/.cost-ledger.json /app/.cost-ledger.json && touch /ledger/.cost-ledger.json && chown app:app /ledger/.cost-ledger.json && exec supervisord -c /etc/supervisor/supervisord.conf'
    restart: unless-stopped
    labels:
      com.centurylinklabs.watchtower.enable: "true"

  watchtower:
    image: containrrr/watchtower
    container_name: watchtower
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    command: --label-enable --cleanup --interval 300
    restart: unless-stopped

volumes:
  jobhunter-out:
  jobhunter-ledger:
  caddy-data:
  caddy-config:
```

- [ ] **Step 2: Validate prod compose config**

Run:
```bash
CADDY_SITE_ADDRESS=jobhunter.example.com CADDY_BASIC_AUTH_USER=dave CADDY_BASIC_AUTH_HASH='x' \
  docker compose -f docker-compose.prod.yml config >/dev/null && echo OK
```
Expected: prints `OK`.

- [ ] **Step 3: Commit**

```bash
git add docker-compose.prod.yml
git commit -m "feat(deploy): production compose (GHCR image, TLS, Watchtower)"
```

---

## Task 4: CI — build and push the image to GHCR on `main`

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Add a publish job**

In `.github/workflows/ci.yml`, append a new `publish` job after the existing `docker` job (keep all existing jobs unchanged). Add a top-level `permissions` block under the `concurrency` block as well.

Add directly under the `concurrency:` block (after line 11):

```yaml
# GHCR push needs package write; checkout needs read.
permissions:
  contents: read
  packages: write
```

Append this job at the end of the file (sibling of `backend`/`frontend`/`docker`):

```yaml
  publish:
    name: Publish image to GHCR
    runs-on: ubuntu-latest
    # Only on pushes to main (not PRs), and only after tests/build pass.
    needs: [backend, frontend, docker]
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4

      # Build the frontend into the source tree so package-data + the image's
      # COPY pick it up (same as the Docker build expects).
      - uses: docker/setup-buildx-action@v3

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and push
        uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: |
            ghcr.io/${{ github.repository }}:main
            ghcr.io/${{ github.repository }}:${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

- [ ] **Step 2: Validate the workflow YAML**

Run: `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml')); print('YAML OK')"`
Expected: prints `YAML OK`. (If `actionlint` is available, also run `actionlint .github/workflows/ci.yml` and expect no errors.)

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: publish all-in-one image to GHCR on main"
```

---

## Task 5: Oracle Cloud runbook

**Files:**
- Create: `docs/deployment/oracle-cloud.md`

- [ ] **Step 1: Write the runbook**

Create `docs/deployment/oracle-cloud.md`:

````markdown
# Deploy Job Hunter to Oracle Cloud (Always-Free) with a public HTTPS URL

End state: `https://<your-domain>` serves the Job Hunter UI (behind basic-auth),
runs 24/7 independent of your Mac, and auto-updates whenever you push to `main`.

> **Security:** this app runs on *your* Anthropic key and spend cap. The only
> network-facing auth is Caddy basic-auth over HTTPS. Use a strong password.
> Expose **only** Job Hunter — never expose n8n's admin UI publicly.

## 0. Cost

Oracle **Always Free** VMs are $0 forever; the card at signup is identity
verification only. Prefer an **Ampere A1 (Arm)** shape (1 OCPU / 6 GB is plenty);
if A1 is "out of capacity," retry or pick another availability domain. Avoid the
1 GB AMD micro — it is too small to run comfortably.

## 1. Provision the VM

1. Create an **Always Free** compute instance, image **Ubuntu 22.04**, shape
   **VM.Standard.A1.Flex** (1 OCPU, 6 GB).
2. Add your SSH public key. Note the **public IP**.
3. In the VCN **Security List** (or an NSG on the instance), add **ingress**
   rules: TCP `80` and TCP `443` from `0.0.0.0/0`.

## 2. Open the OS firewall (the step everyone forgets)

Oracle Ubuntu images ship with a default iptables REJECT. Opening the Security
List is **not enough** — open the host firewall too:

```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```

## 3. Install Docker

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
newgrp docker
```

## 4. Point a domain at the VM

Free option — **DuckDNS**: create `yourname.duckdns.org`, set its IP to the VM's
public IP. Or use any registrar and create an **A record** → the public IP.

Verify: `dig +short yourname.duckdns.org` returns the VM IP.

## 5. Get the deploy files + secrets onto the VM

```bash
git clone https://github.com/davecharm16/jobhunter.git
cd jobhunter
cp .env.example .env
```

Edit `.env`:

```bash
LLM_API_KEY=sk-ant-...
MONTHLY_SPEND_CAP_USD=25.00
CADDY_SITE_ADDRESS=yourname.duckdns.org
CADDY_BASIC_AUTH_USER=dave
CADDY_BASIC_AUTH_HASH=     # fill from the next command
ACME_EMAIL=you@example.com
# INGEST_TOKEN stays unset — Caddy basic-auth is the boundary in this topology.
```

Generate the password hash and paste it into `CADDY_BASIC_AUTH_HASH`:

```bash
docker run --rm caddy caddy hash-password --plaintext 'your-strong-password'
```

## 6. Make the GHCR image pullable

After your first push to `main` (CI builds + pushes the image), open the package
at `https://github.com/davecharm16?tab=packages`, select **jobhunter**, and set
its visibility to **Public**. (Public images need no registry login on the VM.)

## 7. Deploy

```bash
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml logs -f app
```

Caddy fetches a Let's Encrypt cert automatically (needs port 80 reachable —
that's what steps 1–2 enabled). Open `https://yourname.duckdns.org`, enter your
basic-auth credentials, and you should see the dashboard.

## 8. Point n8n at it

In your n8n HTTP Request node:
- URL: `https://yourname.duckdns.org/api/paste`
- Authentication: **Basic Auth** with `CADDY_BASIC_AUTH_USER` / your password.
- Body: the JSON from `docs/n8n-contract.md` (`jd_text`, `source`, ...).

No Bearer token is needed in this topology — Caddy basic-auth is the boundary,
and the app sees Caddy as a loopback peer.

## Troubleshooting

- **Cert won't issue:** port 80 must be reachable from the internet (Security
  List **and** iptables). Check `docker compose -f docker-compose.prod.yml logs app`.
- **502 from Caddy:** uvicorn hasn't started; check the same logs for the
  `jobhunter` program.
- **Updates not landing:** confirm the GHCR package is Public and Watchtower is
  running: `docker logs watchtower`.
````

- [ ] **Step 2: Commit**

```bash
git add docs/deployment/oracle-cloud.md
git commit -m "docs(deploy): Oracle Cloud always-free runbook"
```

---

## Task 6: Continuous-deployment doc

**Files:**
- Create: `docs/deployment/continuous-deployment.md`

- [ ] **Step 1: Write the CD doc**

Create `docs/deployment/continuous-deployment.md`:

````markdown
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
````

- [ ] **Step 2: Commit**

```bash
git add docs/deployment/continuous-deployment.md
git commit -m "docs(deploy): continuous deployment + rollback guide"
```

---

## Task 7: Update README pointers

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update the "Self-host with Docker" section heading + intro**

In `README.md`, find the line:

```markdown
## Self-host with Docker (private)
```

Replace that heading and the blockquote/paragraph immediately under it (down to but not including the ```` ```bash ```` first-run block) with:

```markdown
## Deploy

Two supported targets, both using the single all-in-one image (Caddy + uvicorn):

- **Local / private** (this section) — `docker compose up`, reachable at
  `http://127.0.0.1:8080` behind basic-auth. Good behind Tailscale/VPN.
- **Oracle Cloud (always-free, public HTTPS, 24/7, push-to-deploy)** — see
  [`docs/deployment/oracle-cloud.md`](./docs/deployment/oracle-cloud.md) and
  [`docs/deployment/continuous-deployment.md`](./docs/deployment/continuous-deployment.md).

> ⚠️ Job Hunter runs on *your* LLM key + spend cap and trusts whoever clears
> Caddy basic-auth. Use a strong password; never expose n8n's admin UI publicly.
```

- [ ] **Step 2: Verify the first-run block below still matches the new local compose**

The existing local first-run `bash` block references `docker compose up --build` and `.cost-ledger.json` — confirm it still reads correctly against the Task 2 `docker-compose.yml` (single `app` service, `:8080`). Adjust the prose only if it still mentions the old `caddy` sidecar.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: point deploy section at local + Oracle Cloud targets"
```

---

## Task 8: Final integration verification

**Files:** none (verification only)

- [ ] **Step 1: Rebuild the image clean and re-run the auth smoke test**

```bash
docker build -t jobhunter:final .
HASH=$(docker run --rm caddy caddy hash-password --plaintext 'testpass')
docker rm -f jh_f >/dev/null 2>&1
docker run -d --name jh_f -p 8089:8080 \
  -e CADDY_SITE_ADDRESS=:8080 -e CADDY_BASIC_AUTH_USER=dave -e CADDY_BASIC_AUTH_HASH="$HASH" \
  jobhunter:final
sleep 5
curl -s -o /dev/null -w "no-creds: %{http_code}\n" http://127.0.0.1:8089/
curl -s -u dave:testpass -o /dev/null -w "creds /: %{http_code}\n" http://127.0.0.1:8089/
curl -s -u dave:testpass http://127.0.0.1:8089/healthz; echo
docker rm -f jh_f >/dev/null 2>&1
```

Expected: `no-creds: 401`, `creds /: 200`, and `{"status":"ok","version":"0.1.0"}`.

- [ ] **Step 2: Validate both compose files**

```bash
CADDY_BASIC_AUTH_USER=d CADDY_BASIC_AUTH_HASH=x docker compose config >/dev/null && echo "local OK"
CADDY_SITE_ADDRESS=ex.com CADDY_BASIC_AUTH_USER=d CADDY_BASIC_AUTH_HASH=x \
  docker compose -f docker-compose.prod.yml config >/dev/null && echo "prod OK"
```

Expected: `local OK` and `prod OK`.

- [ ] **Step 3: Confirm the existing test suite is unaffected**

Run: `.venv/bin/python -m pytest -q` (with `.env` present this has 12 known local-only failures; the count must not increase).
Expected: no NEW failures beyond the documented 12 env-driven ones.

- [ ] **Step 4: Clean up test images**

```bash
docker rmi jobhunter:allinone jobhunter:final 2>/dev/null || true
```

---

## Self-Review (completed by plan author)

**Spec coverage:**
- GHCR build+push on main → Task 4 ✅
- Auto-deploy (Watchtower chosen over SSH) → Task 3 + Task 6 ✅
- Single-container Caddy (folded in) → Task 1 ✅
- Public URL + domain + TLS → Task 1 (parameterized Caddyfile) + Task 3 (80/443) + Task 5 (DNS/firewall) ✅
- "Will updating main break Oracle?" answered → Task 6 (data-survival table, rollback) ✅
- n8n connectivity preserved → Task 5 step 8 + topology note ✅

**Placeholder scan:** none — every file has complete contents; every verify step has exact commands + expected output.

**Type/name consistency:** image ref `ghcr.io/davecharm16/jobhunter:main` is identical in Task 3, 4, 5, 6. Env var names (`CADDY_SITE_ADDRESS`, `CADDY_BASIC_AUTH_USER`, `CADDY_BASIC_AUTH_HASH`, `ACME_EMAIL`) are consistent across Caddyfile, both compose files, and the runbook. uvicorn port `8765` and Caddy default `:8080` are consistent across `supervisord.conf`, `Caddyfile`, and compose.

**Known risk flagged for the executor:** `ACME_EMAIL` is set in `.env` but the Caddyfile above does not wire it into a global `email` directive. If Let's Encrypt requires a contact, add `email {$ACME_EMAIL}` to the Caddyfile global options block during Task 1 (it is currently omitted because Caddy issues certs without a contact email by default). Decide during Task 1.
````
