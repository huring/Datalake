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
# ResMed myAir — daily at 11:00
0 11 * * * python3 /scripts/resmed_sync.py

# Pocketcasts — every 2 hours
0 */2 * * * python3 /scripts/pocketcasts_sync.py
```

Standard cron syntax. All output goes to stdout and is visible via `docker logs datalake-jobs`.

## docker-compose.yml

Add the service to the existing datalake `docker-compose.yml`:

```yaml
datalake-jobs:
  image: ghcr.io/${GHCR_OWNER}/datalake-jobs:latest
  container_name: datalake-jobs
  restart: unless-stopped
  depends_on:
    - datalake-api
  labels:
    - "com.centurylinklabs.watchtower.enable=true"
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
| `MYAIR_EMAIL` | email |
| `MYAIR_PASSWORD` | password |
| `MYAIR_API_URL` | api_url |
| `POCKETCASTS_EMAIL` | email |
| `POCKETCASTS_PASSWORD` | password |

`API_TOKEN`, `DATALAKE_URL` are already set in the stack.

## Build and deploy

The jobs image is built by the GitHub Actions deploy workflow and pushed to `ghcr.io/${GHCR_OWNER}/datalake-jobs:latest` on every push to `main`.

The `datalake-jobs` service in `docker-compose.yml` points at that registry image, and Watchtower will pick up new pushes automatically when the container updates.

To deploy after changes, redeploy the stack in Portainer so it pulls the latest image and applies any new environment variables.

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
