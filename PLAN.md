# Homelab Data Lake — Implementation Plan

## 1. Project Structure

```
datalake/
├── docker-compose.yml
├── .env.example
├── README.md
│
├── api/                          # FastAPI application
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic.ini               # Alembic config
│   ├── main.py                   # App factory, lifespan, router registration
│   ├── config.py                 # Settings via pydantic-settings / env vars
│   ├── auth.py                   # Bearer token dependency
│   ├── database.py               # SQLAlchemy engine, session factory, Base
│   ├── models.py                 # ORM models: Event, Source
│   ├── schemas.py                # Pydantic request/response schemas
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── events.py             # POST/GET /events, GET /events/:id
│   │   ├── batch.py              # POST /events/batch
│   │   ├── sources.py            # GET /sources
│   │   └── health.py             # GET /health
│   └── migrations/
│       ├── env.py                # Alembic env (reads DATABASE_URL)
│       └── versions/
│           └── 0001_initial.py   # Initial schema migration
│
├── mcp/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── server.py                 # fastmcp SSE server: query_datalake_events + log_datalake_event
│
├── data/                          # Optional local exports / backups
│
└── docs/
    ├── api.md                    # API reference (generated from OpenAPI)
    ├── ha-integration.md         # Home Assistant config snippets
    └── grafana-integration.md    # Grafana/Infinity datasource setup
```

---

## 2. Data Model

### 2.1 DDL — `events` table

```sql
CREATE TABLE events (
    id          TEXT        NOT NULL PRIMARY KEY,       -- UUID v4, generated server-side
    source      TEXT        NOT NULL,                   -- e.g. "apple_tv", "roborock"
    event_type  TEXT        NOT NULL,                   -- e.g. "watch.started", "clean.completed"
    timestamp   TEXT        NOT NULL,                   -- ISO 8601 with timezone, e.g. "2024-03-15T21:05:00Z"
    payload     TEXT        NOT NULL,                   -- JSON blob (TEXT in SQLite, JSONB in Postgres)
    created_at  TEXT        NOT NULL                    -- ISO 8601, server insertion time
        DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX idx_events_source       ON events (source);
CREATE INDEX idx_events_event_type   ON events (event_type);
CREATE INDEX idx_events_timestamp    ON events (timestamp);
CREATE INDEX idx_events_source_ts    ON events (source, timestamp DESC);  -- most common filter pattern
CREATE UNIQUE INDEX idx_events_id    ON events (id);
```

**Notes on the payload column:**
- SQLite stores it as `TEXT` (JSON serialised string).
- Alembic migration for Postgres will change this column to `JSONB` for indexing and containment queries. The API layer always deserialises/serialises JSON, so no application code changes are needed.

### 2.2 DDL — `sources` metadata table

This table is a registry of known producers, populated automatically on first event insert (upsert) and editable for metadata.

```sql
CREATE TABLE sources (
    id            TEXT  NOT NULL PRIMARY KEY,           -- same value as events.source, e.g. "apple_tv"
    display_name  TEXT  NOT NULL,                       -- e.g. "Apple TV"
    description   TEXT,                                 -- free text
    first_seen_at TEXT  NOT NULL,                       -- ISO 8601
    last_seen_at  TEXT  NOT NULL,                       -- ISO 8601, updated on each insert
    event_count   INTEGER NOT NULL DEFAULT 0            -- denormalised counter, updated on each insert
);
```

**Assumption:** The `sources` table is maintained via upsert from the ingest path — there is no separate admin endpoint to create sources manually. Sources self-register.

---

## 3. API Design

### 3.1 Authentication

All non-health endpoints require:

```
Authorization: Bearer <token>
```

The token is a static secret set in the `API_TOKEN` environment variable. A 401 is returned when the header is absent or the token does not match.

**Decision note:** See section 9 for token and transport decisions.

### 3.2 Error Response Shape

All errors use a consistent JSON envelope:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Human-readable description",
    "details": [ ... ]   // optional array of field-level errors
  }
}
```

Standard HTTP status codes: 400 (bad input), 401 (missing/bad token), 404 (not found), 422 (schema validation), 500 (server error).

---

### 3.3 Endpoints

#### `GET /health`

No auth required.

**Response 200:**
```json
{
  "status": "ok",
  "db": "ok",
  "version": "1.0.0",
  "uptime_seconds": 3600
}
```

---

#### `POST /events`

Ingest a single event.

**Request body:**
```json
{
  "source":     "apple_tv",
  "event_type": "watch.started",
  "timestamp":  "2024-03-15T21:05:00Z",
  "payload": {
    "title":   "Severance",
    "series_title": "Severance",
    "season":  2,
    "episode": 5,
    "app_name": "Netflix",
    "app_id": "com.netflix.Netflix",
    "content_type": "tvshow",
    "duration_seconds": 3120
  }
}
```

Field rules:
- `source`: required, string, max 64 chars, lowercase, no spaces (snake_case or dot-notation)
- `event_type`: required, string, max 128 chars
- `timestamp`: required, ISO 8601 string with timezone offset or `Z`
- `payload`: required, arbitrary JSON object (must be an object, not an array or scalar)

**Response 201:**
```json
{
  "id":         "550e8400-e29b-41d4-a716-446655440000",
  "source":     "apple_tv",
  "event_type": "watch.started",
  "timestamp":  "2024-03-15T21:05:00Z",
  "payload":    { ... },
  "created_at": "2024-03-15T21:05:03Z"
}
```

**Idempotency note:** The server generates the UUID. Clients that need idempotent inserts should include a stable `external_id` field inside `payload` and implement dedup at the collector level using the last-seen timestamp state file.

---

#### `POST /events/batch`

Ingest multiple events in a single request. Maximum 500 events per request.

**Request body:**
```json
{
  "events": [
    { "source": "roborock", "event_type": "clean.completed", "timestamp": "...", "payload": { ... } },
    { "source": "roborock", "event_type": "clean.completed", "timestamp": "...", "payload": { ... } }
  ]
}
```

**Response 207 Multi-Status:**
```json
{
  "inserted": 2,
  "errors": []
}
```

On partial failure:
```json
{
  "inserted": 1,
  "errors": [
    { "index": 1, "code": "VALIDATION_ERROR", "message": "timestamp: invalid format" }
  ]
}
```

---

#### `GET /events`

List and filter events. All parameters optional.

| Parameter    | Type    | Default | Description                                        |
|--------------|---------|---------|----------------------------------------------------|
| `source`     | string  | —       | Filter by source (exact match)                     |
| `event_type` | string  | —       | Filter by event_type (exact match)                 |
| `since`      | string  | —       | ISO 8601 — events where timestamp >= since         |
| `until`      | string  | —       | ISO 8601 — events where timestamp <= until         |
| `page`       | integer | 1       | 1-based page number                                |
| `page_size`  | integer | 50      | Items per page, max 500                            |
| `order`      | string  | `desc`  | `asc` or `desc` — sorts by timestamp               |

**Response 200:**
```json
{
  "data": [ { ...event }, { ...event } ],
  "pagination": {
    "page":       1,
    "page_size":  50,
    "total":      312,
    "pages":      7
  }
}
```

---

#### `GET /events/:id`

Retrieve a single event by UUID.

**Response 200:** Single event object (same shape as POST response).
**Response 404:** Standard error envelope.

---

#### `GET /sources`

List all known sources with metadata.

**Response 200:**
```json
{
  "data": [
    {
      "id":            "apple_tv",
      "display_name":  "Apple TV",
      "description":   "Viewing history captured from Home Assistant",
      "first_seen_at": "2024-01-01T00:00:00Z",
      "last_seen_at":  "2024-03-15T21:05:00Z",
      "event_count":   847
    }
  ]
}
```

---

## 4. Tech Stack Decision

### Evaluation

| Criterion                    | FastAPI (Python)                                       | Hono + Bun (TypeScript)                               |
|------------------------------|--------------------------------------------------------|-------------------------------------------------------|
| **Docker image size**        | `python:3.12-slim` ~200 MB base; final ~300–350 MB     | `oven/bun:alpine` ~90 MB base; final ~120–150 MB      |
| **Cold start**               | ~0.5–1.5 s (CPython startup + uvicorn)                 | ~50–150 ms (Bun JIT, V8-based)                        |
| **SQLite driver maturity**   | Excellent — `aiosqlite` + SQLAlchemy; stdlib `sqlite3` | Good — `bun:sqlite` (native Bun binding, very fast)   |
| **ORM / migration tooling**  | SQLAlchemy 2 + Alembic — mature, Postgres-proven       | Drizzle ORM + drizzle-kit — modern, good Postgres support |
| **MCP tool integration**     | Standard MCP transport and Python SDKs are straightforward | Any MCP-capable client can use the server, regardless of model |
| **Home Assistant ecosystem** | Python dominant; HA itself is Python                   | No advantage; HA uses REST regardless of server lang  |
| **Homelab ecosystem**        | Vast Python tooling for data, cron scripts, etc.       | Good tooling but less homelab tradition               |
| **Developer experience**     | Auto-generated OpenAPI/Swagger; Pydantic validation    | Manual OpenAPI via `@hono/zod-openapi`; Zod types     |
| **Collector reuse**          | Same Python env can run collectors in same image       | Collectors would likely be Python anyway (separate runtime) |

### Recommendation: FastAPI (Python)

**Rationale:**

1. The Home Assistant automations and any future collector scripts are Python-friendly. Using FastAPI keeps the API and the ingestion layer in one operational stack.
2. SQLAlchemy + Alembic is the most battle-tested ORM migration path from SQLite to Postgres — a stated requirement. Drizzle is capable but younger.
3. FastAPI generates interactive OpenAPI documentation automatically from Pydantic models, making it immediately usable as a reference when building the MCP tool or Home Assistant sensors.
4. A homelab is not cold-start sensitive. The 150–200 MB extra image weight is immaterial on a host with gigabytes of RAM.
5. If an MCP server is built later (section 7.3), `fastmcp` (Python) or any equivalent MCP SDK makes it straightforward.

**The only case for Hono/Bun** would be if the API needed to run on very constrained hardware (e.g., a 256 MB RAM device) or edge deployment were required. Neither applies here.

---

## 5. Ingest Strategy

### 5.1 Apple TV Viewing History

All viewing history is collected via the Home Assistant Apple TV integration. No third-party services or collector containers are involved.

#### How it works

The HA `media_player` entity for the Apple TV exposes whatever is currently playing on the device, regardless of app. An automation fires on every `media_title` attribute change while the state is `playing` and POSTs a `watch.started` event to the datalake. This covers all services uniformly.

**Why `watch.started` not `watch.completed`:** The ATV transitions to `idle`/`standby` unpredictably (auto-play chains, screen saver, app close). Capturing start is reliable; capturing end is not.

**Available entity attributes:**

| Attribute | Example value |
|-----------|--------------|
| `state` | `playing`, `paused`, `idle`, `standby` |
| `media_title` | `"Why I Quit My Job"` |
| `media_series_title` | `"Severance"` (TV shows only) |
| `media_season` | `2` |
| `media_episode` | `5` |
| `app_name` | `"YouTube"`, `"Netflix"`, `"Disney+"` |
| `app_id` | `"com.google.ios.youtube"` |
| `media_content_type` | `"tvshow"`, `"video"`, `"movie"` |
| `media_duration` | `3720` (seconds) |

#### HA automation

```yaml
# configuration.yaml (or automations.yaml)
automation:
  - alias: "Push Apple TV watch start to datalake"
    trigger:
      - platform: state
        entity_id: media_player.apple_tv   # adjust to your entity name
        attribute: media_title
        for:
          seconds: 2                        # debounce: ignore sub-2s flickers on reconnect
    condition:
      - condition: state
        entity_id: media_player.apple_tv
        state: "playing"
      - condition: template
        value_template: >
          {{ trigger.to_state.attributes.media_title not in ['', None] }}
    action:
      - service: rest_command.datalake_push_apple_tv
        data:
          title:        "{{ state_attr('media_player.apple_tv', 'media_title') }}"
          series_title: "{{ state_attr('media_player.apple_tv', 'media_series_title') | default('') }}"
          season:       "{{ state_attr('media_player.apple_tv', 'media_season') | default(none) }}"
          episode:      "{{ state_attr('media_player.apple_tv', 'media_episode') | default(none) }}"
          app_name:     "{{ state_attr('media_player.apple_tv', 'app_name') }}"
          app_id:       "{{ state_attr('media_player.apple_tv', 'app_id') }}"
          content_type: "{{ state_attr('media_player.apple_tv', 'media_content_type') | default('') }}"
          duration:     "{{ state_attr('media_player.apple_tv', 'media_duration') | default(none) }}"

rest_command:
  datalake_push_apple_tv:
    url: "http://YOUR_HOMELAB_IP:8000/events"
    method: POST
    headers:
      Authorization: !secret datalake_token
      Content-Type: application/json
    payload: >
      {
        "source": "apple_tv",
        "event_type": "watch.started",
        "timestamp": "{{ now().isoformat() }}",
        "payload": {
          "title":            "{{ title }}",
          "series_title":     {{ ('"' ~ series_title ~ '"') if series_title else 'null' }},
          "season":           {{ season if season != 'None' else 'null' }},
          "episode":          {{ episode if episode != 'None' else 'null' }},
          "app_name":         "{{ app_name }}",
          "app_id":           "{{ app_id }}",
          "content_type":     "{{ content_type }}",
          "duration_seconds": {{ duration if duration != 'None' else 'null' }}
        }
      }
```

**Resulting event shapes:**

```json
// YouTube video
{
  "source": "apple_tv", "event_type": "watch.started",
  "timestamp": "2024-03-15T20:00:00+01:00",
  "payload": {
    "title": "Why Every YouTube Channel Looks the Same",
    "series_title": null, "season": null, "episode": null,
    "app_name": "YouTube", "app_id": "com.google.ios.youtube",
    "content_type": "video", "duration_seconds": null
  }
}

// Netflix episode
{
  "source": "apple_tv", "event_type": "watch.started",
  "timestamp": "2024-03-15T21:00:00+01:00",
  "payload": {
    "title": "Goodbye, Mrs. Selvig",
    "series_title": "Severance", "season": 2, "episode": 5,
    "app_name": "Netflix", "app_id": "com.netflix.Netflix",
    "content_type": "tvshow", "duration_seconds": 3120
  }
}
```

---

### 5.2 Robovac Cleaning History

#### Device: Roborock S6 MaxV (`roborock.vacuum.a10`)

Collected via the existing Home Assistant Roborock integration — no collector container or additional credentials needed. An HA automation fires when the vacuum returns to the dock and POSTs a `clean.completed` event to the datalake with run stats from the entity's state attributes.

---

### 5.3 LLM-mediated Health & Lifestyle Ingest

#### How it works

The user describes an event in natural language to any MCP-capable LLM client. The client interprets the description, determines the event type, structures a JSON payload (including nutritional estimates for meals), and calls the `log_datalake_event` MCP write tool to insert it. No separate parsing service or API call is needed — the client model is the structuring engine.

```
User → "I went on a run, 2.6km, avg HR 145"
         ↓
LLM client (interprets + structures)
         ↓
log_datalake_event MCP tool
         ↓
POST /events → datalake
```

#### Source and event_type taxonomy

| source | event_type | When to use |
|--------|------------|-------------|
| `assistant_ingest` | `health.workout` | Any physical activity |
| `assistant_ingest` | `health.meal` | Any food/drink intake |
| `assistant_ingest` | `health.sleep` | Sleep duration/quality |
| `assistant_ingest` | `health.measurement` | Weight, blood pressure, etc. |
| `assistant_ingest` | `health.note` | Freeform health observations |

#### Payload schemas

**`health.workout`**
```json
{
  "source": "assistant_ingest",
  "event_type": "health.workout",
  "timestamp": "2024-03-15T09:30:00+01:00",
  "payload": {
    "activity": "run",
    "distance_km": 2.6,
    "duration_minutes": null,
    "avg_heart_rate_bpm": 145,
    "max_heart_rate_bpm": null,
    "calories_kcal": null,
    "notes": "I went on a run today"
  }
}
```

Known `activity` values: `run`, `walk`, `cycle`, `swim`, `strength`, `yoga`, `hiit`, `hike`. Use the closest match; default to `other` with a `notes` field if unclear.

**`health.meal`**
```json
{
  "source": "assistant_ingest",
  "event_type": "health.meal",
  "timestamp": "2024-03-15T08:00:00+01:00",
  "payload": {
    "meal_type": "breakfast",
    "description": "Two eggs and a sandwich with cottage cheese",
    "items": [
      { "name": "egg", "quantity": 2, "unit": "whole" },
      { "name": "bread", "quantity": 2, "unit": "slice" },
      { "name": "cottage cheese", "quantity": 100, "unit": "g", "estimated": true }
    ],
    "nutrition": {
      "calories_kcal": 420,
      "protein_g": 32,
      "carbs_g": 35,
      "fat_g": 14,
      "fiber_g": 2,
      "confidence": "estimated"
    }
  }
}
```

`meal_type`: `breakfast`, `lunch`, `dinner`, `snack`. Infer from time of day if not stated.

`nutrition.confidence`: always `"estimated"` for assistant-derived values. Quantities marked `"estimated": true` in items are guessed from context (e.g. a "sandwich" implies ~2 slices of bread, cottage cheese portion assumed 100g if unspecified).

#### Nutritional enrichment approach

The client model uses general knowledge of common foods for nutritional estimates. This covers typical portions of everyday foods accurately enough for personal tracking. The `confidence: "estimated"` field ensures queries can filter or caveat accordingly.

No external nutrition API is used in v1. If higher precision is needed later, the USDA FoodData Central API (free, no key required) can be called from the MCP server to look up exact values — but this adds latency and requires internet access from the MCP host.

#### Timestamp handling

If the user says "today" or "this morning", the client resolves to a reasonable timestamp (today's date + inferred time of day) before calling the tool. If the user gives a specific time, use it exactly. Always include the local timezone offset.

#### Example interactions

> "I went on a run today, 2.6km, avg heart rate 145"

→ `event_type: health.workout`, `activity: run`, `distance_km: 2.6`, `avg_heart_rate_bpm: 145`

> "I ate two eggs and a sandwich with cottage cheese"

→ `event_type: health.meal`, meal items + full nutrition block estimated

> "8 hours sleep last night, felt pretty good"

→ `event_type: health.sleep`, `duration_hours: 8`, `quality_notes: "felt pretty good"`

> "Weighed myself this morning, 82kg"

→ `event_type: health.measurement`, `metric: weight_kg`, `value: 82`

---

## 6. Docker Setup

### 6.1 `docker-compose.yml`

```yaml
version: "3.9"

services:
  api:
    build:
      context: ./api
      dockerfile: Dockerfile
    container_name: datalake-api
    restart: unless-stopped
    ports:
      - "${API_PORT:-8000}:8000"
    environment:
      DATABASE_URL: "sqlite:////data/datalake.db"
      API_TOKEN: "${API_TOKEN}"
      LOG_LEVEL: "${LOG_LEVEL:-info}"
    volumes:
      - datalake-data:/data
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 30s
      timeout: 5s
      retries: 3
    networks:
      - datalake

  mcp:
    build:
      context: ./mcp
      dockerfile: Dockerfile
    container_name: datalake-mcp
    restart: unless-stopped
    ports:
      - "${MCP_PORT:-8001}:8001"
    environment:
      DATALAKE_API_URL: "http://api:8000"
      DATALAKE_API_TOKEN: "${API_TOKEN}"
    depends_on:
      api:
        condition: service_healthy
    networks:
      - datalake

volumes:
  datalake-data:    # SQLite .db file — survives container restarts/upgrades

networks:
  datalake:
    driver: bridge
```

### 6.2 `api/Dockerfile`

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["sh", "-c", "alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 8000"]
```

### 6.3 `mcp/Dockerfile`

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .

CMD ["python", "server.py"]
```

`mcp/requirements.txt` needs: `fastmcp`, `httpx` (for async calls to the datalake API).

### 6.4 `.env.example`

```bash
# API
API_PORT=8000
API_TOKEN=change-me-generate-with-openssl-rand-hex-32
LOG_LEVEL=info

# MCP server
MCP_PORT=8001

# Future: Postgres
# DATABASE_URL=postgresql+asyncpg://user:pass@postgres:5432/datalake
```

### 6.5 Volume strategy

- `datalake-data` is a named Docker volume mounted at `/data` in the API container. The SQLite file lives at `/data/datalake.db`.
- Named volumes persist across `docker-compose down` and `docker-compose up` cycles.
- **Backup:** `docker run --rm -v datalake-data:/data -v $(pwd):/backup alpine tar czf /backup/datalake-backup.tar.gz /data`
- When migrating to Postgres, the `datalake-data` volume is no longer needed; data is exported via `sqlite3 datalake.db .dump` and imported to Postgres.

---

## 7. Consumer Integration Guide

### 7.1 Home Assistant

HA plays two roles: **producer** (automations in sections 5.1 and 5.2 push all events) and **consumer** (REST sensors read back from the datalake).

#### REST sensors — read from datalake

```yaml
# secrets.yaml
datalake_token: "Bearer your-api-token-here"
```

```yaml
# configuration.yaml
rest:
  - resource: "http://YOUR_HOMELAB_IP:8000/events"
    headers:
      Authorization: !secret datalake_token
    params:
      source: apple_tv
      page_size: 1
      order: desc
    scan_interval: 300
    sensor:
      - name: "Last Watched"
        unique_id: datalake_last_watched
        value_template: >
          {{ value_json.data[0].payload.title if value_json.data | length > 0 else 'None' }}
        json_attributes_path: "$.data[0]"
        json_attributes:
          - timestamp
          - payload

  - resource: "http://YOUR_HOMELAB_IP:8000/events"
    headers:
      Authorization: !secret datalake_token
    params:
      source: roborock
      page_size: 1
      order: desc
    scan_interval: 1800
    sensor:
      - name: "Last Vacuum Run"
        unique_id: datalake_last_vacuum
        value_template: >
          {{ value_json.data[0].payload.duration_seconds | int // 60 }} min
        json_attributes_path: "$.data[0]"
        json_attributes:
          - timestamp
          - payload
```

#### Automation — push vacuum run

```yaml
automation:
  - alias: "Push vacuum run to datalake"
    trigger:
      - platform: state
        entity_id: vacuum.roborock_s6_maxv   # adjust to your entity name
        to: "docked"
        for:
          seconds: 10
    action:
      - service: rest_command.datalake_push_vacuum
        data:
          duration: "{{ state_attr('vacuum.roborock_s6_maxv', 'last_run_stats').total_time | default(0) }}"
          area:     "{{ (state_attr('vacuum.roborock_s6_maxv', 'last_run_stats').area | float / 1000000) | round(2) }}"

rest_command:
  datalake_push_vacuum:
    url: "http://YOUR_HOMELAB_IP:8000/events"
    method: POST
    headers:
      Authorization: !secret datalake_token
      Content-Type: application/json
    payload: >
      {
        "source": "roborock",
        "event_type": "clean.completed",
        "timestamp": "{{ now().isoformat() }}",
        "payload": {
          "duration_seconds": {{ duration }},
          "area_m2": {{ area }},
          "device": "roborock_s6_maxv"
        }
      }
```

---

### 7.2 Grafana — Infinity Datasource

Install the Infinity datasource plugin in Grafana (available in Grafana Cloud and via the plugin marketplace for self-hosted Grafana).

#### Provisioning config (`grafana/provisioning/datasources/datalake.yml`):

```yaml
apiVersion: 1
datasources:
  - name: Datalake
    type: yesoreyeram-infinity-datasource
    access: proxy
    jsonData:
      auth_method: bearerToken
      allowed_hosts:
        - "http://YOUR_HOMELAB_IP:8000"
    secureJsonData:
      bearerToken: "your-api-token-here"
```

#### Example panel query (JSON format in Infinity):

```
Type:       JSON
Method:     GET
URL:        http://YOUR_HOMELAB_IP:8000/events
Query params:
  source    = roborock
  page_size = 500
  order     = asc
  since     = ${__from:date:iso}
  until     = ${__to:date:iso}
Root path:  data
Columns:
  timestamp                → time field
  payload.duration_seconds → number → "Duration (s)"
  payload.area_m2          → number → "Area (m²)"
```

For a time series panel showing vacuum run durations, set `timestamp` as the time column and `payload.duration_seconds` as the value column.

---

### 7.3 MCP Tools

The MCP server (`mcp/server.py`) uses `fastmcp` (Python) and exposes two tools: one for querying and one for writing. The write tool is what enables the model-mediated health ingest described in section 5.3.

#### Tool 1: `query_datalake_events` (read)

```json
{
  "name": "query_datalake_events",
    "description": "Query the homelab data lake for stored events. Sources: 'apple_tv' (viewing history), 'roborock' (vacuum runs), 'assistant_ingest' (health, meals, workouts logged via an LLM client). Returns paginated results.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "source": {
        "type": "string",
        "description": "Filter by source. Known values: 'apple_tv', 'roborock', 'assistant_ingest'. Omit for all sources."
      },
      "event_type": {
        "type": "string",
        "description": "Filter by event type. Examples: 'watch.started', 'clean.completed', 'health.workout', 'health.meal'."
      },
      "since": {
        "type": "string",
        "description": "ISO 8601 datetime — return events at or after this time."
      },
      "until": {
        "type": "string",
        "description": "ISO 8601 datetime — return events at or before this time."
      },
      "page":      { "type": "integer", "default": 1,    "minimum": 1 },
      "page_size": { "type": "integer", "default": 50,   "minimum": 1, "maximum": 500 },
      "order":     { "type": "string",  "default": "desc", "enum": ["asc", "desc"] }
    },
    "required": []
  }
}
```

#### Tool 2: `log_datalake_event` (write)

Any MCP-capable client calls this tool after interpreting a natural language description. The client is responsible for structuring the payload — the tool is a thin POST wrapper.

```json
{
  "name": "log_datalake_event",
    "description": "Insert a structured event into the homelab data lake. Use this after interpreting a natural language description from the user. You are responsible for determining source, event_type, and structuring the payload according to the schemas in your instructions. Always confirm back to the user what was logged.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "source": {
        "type": "string",
        "description": "Always 'assistant_ingest' for events logged via this tool."
      },
      "event_type": {
        "type": "string",
        "description": "One of: 'health.workout', 'health.meal', 'health.sleep', 'health.measurement', 'health.note'."
      },
      "timestamp": {
        "type": "string",
        "description": "ISO 8601 datetime with timezone. Resolve natural language times ('this morning', 'today') to an absolute timestamp before calling."
      },
      "payload": {
        "type": "object",
        "description": "Structured event data. See section 5.3 of PLAN.md for per-event-type schemas. For health.meal, always include a 'nutrition' block with calorie and protein estimates."
      }
    },
    "required": ["source", "event_type", "timestamp", "payload"]
  }
}
```

#### MCP client configuration

The MCP server runs in Docker using SSE (Server-Sent Events) transport, making it accessible from any device on the LAN — desktop clients, web clients, mobile clients, or custom tools that support MCP.

This intentionally does not use `stdio` for the primary path. `stdio` is great for a local, same-machine assistant, but it would block the house-wide use case where the server lives on the homelab and any computer or phone can connect to it over the network.

```json
{
  "mcpServers": {
    "datalake": {
      "type": "sse",
      "url": "http://YOUR_HOMELAB_IP:8001/sse"
    }
  }
}
```

Add this config to the MCP client's equivalent settings file, or a project-local `.mcp.json` if your client supports it. No credentials are stored on the client — the MCP server holds the datalake API token internally.

**Transport:** SSE (`fastmcp run server.py --transport sse --port 8001`). The MCP server is LAN-accessible only, consistent with the API. If you need access outside the home network, connecting via VPN is the recommended path rather than exposing either service to the internet.

`mcp/server.py` exposes both tools. `query_datalake_events` makes an authenticated GET to `/events`; `log_datalake_event` makes an authenticated POST to `/events`. Both use `httpx.AsyncClient` with the `DATALAKE_API_TOKEN` from environment.

#### Example query flows

> "How much protein have I had today?"

→ The client calls `query_datalake_events(source="assistant_ingest", event_type="health.meal", since="<today 00:00>")`, sums `payload.nutrition.protein_g` across results, answers.

> "How many runs did I do last month?"

→ The client calls `query_datalake_events(source="assistant_ingest", event_type="health.workout", since="<first of last month>", until="<last of last month>")`, filters `payload.activity == "run"`, counts, answers.

---

## 8. Migration Path: SQLite to Postgres

All that changes is `DATABASE_URL` and one Alembic migration for the payload column type. No API code changes.

### Step 1 — Add Postgres to docker-compose.yml

```yaml
services:
  postgres:
    image: postgres:16-alpine
    container_name: datalake-postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: datalake
      POSTGRES_USER: datalake
      POSTGRES_PASSWORD: "${POSTGRES_PASSWORD}"
    volumes:
      - postgres-data:/var/lib/postgresql/data
    networks:
      - datalake
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U datalake"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  postgres-data:
```

### Step 2 — Update `DATABASE_URL` in `.env`

```bash
# Before
DATABASE_URL=sqlite:////data/datalake.db

# After
DATABASE_URL=postgresql+asyncpg://datalake:${POSTGRES_PASSWORD}@postgres:5432/datalake
```

No changes to `api/database.py` — SQLAlchemy reads `DATABASE_URL` and selects the dialect automatically.

### Step 3 — Write the Alembic migration for Postgres JSONB

Create `api/migrations/versions/0002_postgres_jsonb.py`:

```python
# This migration is a no-op on SQLite (detected via dialect)
# On Postgres it changes the payload column from TEXT to JSONB

def upgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.alter_column(
            "events",
            "payload",
            type_=postgresql.JSONB(astext_type=Text()),
            postgresql_using="payload::jsonb"
        )
```

### Step 4 — Export data from SQLite

```bash
sqlite3 /data/datalake.db ".mode csv" ".output /tmp/events.csv" "SELECT * FROM events;"
sqlite3 /data/datalake.db ".mode csv" ".output /tmp/sources.csv" "SELECT * FROM sources;"
```

### Step 5 — Import to Postgres

```bash
psql postgresql://datalake:password@localhost:5432/datalake \
  -c "\COPY events FROM '/tmp/events.csv' CSV HEADER"
psql postgresql://datalake:password@localhost:5432/datalake \
  -c "\COPY sources FROM '/tmp/sources.csv' CSV HEADER"
```

### Step 6 — Run migrations and restart

```bash
docker-compose exec api alembic upgrade head
docker-compose up -d api
```

### ORM abstraction strategy

The SQLAlchemy model uses a custom type that maps transparently across dialects:

```python
# api/models.py
PayloadType = Text().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql")
```

All `session.query(Event).filter(...)` calls work identically on both dialects. Postgres-specific JSONB containment queries can be added later as opt-in, dialect-aware filters without breaking the SQLite path.

---

## 9. Confirmed Decisions

Summary of confirmed decisions:

| Question | Decision |
|----------|----------|
| Robovac brand/model | Roborock S6 MaxV (`roborock.vacuum.a10`) — HA integration already running |
| Apple TV viewing history | HA Apple TV entity for all services — no Trakt, no collector container |
| Roborock history | HA Roborock integration already running — HA automation pushes on dock |
| Retention policy | Grow indefinitely, no TTL in v1 |
| Auth tokens | Single shared static token for all consumers |
| MCP clients | Any MCP-capable client can use the server; not tied to one model or vendor |
| MCP transport | SSE over LAN, not `stdio`, so any computer or phone in the house can connect |
| Grafana | External consumer, not in this docker-compose stack |
| Transport security | HTTP on LAN, no TLS proxy needed |

**Implementation can begin.**
