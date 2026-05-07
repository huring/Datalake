from __future__ import annotations

import re
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import requests


DEFAULT_TIMEOUT = 30
COMPACT_OFFSET_PATTERN = re.compile(r"([+-]\d{2})(\d{2})$")


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"missing required environment variable: {name}")
    return value


def get_datalake_token() -> str:
    return os.environ.get("DATALAKE_TOKEN") or os.environ.get("API_TOKEN") or ""


def make_session(token: str | None = None) -> requests.Session:
    session = requests.Session()
    if token:
        session.headers.update({"Authorization": f"Bearer {token}"})
    return session


def extract_token(payload: Any) -> str | None:
    if isinstance(payload, dict):
        for key in ("token", "access_token", "accessToken", "bearer_token"):
            value = payload.get(key)
            if value:
                return str(value)
        nested = payload.get("data")
        if isinstance(nested, dict):
            return extract_token(nested)
    return None


def parse_iso_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    if " " in normalized and "T" not in normalized:
        normalized = normalized.replace(" ", "T", 1)
    normalized = COMPACT_OFFSET_PATTERN.sub(r"\1:\2", normalized)
    return datetime.fromisoformat(normalized)


def day_window(value: str) -> tuple[str, str]:
    parsed = parse_iso_datetime(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    start = parsed.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1) - timedelta(microseconds=1)
    return start.isoformat(), end.isoformat()


def api_get_json(
    session: requests.Session,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Any:
    response = session.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    return response.json()


def api_post_json(
    session: requests.Session,
    url: str,
    *,
    json_body: dict[str, Any],
    timeout: int = DEFAULT_TIMEOUT,
) -> Any:
    response = session.post(url, json=json_body, timeout=timeout)
    response.raise_for_status()
    if response.content:
        return response.json()
    return {}


def fetch_events(
    base_url: str,
    token: str,
    *,
    params: dict[str, Any],
    page_size: int = 500,
) -> list[dict[str, Any]]:
    session = make_session(token)
    events: list[dict[str, Any]] = []
    page = 1

    while True:
        page_params = dict(params)
        page_params.update({"page": page, "page_size": page_size, "order": "desc"})
        payload = api_get_json(session, f"{base_url.rstrip('/')}/events", params=page_params)
        events.extend(payload.get("data", []))
        total_pages = int(payload.get("total_pages", 0) or 0)
        if page >= total_pages:
            break
        page += 1

    return events


def create_event(
    base_url: str,
    token: str,
    *,
    source: str,
    event_type: str,
    timestamp: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    session = make_session(token)
    body = {
        "source": source,
        "event_type": event_type,
        "timestamp": timestamp,
        "payload": payload,
    }
    response = api_post_json(session, f"{base_url.rstrip('/')}/events", json_body=body)
    if not isinstance(response, dict):
        raise RuntimeError("unexpected response shape from datalake API")
    return response
