# Deploy Job Hunter to AWS EC2 (app only; n8n stays on Railway)

End state: `https://<your-domain>` serves the Job Hunter UI (behind Caddy
basic-auth + Let's Encrypt HTTPS), runs 24/7, and auto-updates on every push to
`main` (Watchtower pulls the new GHCR image). **n8n stays on Railway** and calls
this app over HTTPS.

> **Why EC2 here:** generic AWS / Activate credits always cover EC2 (Lightsail is
> sometimes excluded). It's a normal VM, so the same `docker-compose.prod.yml`
> runs unchanged. The image is **multi-arch**, so you can use cheaper **ARM
> (`t4g`)** instances.

## 0. Cost & sizing (app only — it's light; no browser here)

| Instance | RAM | ~Monthly (on-demand) | Notes |
|---|---|---|---|
| **`t4g.small`** | 2 GB | ~$12 instance + ~$3.6 IPv4 + ~$2.4 EBS ≈ **$18/mo** | **recommended**, comfortable |
| `t3.micro` | 1 GB | free 12 mo (new acct) + ~$3.6 IPv4 | cheapest; add swap |

A **$100 credit** covers `t4g.small` for ~5 months. Billing is itemized:
**instance-hours + EBS + public IPv4 + egress**. (AWS bills ~$0.005/hr ≈ $3.6/mo
for a public IPv4 even when attached — covered by credit.)

## 1. Launch the instance

1. **EC2 → Launch instance** → name `jobhunter`.
2. **AMI:** Ubuntu 22.04 LTS. **Architecture: Arm (64-bit)** if using `t4g`.
3. **Instance type:** `t4g.small` (or `t3.micro` for free tier — pick x86 AMI then).
4. **Key pair:** create/select one (for SSH).
5. **Storage:** gp3, 30 GB.
6. Launch.

## 2. Security Group (inbound rules)

Edit the instance's Security Group → **Inbound rules**:
- TCP **22** — source **My IP** (SSH; don't open 22 to the world).
- TCP **80** — source `0.0.0.0/0` (HTTP + Let's Encrypt challenge).
- TCP **443** — source `0.0.0.0/0` (HTTPS).

## 3. (Recommended) Elastic IP

**EC2 → Elastic IPs → Allocate** → **Associate** with the instance. Gives a
stable public IP that survives stop/start. (Release it at teardown or it bills.)

## 4. Install Docker

`ssh -i your-key.pem ubuntu@<PUBLIC_IP>`, then:

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER && newgrp docker
docker run --rm hello-world      # sanity check
```

### (1 GB `t3.micro` only) add swap so PDF rendering has headroom
```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

## 5. Point a domain at the IP

Free — **DuckDNS**: create `yourname.duckdns.org`, set its IP to the EC2
Elastic IP. Verify: `dig +short yourname.duckdns.org` returns that IP.

## 6. Make the GHCR image public

After the `main` build, GitHub → `davecharm16?tab=packages` → **jobhunter** →
visibility **Public** (so the VM pulls with no login). The image is multi-arch,
so it runs on `t4g` (arm64) or `t3` (amd64) automatically.

## 7. Deploy

```bash
git clone https://github.com/davecharm16/jobhunter.git && cd jobhunter
cp .env.example .env
nano .env
```

Set in `.env`:
```bash
LLM_API_KEY=sk-ant-...
MONTHLY_SPEND_CAP_USD=25.00
SUPABASE_DB_URL=postgresql://...            # same Supabase as tracker + scan tables
CADDY_SITE_ADDRESS=yourname.duckdns.org     # hostname => HTTPS via Let's Encrypt
CADDY_BASIC_AUTH_USER=dave
CADDY_BASIC_AUTH_HASH=                       # fill from the next command
GCHAT_WEBHOOK_URL=                           # optional
N8N_SCAN_TRIGGER_URL=                        # fill in §8 (the n8n webhook URL)
```
Generate the password hash → paste into `CADDY_BASIC_AUTH_HASH`:
```bash
docker run --rm caddy caddy hash-password --plaintext 'your-strong-password'
```
Launch:
```bash
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml logs -f app
```
Open `https://yourname.duckdns.org` → basic-auth → dashboard. ✅ That URL is your
**`APP_BASE_URL`**. (Packages, cost ledger, and TLS certs persist in Docker
named volumes on the EBS disk.)

## 8. Wire n8n (on Railway) to this app

- On the **Railway n8n service**, set `APP_BASE_URL=https://yourname.duckdns.org`.
- ⚠️ This topology gates everything behind **Caddy basic-auth**, and the app sees
  Caddy as a loopback peer (so its own token check is bypassed). The scan
  workflow's HTTP nodes therefore must authenticate with **Basic Auth**
  (`CADDY_BASIC_AUTH_USER` / your password), **not** the Bearer token. Update the
  4 HTTP nodes (Get Settings, Get Known URLs, Get Canonical Profile, Post
  Results) to Basic Auth.
- Copy the workflow's **Manual Run Webhook** URL → set `N8N_SCAN_TRIGGER_URL` to
  it in this app's `.env` → `docker compose -f docker-compose.prod.yml up -d`.

## Continuous deployment

Push to `main` → CI builds + pushes the multi-arch `ghcr.io/davecharm16/jobhunter:main`
→ Watchtower on the instance auto-pulls and recreates the container.

## Billing control

- AWS **Budgets** → small monthly budget + alert.
- Watch three line items: **instance-hours, EBS, public IPv4**.

## Teardown (stop billing)

**Terminate the instance** *and* **release the Elastic IP** (an unassociated EIP
bills ~$0.005/hr). That zeroes the cost.

## Troubleshooting

- **Cert won't issue:** port 80 must be open in the Security Group and DNS must
  resolve to the Elastic IP. Check `docker compose -f docker-compose.prod.yml logs app`.
- **502 from Caddy:** uvicorn hasn't started; check the same logs.
- **OOM on 1 GB:** confirm swap is active (`free -h`); prefer `t4g.small` (2 GB).
- **Updates not landing:** `docker logs watchtower`.
