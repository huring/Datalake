# API Reference

Base URL:

- `http://docker.home:8000`

All non-health routes require a bearer token:

```http
Authorization: Bearer <API_TOKEN>
```

## Health

### `GET /health`

Unauthenticated health check for the API and database.

Response:

```json
{
  "status": "ok",
  "db": {
    "status": "ok",
    "engine": "sqlite",
    "path": "/data/datalake.db"
  },
  "version": "..."
}
```

## Root

### `GET /`

Protected status endpoint.

Response:

```json
{
  "service": "api",
  "status": "running",
  "version": "..."
}
```

## Events

### `POST /events`

Create one event.

Request body:

```json
{
  "source": "apple_tv",
  "event_type": "watch.started",
  "timestamp": "2026-05-07T20:00:00+02:00",
  "payload": {}
}
```

Response: `201 Created`

```json
{
  "id": "uuid",
  "source": "apple_tv",
  "event_type": "watch.started",
  "timestamp": "2026-05-07T20:00:00+02:00",
  "payload": {},
  "created_at": "2026-05-07T20:00:01+02:00"
}
```

### `GET /events`

List events with filters and pagination.

Query params:

- `source`
- `event_type`
- `timestamp_from`
- `timestamp_to`
- `page` default `1`
- `page_size` default `25`
- `order` default `desc`, allowed `asc` or `desc`

Response:

```json
{
  "data": [],
  "page": 1,
  "page_size": 25,
  "total": 0,
  "total_pages": 0
}
```

### `GET /events/{event_id}`

Fetch one event by ID.

Response: `200 OK` or `404 Not Found`

### `POST /events/batch`

Insert a batch of events with partial success reporting.

Request body:

```json
{
  "events": [
    {
      "source": "apple_tv",
      "event_type": "watch.started",
      "timestamp": "2026-05-07T20:00:00+02:00",
      "payload": {}
    }
  ]
}
```

Response: `207 Multi-Status`

```json
{
  "inserted": 1,
  "errors": []
}
```

Batch limit: 500 events.

## Sources

### `GET /sources`

List the known sources.

Response:

```json
{
  "data": [
    {
      "id": "apple_tv",
      "display_name": "Apple Tv",
      "description": null,
      "first_seen_at": "2026-05-07T20:00:00+02:00",
      "last_seen_at": "2026-05-07T20:10:00+02:00",
      "event_count": 3
    }
  ]
}
```

## Error responses

- `401 Unauthorized` for missing or invalid bearer tokens
- `404 Not Found` for unknown event IDs
- `422 Unprocessable Entity` for validation errors

