# Homelab Data Lake Backlog

Source documents:
- [PLAN.md](./PLAN.md)
- [agents.md](./agents.md)

This backlog is ordered for implementation, not for design discussion. The goal is to finish the simplest vertical slice first, then expand outward.

## Priority Order

1. Foundation and API skeleton
2. Core event storage and query endpoints
3. Batch ingest and source registry
4. MCP server and LAN client wiring
5. Home Assistant producers and consumers
6. Grafana and docs
7. SQLite to Postgres migration path

## Implementation Cards

### Card 01 - Repo scaffold and runtime wiring
- Goal: Create the initial project structure from the plan, including API and MCP service directories, environment examples, and Docker Compose wiring.
- Status: Done.
- Depends on: None.
- Deliverable: The repo builds into separate API and MCP containers with a shared LAN network and a persisted data volume.
- Acceptance criteria: `docker-compose up` starts both services, the API health endpoint is reachable, and the MCP service can reach the API over the internal network.

### Card 02 - API configuration, auth, and health check
- Goal: Implement config loading, bearer-token auth, and the unauthenticated health endpoint.
- Status: Done.
- Depends on: Card 01.
- Deliverable: A FastAPI app that reads environment variables, enforces auth on non-health routes, and reports basic DB readiness.
- Acceptance criteria: Missing or invalid tokens return 401, `/health` returns 200 without auth, and startup failures are visible in logs.

### Card 03 - Database layer and initial migrations
- Goal: Implement SQLAlchemy models, session management, and Alembic bootstrap for the initial schema.
- Status: Done.
- Depends on: Card 02.
- Deliverable: `events` and `sources` tables with the indexes and column types described in the plan.
- Acceptance criteria: Fresh database creation works from migration, and the ORM models match the documented schema.

### Card 04 - Single-event ingest endpoint
- Goal: Add `POST /events` for event creation with validation, UUID generation, and source upsert behavior.
- Depends on: Card 03.
- Deliverable: A working single-event ingestion path that stores events and updates source metadata.
- Acceptance criteria: Valid events return 201, invalid payloads are rejected cleanly, and inserted events are retrievable.

### Card 05 - Event query endpoints
- Goal: Add `GET /events` and `GET /events/:id` with filtering, sorting, pagination, and consistent error handling.
- Depends on: Card 04.
- Deliverable: Read endpoints that match the response shapes in the plan.
- Acceptance criteria: Source, type, and time-range filters work; pagination metadata is correct; missing IDs return 404.

### Card 06 - Batch ingest endpoint
- Goal: Add `POST /events/batch` with partial success reporting and a request-size limit.
- Status: Done.
- Depends on: Card 04.
- Deliverable: Bulk event ingestion with per-item validation feedback.
- Acceptance criteria: Mixed-validity batches return a multi-status style response, and the documented max batch size is enforced.

### Card 07 - Sources endpoint
- Goal: Add `GET /sources` so consumers can inspect the registry of known producers.
- Status: Done.
- Depends on: Card 03.
- Deliverable: A read-only sources listing endpoint with metadata and event counts.
- Acceptance criteria: Source metadata reflects insert activity and returns in a stable JSON shape.

### Card 08 - MCP server skeleton and transport
- Goal: Stand up the MCP server as a LAN-accessible SSE service that is usable from any computer or phone on the home network.
- Status: In progress.
- Depends on: Card 02 and Card 04.
- Deliverable: A generic MCP server entrypoint that can connect to the API and expose tools over SSE.
- Acceptance criteria: The server starts in Docker, publishes a stable SSE endpoint, and does not depend on `stdio` for the primary path.

### Card 09 - MCP read tool
- Goal: Implement `query_datalake_events` as the read path for any MCP-capable client.
- Depends on: Card 08 and Card 05.
- Deliverable: A tool that proxies the API query endpoint with the same filters and pagination semantics.
- Acceptance criteria: The tool returns predictable structured results, handles empty sets, and surfaces API errors clearly.

### Card 10 - MCP write tool
- Goal: Implement `log_datalake_event` as the write path for any MCP-capable client.
- Depends on: Card 08 and Card 04.
- Deliverable: A thin POST wrapper that inserts structured events into the API.
- Acceptance criteria: Valid tool calls create events, malformed calls fail cleanly, and the tool contract stays model-agnostic.

### Card 11 - Home Assistant Apple TV automation
- Goal: Push Apple TV viewing events into the datalake from Home Assistant.
- Depends on: Card 04 and Card 10.
- Deliverable: A documented HA automation that emits `apple_tv` `watch.started` events.
- Acceptance criteria: The automation posts valid payloads, handles reconnect flicker, and records enough metadata for downstream consumers.

### Card 12 - Home Assistant Roborock automation
- Goal: Push vacuum completion events into the datalake from Home Assistant.
- Depends on: Card 04 and Card 10.
- Deliverable: A documented HA automation that emits `roborock` `clean.completed` events.
- Acceptance criteria: Dock-return events are captured reliably, and the payload includes the documented run stats.

### Card 13 - Home Assistant consumer docs
- Goal: Document REST sensor patterns for reading recent events back from the datalake.
- Depends on: Card 05.
- Deliverable: Example HA configs for last watched item and last vacuum run.
- Acceptance criteria: The examples are consistent with the API response shapes and do not assume hidden fields.

### Card 14 - Grafana integration guide
- Goal: Document how to query the datalake from Grafana using the Infinity datasource.
- Depends on: Card 05.
- Deliverable: A Grafana provisioning example and a sample panel query.
- Acceptance criteria: A user can follow the doc to build a basic time-series panel without guessing the API shape.

### Card 15 - Postgres migration path
- Goal: Turn the SQLite-to-Postgres migration sketch into a real, repeatable path.
- Depends on: Card 03.
- Deliverable: A migration plan that covers the database URL swap, JSONB conversion, and data export/import.
- Acceptance criteria: The migration steps are concrete enough to run without ad hoc reasoning, and SQLite behavior remains the default v1 path.

### Card 16 - API reference and rollout docs
- Goal: Generate or publish the API reference and a short operator README for setup and backup.
- Depends on: Cards 04, 05, 06, 07.
- Deliverable: Human-readable docs for the API, backups, and first-run startup.
- Acceptance criteria: The README points to the right env vars, ports, and backup steps, and the API reference matches the implemented routes.

## Suggested Execution Slice

If we want the smallest useful first milestone, build Cards 01 through 05 first. That gives us a working API with storage, auth, and query capability before layering on batch ingest, MCP, and Home Assistant automation.

## Out of Scope For v1

- Per-user auth and multi-tenant access control
- TLS termination inside the stack
- TTL-based retention or archival jobs
- A separate source admin UI
- Advanced Postgres-specific JSONB query features
