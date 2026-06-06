# Deploy Job Hunter to AWS Lightsail (cost-efficient, always-on)

End state: `https://<your-domain>` serves the Job Hunter UI (behind basic-auth),
runs 24/7, and auto-updates whenever you push to `main` (Watchtower pulls the
new GHCR image). This is the cheap, reliable alternative to Oracle when its
Always-Free capacity is unavailable.

> **Why Lightsail over EC2/Fargate:** Lightsail bundles compute + SSD + static
> IP + data transfer into one **flat monthly price** with no surprise IPv4/EBS/
> data charges, and it's far simpler (built-in firewall, browser SSH, no VPC to
> wire). For a single always-on Docker box this is the cost-efficient AWS choice.

## 0. Cost & sizing

| Plan | RAM | Use it for |
|---|---|---|
| **$5/mo** | 1 GB / 2 vCPU / 40 GB SSD / 2 TB transfer | **Job Hunter alone** (+ a swap file) |
| **$10/mo** | 2 GB | Job Hunter **and** n8n on the same box |

First **3 months are free** (Lightsail free trial). The **static IP is free**
while attached to a running instance. Everything is x86 — matches our amd64 GHCR
image, no rebuild needed.

## 1. Create the instance

1. **Lightsail console → Create instance.**
2. **Region/AZ:** pick the one nearest you (e.g. `ap-southeast-1` Singapore).
3. **Platform:** Linux/Unix → **OS Only → Ubuntu 22.04 LTS**.
4. **Plan:** **$5** (1 GB) — or **$10** (2 GB) if you'll also run n8n here.
5. Name it `jobhunter`, **Create instance**.

## 2. Attach a static IP

**Networking → Create static IP →** attach it to the `jobhunter` instance.
(Free while attached. Note this IP — it's your server's public address.)

## 3. Open the firewall (one layer only — no OS firewall step)

On the instance → **Networking → IPv4 Firewall → Add rule**, twice:
- **HTTP** — TCP **80**
- **HTTPS** — TCP **443**

(SSH **22** is there by default.) Unlike Oracle, Lightsail's firewall is the only
layer — there is **no** `iptables` step to remember.

## 4. Install Docker

Click **Connect using SSH** (browser terminal), or `ssh ubuntu@<STATIC_IP>` with
the key from *Account → SSH keys*. Then:

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER && newgrp docker
docker run --rm hello-world      # sanity check
```

### (1 GB plan only) add swap so WeasyPrint PDF rendering has headroom
```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h                          # confirm 2.0Gi swap
```

## 5. Point a domain at the static IP

Free option — **DuckDNS**: create `yourname.duckdns.org`, set its IP to your
Lightsail **static IP**. (Or any registrar: an **A record** → the static IP.)
Verify: `dig +short yourname.duckdns.org` returns the static IP.

## 6. Deploy

```bash
git clone https://github.com/davecharm16/jobhunter.git && cd jobhunter
cp .env.example .env
nano .env
```
Set in `.env`:
```bash
LLM_API_KEY=sk-ant-...
MONTHLY_SPEND_CAP_USD=25.00
CADDY_SITE_ADDRESS=yourname.duckdns.org
CADDY_BASIC_AUTH_USER=dave
CADDY_BASIC_AUTH_HASH=          # fill from the next command
# INGEST_TOKEN stays unset — Caddy basic-auth is the boundary in this topology.
```
Generate the password hash and paste it into `CADDY_BASIC_AUTH_HASH`:
```bash
docker run --rm caddy caddy hash-password --plaintext 'your-strong-password'
```
Launch (the GHCR image is already public — no registry login needed):
```bash
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml logs -f app
```

The spend ledger, tailored packages, and TLS certs persist in Docker named
volumes on the instance SSD — nothing to create by hand.

## 7. Verify + wire n8n

- Open `https://yourname.duckdns.org` → enter your basic-auth creds → dashboard.
  (Caddy auto-fetches the Let's Encrypt cert; needs port 80 reachable, hence §3.)
- **n8n HTTP Request node:** URL `https://yourname.duckdns.org/api/paste`,
  Authentication **Basic Auth** with `CADDY_BASIC_AUTH_USER` / your password,
  body per `docs/n8n-contract.md`. No Bearer token in this topology.

## Continuous deployment

Same as everywhere: push to `main` → CI builds + pushes
`ghcr.io/davecharm16/jobhunter:main` → Watchtower on the instance auto-pulls and
recreates the container. See `docs/deployment/continuous-deployment.md`.

## Troubleshooting

- **Cert won't issue:** port 80 must be open in the Lightsail firewall (§3) and
  DNS must resolve to the static IP. Check `docker compose -f docker-compose.prod.yml logs app`.
- **502 from Caddy:** uvicorn hasn't started; check the same logs.
- **OOM / sluggish on 1 GB:** confirm the swap file from §4 is active (`free -h`);
  if you run n8n here too, move to the $10 (2 GB) plan.
- **Updates not landing:** `docker logs watchtower`.

## Teardown (stop billing)

Delete the instance **and** the static IP in the Lightsail console (an unattached
static IP bills ~$0.005/hr). That zeroes the cost.
