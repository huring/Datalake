# Pocketcasts Integration

A scheduled sync script that pulls recent podcast listening history from the Pocketcasts API and stores new episodes in the datalake as `media.podcast` events.

Runs as part of the `datalake-jobs` container — see [`docs/features/datalake-jobs/feature.md`](../datalake-jobs/feature.md) for the container setup.

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

### File location

```
jobs/scripts/pocketcasts_sync.py
```

### Dependencies

Add to `jobs/requirements.txt`:
```
requests
```

### Auth flow

The Pocketcasts API is unofficial but stable and widely used by the community.

```
POST https://api.pocketcasts.com/user/login
Content-Type: application/json

{"email": "...", "password": "..."}
```

Returns `{"token": "..."}`. Use as a Bearer token for all subsequent requests.

### History endpoint

```
POST https://api.pocketcasts.com/user/history
Authorization: Bearer {token}
```

Returns a list of recently played episodes. Each episode includes:
- `podcast` — podcast name
- `title` — episode title
- `duration` — total length in seconds
- `playedUpTo` — seconds listened
- `publishedAt` — ISO 8601 publish date

### Datalake URL

Inside the datalake stack, reach the API via the internal Docker network:

```
http://datalake-api:8000
```

### Deduplication

The history endpoint always returns the same recent episodes regardless of when it's called. Before posting each episode, check whether it already exists:

```
GET {DATALAKE_URL}/events?source=pocketcasts&event_type=media.podcast&timestamp_from=<start_of_publish_day>&timestamp_to=<end_of_publish_day>
```

Check the response for an event whose `payload.podcast` and `payload.title` match. Skip if found.

### Environment variables

`POCKETCASTS_EMAIL`, `POCKETCASTS_PASSWORD`, `DATALAKE_URL`, and `DATALAKE_TOKEN` — all defined in the datalake Portainer stack. See [`docs/features/datalake-jobs/feature.md`](../datalake-jobs/feature.md) for the full list.

### Cron schedule

Add to `jobs/crontab`:
```
0 */2 * * * python3 /scripts/pocketcasts_sync.py
```

Runs every two hours — Pocketcasts syncs from the app periodically so this catches episodes shortly after they're listened to.

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
