# ResMed myAir Integration (v2 — Okta/GraphQL)

Replaces `docs/features/resmed-myair/feature.md`. The original doc assumed a simple username/password POST login — this is incorrect. The myAir API uses **OAuth 2.0 with PKCE** via Okta for auth, and **GraphQL** for sleep data.

Reference implementation: https://github.com/prestomation/resmed_myair_sensors — use this as the primary source for auth and GraphQL code. The Python implementation in that repo is working and can be used directly.

Runs as part of the `datalake-jobs` container. See [`docs/features/datalake-jobs/feature.md`](../datalake-jobs/feature.md) for container setup.

---

## What it sends

- `source`: `resmed_myair`
- `event_type`: `health.sleep`
- `timestamp`: session `startDate` in ISO 8601 format
- `payload`: CPAP session metrics

Payload fields (from GraphQL response):

| Field | Source field | Notes |
|---|---|---|
| `duration_hours` | `totalUsage` | Convert from minutes → hours |
| `ahi` | `ahi` | Apnea-hypopnea index (events/hour) |
| `leak_percentile` | `leakPercentile` | 0–100, lower is better |
| `mask_on_count` | `maskPairCount` | Times mask was put on |
| `sleep_score` | `sleepScore` | myAir score 0–100 |
| `ahi_score` | `ahiScore` | Component score |
| `mask_score` | `maskScore` | Component score |
| `usage_score` | `usageScore` | Component score |

---

## Authentication — OAuth 2.0 with PKCE via Okta (EU)

All EU endpoints. For full implementation details refer to the reference repo.

### Step 1 — Username/password auth

```
POST https://id.resmed.eu/api/v1/authn
Content-Type: application/json

{"username": "email@example.com", "password": "..."}
```

Returns `sessionToken` if no MFA, or `stateToken` + MFA factor if MFA is required.

### Step 2 — MFA (if required)

```
POST https://id.resmed.eu/api/v1/authn/factors/{factor_id}/verify
Content-Type: application/json

{"passCode": "123456", "stateToken": "..."}
```

Returns `sessionToken`.

### Step 3 — Generate PKCE values

- **Code verifier**: Base64-URL encode 40 random bytes, strip non-alphanumeric characters
- **Code challenge**: SHA256(code_verifier), Base64-URL encoded, strip `=` padding
- **Challenge method**: `S256`

### Step 4 — Get authorisation code

```
GET https://id.resmed.eu/oauth2/{auth_server_id}/v1/authorize
  ?client_id={EU_CLIENT_ID}
  &redirect_uri=...
  &response_type=code
  &scope=openid profile email
  &sessionToken={sessionToken}
  &code_challenge={code_challenge}
  &code_challenge_method=S256
```

Returns redirect containing `code` parameter.

### Step 5 — Exchange code for tokens

```
POST https://id.resmed.eu/oauth2/{auth_server_id}/v1/token
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code
&code={auth_code}
&code_verifier={code_verifier}
&client_id={EU_CLIENT_ID}
&redirect_uri=...
```

Returns `access_token` (Bearer) and `id_token` (JWT). Extract `myAirCountryId` from the JWT claims — needed as a request header.

---

## Sleep data — GraphQL

### Endpoint

```
POST https://graphql.hyperdrive.resmed.eu/graphql
```

### Required headers

```
Authorization: Bearer {access_token}
x-api-key: {EU_API_KEY}
rmdcountry: {myAirCountryId from JWT}
rmdproduct: myAir EU
rmdappversion: 1.0.0
rmdhandsetid: {generated device identifier}
rmdhandsetmodel: {device model string}
rmdhandsetplatform: {platform string}
```

`x-api-key` and `EU_CLIENT_ID` values: extract from the reference repo source or the myAir web app JS bundle. They are hardcoded constants, not user-specific.

### Query

```graphql
query GetPatientSleepRecords {
  getPatientWrapper {
    sleepRecords(startMonth: "ONE_MONTH_AGO", endMonth: "DATE") {
      items {
        startDate
        totalUsage
        sleepScore
        usageScore
        ahiScore
        maskScore
        leakScore
        ahi
        maskPairCount
        leakPercentile
        sleepRecordPatientId
      }
    }
  }
}
```

---

## Script location

```
jobs/scripts/resmed_sync.py
```

Replace the existing stub/v1 implementation entirely with the v2 auth flow described here, using the reference repo as a guide.

---

## Deduplication

Before posting each record, check whether it already exists:

```
GET {DATALAKE_URL}/events?source=resmed_myair&event_type=health.sleep&timestamp_from=<start_of_day>&timestamp_to=<end_of_day>
```

Skip if `total > 0`.

---

## Cron schedule

```
# ResMed myAir — daily at 11:00
0 11 * * * python3 /scripts/resmed_sync.py
```

Re-enable this line in `jobs/crontab` once the v2 implementation is working.

---

## Environment variables

`MYAIR_EMAIL`, `MYAIR_PASSWORD`, `DATALAKE_URL`, `DATALAKE_TOKEN` — defined in the datalake Portainer stack. See [`docs/features/datalake-jobs/feature.md`](../datalake-jobs/feature.md).

`MYAIR_API_URL` is no longer used — all endpoints are hardcoded for EU in the v2 implementation.

---

## Example event

```json
{
  "source": "resmed_myair",
  "event_type": "health.sleep",
  "timestamp": "2026-05-07T22:00:00+02:00",
  "payload": {
    "duration_hours": 7.2,
    "ahi": 2.8,
    "leak_percentile": 12,
    "mask_on_count": 1,
    "sleep_score": 84,
    "ahi_score": 90,
    "mask_score": 88,
    "usage_score": 95
  }
}
```
