# Deploying PsiDataViz on a public VPS

PsiDataViz ships as a small Docker stack: the v2 app — React UI + FastAPI JSON API in one container (uvicorn) behind
[Caddy](https://caddyserver.com/), which terminates TLS and obtains a free Let's Encrypt
certificate automatically.

## Prerequisites

- A VPS (any provider) running Docker + the Compose plugin.
- A domain name with a DNS **A record** pointing at the VPS's public IP.
- Ports **80** and **443** open in the firewall.

## Steps

```bash
git clone <your-fork-of-psidata> && cd psidata

# Tell Caddy which hostname to get a certificate for:
export PSIDATA_DOMAIN=psidata.example.org
# Optional: raise the GitHub API rate limit (60/hr -> 5000/hr):
export GITHUB_TOKEN=ghp_xxx          # a read-only, public-repo token is enough

docker compose up -d --build
```

Visit `https://psidata.example.org`. Caddy provisions and renews the certificate with no further
configuration.

## Operations

```bash
docker compose logs -f app      # application logs
docker compose pull && docker compose up -d --build   # update
docker compose down             # stop
```

- **Cache:** fetched files and repo listings are cached in the `psidata-cache` volume. Remove it
  (`docker volume rm psidata_psidata-cache`) to force a cold re-fetch.
- **Scaling:** increase uvicorn `--workers` in the `Dockerfile` `CMD` for more
  concurrency; the app is stateless, so you can also run multiple replicas behind Caddy.

## Local smoke test (no domain needed)

```bash
docker compose up --build      # PSIDATA_DOMAIN defaults to localhost
# open http://localhost  (Caddy serves a local self-signed cert on https)
```

Or run just the app container directly:

```bash
docker build -t psidataviz:v2 .
docker run --rm -p 8000:8000 psidataviz:v2
# open http://localhost:8000
```
