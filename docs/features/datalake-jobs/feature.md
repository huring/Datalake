# datalake-jobs Container

A lightweight container in the datalake stack that runs scheduled sync scripts. It replaces ad-hoc cron jobs on the host — keeping all datalake-related processes in one place, sharing credentials via the stack, and using the internal Docker network to reach the API.

## Structure

Add a `jobs/` directory alongside the existing `api/` and `mcp/` directories in the repo:

```
jobs/
├── Dockerfile
├── requirements.txt
├── crontab
└── scripts/
    ├── resmed_sync.py
    └── pocketcasts_sync.py
```

## Dockerfile

```dockerfile
FROM python:3.12-alpine

RUN pip install --no-cache-dir supercronic

WORKDIR /scripts
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY scripts/ .
COPY crontab /crontab

CMD ["supercronic", "/crontab"]
```

Use `supercronic` rather than standard cron — it is designed for containers, logs to stdout, and handles signals correctly.

## requirements.txt

```
requests
```

Add any additional dependencies here as new scripts are added.

## crontab

```
# ResMed myAir — daily at 08:00
0 8 * * * python3 /scripts/resmed_sync.py

# Pocketcasts — every 2 hours
0 */2 * * * python3 /scripts/pocketcasts_sync.py
```

Standard cron syntax. All output goes to stdout and is visible via `docker logs datalake-jobs`.

## docker-compose.yml

Add the service to the existing datalake `docker-compose.yml`:

```yaml
datalake-jobs:
  build: ./jobs
  container_name: datalake-jobs
  restart: unless-stopped
  depends_on:
    - datalake-api
  environment:
    - DATALAKE_URL=http://datalake-api:8000
    - DATALAKE_TOKEN=${API_TOKEN}
    - MYAIR_EMAIL=${MYAIR_EMAIL}
    - MYAIR_PASSWORD=${MYAIR_PASSWORD}
    - MYAIR_API_URL=${MYAIR_API_URL}
    - POCKETCASTS_EMAIL=${POCKETCASTS_EMAIL}
    - POCKETCASTS_PASSWORD=${POCKETCASTS_PASSWORD}
```

`DATALAKE_URL` uses the internal Docker network hostname `datalake-api` — no external traffic needed.

## Portainer stack environment variables

Add the following to the datalake stack in Portainer:

| Variable | Description |
|---|---|
| `MYAIR_EMAIL` | ResMed myAir account email |
| `MYAIR_PASSWORD` | ResMed myAir account password |
| `MYAIR_API_URL` | `https://api.myair.resmed.eu` (EU) or `https://api.myair.io` (US) |
| `POCKETCASTS_EMAIL` | Pocketcasts account email |
| `POCKETCASTS_PASSWORD` | Pocketcasts account password |

`API_TOKEN`, `DATALAKE_URL` are already set in the stack.

## Build and deploy

The image is built locally on docker-main — it does not go through ghcr.io or Watchtower. To deploy after changes:

```bash
# On docker-main
docker rm -f datalake-jobs
cd /path/to/datalake/repo
docker build -t datalake-jobs ./jobs
```

Then redeploy the stack in Portainer.

## Adding a new script

1. Add the script to `jobs/scripts/`
2. Add its cron line to `jobs/crontab`
3. Add any new dependencies to `jobs/requirements.txt`
4. Rebuild and redeploy as above

## Logs

```bash
docker logs datalake-jobs
docker logs datalake-jobs --follow
```

All script output (successes, skips, errors) goes to stdout.
