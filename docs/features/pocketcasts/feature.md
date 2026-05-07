# Pocketcasts Integration

A scheduled sync script that pulls recent podcast listening history from the Pocketcasts API and stores new episodes in the datalake as `media.podcast` events.

## What it sends

- `source`: `pocketcasts`
- `event_type`: `media.podcast`
- `timestamp`: episode publish date in ISO 8601 format
- `payload`: episode and listening metadata

Payload fields:

- `podcast` — podcast name
- `title` — episode title
- `duration_seconds` — total episode duration
- `listened_seconds` — how far through the episode was listened
- `completed` — true if `listened_seconds >= duration_seconds * 0.9`

## Implementation

A standalone Python script that runs as a cron job. No container needed — runs directly on docker-main.

### File location

```
/opt/integrations/pocketcasts_sync.py
```

### Dependencies

- `requests` (install via pip if not present)

### Auth flow

The Pocketcasts API is unofficial but stable and widely used by the community.

```
POST https://api.pocketcasts.com/user/login
Content-Type: application/json

{"email": "...", "password": "..."}
```

Returns `{"token": "..."}`. Use this as a Bearer token for all subsequent requests.

### History endpoint

```
GET https://api.pocketcasts.com/user/history
Authorization: Bearer {token}
```

Returns a list of recently played episodes. Each episode includes:
- `podcast` — podcast name
- `title` — episode title
- `duration` — total length in seconds
- `playedUpTo` — seconds listened
- `publishedAt` — ISO 8601 publish date

### Deduplication

The history endpoint always returns the same recent episodes regardless of when it's called. Before posting each episode, check whether it already exists in the datalake:

```
GET {DATALAKE_URL}/events?source=pocketcasts&event_type=media.podcast&timestamp_from=<start_of_publish_day>&timestamp_to=<end_of_publish_day>
```

Check the response for an event whose `payload.podcast` and `payload.title` match. Skip if found.

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `POCKETCASTS_EMAIL` | — | Pocketcasts account email |
| `POCKETCASTS_PASSWORD` | — | Pocketcasts account password |
| `DATALAKE_URL` | `http://docker.home:8000` | Datalake API base URL |
| `DATALAKE_TOKEN` | `mytoken` | Datalake bearer token |

### Cron schedule

Run every two hours — Pocketcasts syncs from the app periodically so this catches episodes shortly after they're listened to:

```
0 */2 * * * python3 /opt/integrations/pocketcasts_sync.py >> /var/log/pocketcasts_sync.log 2>&1
```

### Exit behaviour

- Exit 0 — one or more new episodes inserted
- Exit 0 — no new episodes found (all already in datalake or nothing in history)
- Exit 1 — API error or unexpected failure (logged to stdout)

## Example event

```json
{
  "source": "pocketcasts",
  "event_type": "media.podcast",
  "timestamp": "2026-05-07T06:00:00+02:00",
  "payload": {
    "podcast": "Huberman Lab",
    "title": "Tools for Managing Stress and Anxiety",
    "duration_seconds": 5640,
    "listened_seconds": 5640,
    "completed": true
  }
}
```
