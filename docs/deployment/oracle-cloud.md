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
# INGEST_TOKEN stays unset — Caddy basic-auth is the boundary in this topology.
```

Generate the password hash and paste it into `CADDY_BASIC_AUTH_HASH`:

```bash
docker run --rm caddy caddy hash-password --plaintext 'your-strong-password'
```

The spend ledger and tailored packages persist in Docker named volumes
(`jobhunter-ledger`, `jobhunter-out`) — nothing to create by hand.

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
