# ResMed myAir Integration

A daily sync script that pulls the previous night's CPAP session data from the ResMed myAir cloud API and stores it in the datalake as a `health.sleep` event.

Runs as part of the `datalake-jobs` container — see [`docs/features/datalake-jobs/feature.md`](../datalake-jobs/feature.md) for the container setup.

## What it sends

- `source`: `resmed_myair`
- `event_type`: `health.sleep`
- `timestamp`: session start time in ISO 8601 format
- `payload`: CPAP session metrics

Payload fields:

- `duration_hours` — total time mask was on
- `ahi` — apnea-hypopnea index (events per hour, lower is better)
- `mask_leak_lpm` — average mask leak rate (litres per minute)
- `mask_on_count` — number of times mask was put on during the night
- `sleep_score` — myAir score (0–100) if available

## Implementation

### File location

```
jobs/scripts/resmed_sync.py
```

### Dependencies

Add to `jobs/requirements.txt`:
```
requests
```

### Auth flow

The myAir API is not officially documented but has been reverse-engineered by the community. Check recent GitHub projects (search `myair api python` or `resmed myair reverse engineer`) for current working endpoints — the API has changed over time and endpoint paths may need to be verified.

API base URL (EU): `https://api.myair.resmed.eu`

General auth pattern:
```
POST {MYAIR_API_URL}/account/login
Content-Type: application/json

{"email": "...", "password": "...", "grant_type": "password"}
```

Returns a bearer token used for all subsequent requests.

Sleep session endpoint pattern (verify against current community docs):
```
GET {MYAIR_API_URL}/v2/records
Authorization: Bearer {token}
```

### Datalake URL

Inside the datalake stack, reach the API via the internal Docker network:

```
http://datalake-api:8000
```

### Deduplication

Before posting, check whether a record for that night already exists:

```
GET {DATALAKE_URL}/events?source=resmed_myair&event_type=health.sleep&timestamp_from=<start_of_day>&timestamp_to=<end_of_day>
```

Skip the insert if `total > 0`. This makes the script safe to run multiple times.

### Environment variables

`MYAIR_EMAIL`, `MYAIR_PASSWORD`, `MYAIR_API_URL`, `DATALAKE_URL`, and `DATALAKE_TOKEN` — all defined in the datalake Portainer stack. See [`docs/features/datalake-jobs/feature.md`](../datalake-jobs/feature.md) for the full list.

### Cron schedule

Add to `jobs/crontab`:
```
0 8 * * * python3 /scripts/resmed_sync.py
```

Runs once daily at 08:00 — data from the previous night is typically available by then.

### Exit behaviour

- Exit 0 — event inserted successfully
- Exit 0 — record already exists for today (skipped)
- Exit 1 — API error or unexpected failure (logged to stdout)

## Example event

```json
{
  "source": "resmed_myair",
  "event_type": "health.sleep",
  "timestamp": "2026-05-07T23:14:00+02:00",
  "payload": {
    "duration_hours": 7.2,
    "ahi": 2.8,
    "mask_leak_lpm": 6.4,
    "mask_on_count": 1,
    "sleep_score": 84
  }
}
```
