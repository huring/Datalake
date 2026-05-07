# Homelab Data Lake

Small homelab event store with an API, MCP bridge, and Docker Compose deployment.

## Runtime

- API: `http://docker.home:8000`
- MCP SSE: `http://docker.home:8001/sse`
- Jobs container: `datalake-jobs` in the same stack

## Environment

Set these in your stack or `.env` file:

- `API_TOKEN`
- `MCP_API_TOKEN`
- `API_PORT` default `8000`
- `MCP_PORT` default `8001`
- `DATABASE_URL` default `sqlite:////data/datalake.db`
- `LOG_LEVEL` default `info`
- `MYAIR_EMAIL`
- `MYAIR_PASSWORD`
- `MYAIR_API_URL` default `https://api.myair.resmed.eu`
- `POCKETCASTS_EMAIL`
- `POCKETCASTS_PASSWORD`

For the current deployment, `API_TOKEN` and `MCP_API_TOKEN` should usually be the same value.
The jobs container uses `API_TOKEN` as its `DATALAKE_TOKEN` for API writes.

## Deploy

```bash
docker compose pull
docker compose up -d
```

If you use Portainer, redeploy the stack after changing env vars so the containers pick up the new values.

## Backup

The SQLite database lives in the `datalake-data` volume at `/data/datalake.db`.

To back up the volume:

```bash
docker run --rm -v datalake-data:/data -v "$(pwd)":/backup alpine tar czf /backup/datalake-backup.tar.gz /data
```

## API docs

See [docs/api-reference.md](docs/api-reference.md) for the current route list and request/response shapes.
