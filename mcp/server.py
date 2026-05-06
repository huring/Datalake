import os
from typing import Any

import httpx
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse


VERSION = "card-08-mcp-sse-skeleton"
DEFAULT_API_URL = "http://api:8000"

mcp = FastMCP("Homelab Data Lake MCP")


def _api_base_url() -> str:
    return os.environ.get("DATALAKE_API_URL", DEFAULT_API_URL).rstrip("/")


def _api_headers() -> dict[str, str]:
    token = os.environ.get("DATALAKE_API_TOKEN", "")
    return {"Authorization": f"Bearer {token}"} if token else {}


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
