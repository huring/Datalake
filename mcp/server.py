import os
from datetime import datetime
from typing import Any, TypedDict

import httpx
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_access_token
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse


VERSION = "card-10-mcp-write-tool"
DEFAULT_API_URL = "http://api:8000"
ALLOWED_WRITE_EVENT_TYPES = {
    "health.workout",
    "health.meal",
    "health.sleep",
    "health.measurement",
    "health.note",
}

mcp = FastMCP("Homelab Data Lake MCP")


def _api_base_url() -> str:
    return os.environ.get("DATALAKE_API_URL", DEFAULT_API_URL).rstrip("/")


def _api_token() -> str:
    token = get_access_token()
    if token is not None and token.token:
        return token.token
    return os.environ.get("DATALAKE_API_TOKEN", "")


def _api_headers() -> dict[str, str]:
    token = _api_token()
    return {"Authorization": f"Bearer {token}"} if token else {}


def _normalize_iso8601(value: str | None) -> str | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include timezone information")
    return value


async def _fetch_api_health() -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{_api_base_url()}/health", headers=_api_headers())
            response.raise_for_status()
            return response.json()
    except Exception as exc:  # noqa: BLE001 - the health route should report upstream failures cleanly
        return {
            "status": "degraded",
            "error": str(exc),
        }


class QueryResult(TypedDict):
    data: list[dict[str, Any]]
    page: int
    page_size: int
    total: int
    total_pages: int


class WriteResult(TypedDict):
    message: str
    event: dict[str, Any]


@mcp.tool
async def query_datalake_events(
    source: str | None = None,
    event_type: str | None = None,
    since: str | None = None,
    until: str | None = None,
    page: int = 1,
    page_size: int = 50,
    order: str = "desc",
) -> QueryResult:
    if page < 1:
        raise ValueError("page must be at least 1")
    if page_size < 1 or page_size > 500:
        raise ValueError("page_size must be between 1 and 500")
    if order not in {"asc", "desc"}:
        raise ValueError("order must be asc or desc")

    params: dict[str, Any] = {"page": page, "page_size": page_size, "order": order}
    if source is not None:
        params["source"] = source
    if event_type is not None:
        params["event_type"] = event_type
    if since is not None:
        params["timestamp_from"] = _normalize_iso8601(since)
    if until is not None:
        params["timestamp_to"] = _normalize_iso8601(until)

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.get(
                f"{_api_base_url()}/events",
                params=params,
                headers=_api_headers(),
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"API request failed with status {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"API request failed: {exc}") from exc

    return {
        "data": payload.get("data", []),
        "page": payload.get("page", page),
        "page_size": payload.get("page_size", page_size),
        "total": payload.get("total", 0),
        "total_pages": payload.get("total_pages", 0),
    }


@mcp.tool
async def log_datalake_event(
    source: str,
    event_type: str,
    timestamp: str,
    payload: dict[str, Any],
) -> WriteResult:
    if source != "assistant_ingest":
        raise ValueError("source must be assistant_ingest")
    if event_type not in ALLOWED_WRITE_EVENT_TYPES:
        raise ValueError(
            "event_type must be one of: health.workout, health.meal, health.sleep, health.measurement, health.note"
        )
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")

    normalized_timestamp = _normalize_iso8601(timestamp)
    if normalized_timestamp is None:
        raise ValueError("timestamp is required")

    body = {
        "source": source,
        "event_type": event_type,
        "timestamp": normalized_timestamp,
        "payload": payload,
    }

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.post(
                f"{_api_base_url()}/events",
                json=body,
                headers=_api_headers(),
            )
            response.raise_for_status()
            created = response.json()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"API request failed with status {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"API request failed: {exc}") from exc

    return {
        "message": "event logged",
        "event": created,
    }


@mcp.custom_route("/", methods=["GET"])
async def root(_: Request) -> PlainTextResponse:
    return PlainTextResponse("Homelab Data Lake MCP")


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    api_health = await _fetch_api_health()
    ok = api_health.get("status") == "ok"
    return JSONResponse(
        {
            "service": "mcp",
            "status": "ok" if ok else "degraded",
            "version": VERSION,
            "transport": "sse",
            "api": api_health,
        },
        status_code=200 if ok else 503,
    )


def main() -> None:
    port = int(os.environ.get("MCP_PORT", "8001"))
    mcp.run(transport="sse", host="0.0.0.0", port=port, path="/sse")


if __name__ == "__main__":
    main()
