#!/usr/bin/env python3

from __future__ import annotations

import json
import sys
from typing import Any

import requests

from common import (
    api_get_json,
    create_event,
    day_window,
    extract_token,
    get_datalake_token,
    fetch_events,
    parse_iso_datetime,
    make_session,
    require_env,
)


SOURCE = "pocketcasts"
EVENT_TYPE = "media.podcast"
PUBLISHED_KEYS = ("publishedAt", "published_at", "published")
PODCAST_KEYS = ("podcast", "podcastName", "show")
TITLE_KEYS = ("title", "episodeTitle", "episode_title")
DURATION_KEYS = ("duration", "durationSeconds", "duration_seconds")
LISTENED_KEYS = ("playedUpTo", "played_up_to", "listened_seconds")


def main() -> int:
    try:
        email = require_env("POCKETCASTS_EMAIL")
        password = require_env("POCKETCASTS_PASSWORD")
        datalake_url = require_env("DATALAKE_URL")
        datalake_token = get_datalake_token()
        if not datalake_token:
            raise RuntimeError("missing required environment variable: DATALAKE_TOKEN")

        login_session = make_session()
        login_response = login_session.post(
            "https://api.pocketcasts.com/user/login",
            json={"email": email, "password": password},
            timeout=30,
        )
        login_response.raise_for_status()
        token = extract_token(login_response.json())
        if not token:
            raise RuntimeError("Pocketcasts login did not return a token")

        history = api_get_json(
            make_session(token),
            "https://api.pocketcasts.com/user/history",
        )
        if isinstance(history, dict):
            items = history.get("history") or history.get("data") or history.get("items") or []
        elif isinstance(history, list):
            items = history
        else:
            raise RuntimeError("unexpected Pocketcasts history response shape")

        inserted = 0
        received = len(items)

        for raw_item in items:
            if not isinstance(raw_item, dict):
                continue
            try:
                item = _normalize_item(raw_item)
            except ValueError:
                continue
            start, end = day_window(item["published_at"])
            existing_events = fetch_events(
                datalake_url,
                datalake_token,
                params={
                    "source": SOURCE,
                    "event_type": EVENT_TYPE,
                    "timestamp_from": start,
                    "timestamp_to": end,
                },
            )
            if any(
                event.get("payload", {}).get("podcast") == item["podcast"]
                and event.get("payload", {}).get("title") == item["title"]
                for event in existing_events
            ):
                continue

            create_event(
                datalake_url,
                datalake_token,
                source=SOURCE,
                event_type=EVENT_TYPE,
                timestamp=item["published_at"],
                payload={
                    "podcast": item["podcast"],
                    "title": item["title"],
                    "duration_seconds": item["duration_seconds"],
                    "listened_seconds": item["listened_seconds"],
                    "completed": item["completed"],
                },
            )
            inserted += 1

        print(json.dumps({"received": received, "inserted": inserted, "errors": []}))
        return 0
    except requests.RequestException as exc:
        print(f"pocketcasts_sync: request failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - scheduled job should surface unexpected failures
        print(f"pocketcasts_sync: failed: {exc}", file=sys.stderr)
        return 1


def _normalize_item(raw_item: dict[str, Any]) -> dict[str, Any]:
    podcast = _first_value(raw_item, PODCAST_KEYS)
    title = _first_value(raw_item, TITLE_KEYS)
    published_at = _first_value(raw_item, PUBLISHED_KEYS)
    duration = _coerce_number(_first_value(raw_item, DURATION_KEYS))
    listened = _coerce_number(_first_value(raw_item, LISTENED_KEYS))

    if not podcast or not title or not published_at:
        raise ValueError("missing required Pocketcasts fields")

    parsed = parse_iso_datetime(str(published_at))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("publishedAt must include timezone information")

    if duration is None or listened is None:
        raise ValueError("missing duration/listened values")

    return {
        "podcast": str(podcast),
        "title": str(title),
        "published_at": parsed.isoformat(),
        "duration_seconds": int(round(duration)),
        "listened_seconds": int(round(listened)),
        "completed": listened >= (duration * 0.9),
    }


def _first_value(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return None


def _coerce_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, dict):
        for key in ("qty", "value", "seconds", "duration"):
            if key in value:
                return _coerce_number(value[key])
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    raise SystemExit(main())
