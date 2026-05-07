#!/usr/bin/env python3

from __future__ import annotations

from datetime import datetime, timezone
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
    parse_iso_datetime,
    make_session,
    require_env,
)


SOURCE = "resmed_myair"
EVENT_TYPE = "health.sleep"


def main() -> int:
    try:
        email = require_env("MYAIR_EMAIL")
        password = require_env("MYAIR_PASSWORD")
        api_base_url = require_env("MYAIR_API_URL").rstrip("/")
        datalake_url = require_env("DATALAKE_URL")
        datalake_token = get_datalake_token()
        if not datalake_token:
            raise RuntimeError("missing required environment variable: DATALAKE_TOKEN")

        session = make_session()
        login_response = session.post(
            f"{api_base_url}/account/login",
            json={"email": email, "password": password, "grant_type": "password"},
            timeout=30,
        )
        login_response.raise_for_status()
        token = extract_token(login_response.json())
        if not token:
            raise RuntimeError("myAir login did not return a bearer token")

        records_response = api_get_json(
            make_session(token),
            f"{api_base_url}/v2/records",
        )
        records = _extract_records(records_response)
        if not records:
            print(json.dumps({"received": 0, "inserted": 0, "errors": []}))
            return 0

        candidates = [
            (timestamp, record)
            for record in records
            if (timestamp := _record_timestamp(record)) is not None
        ]
        if not candidates:
            print(json.dumps({"received": len(records), "inserted": 0, "errors": []}))
            return 0

        latest_day = max(timestamp for timestamp, _ in candidates).date()
        received = len(records)

        for _, record in sorted(
            [item for item in candidates if item[0].date() == latest_day],
            key=lambda item: item[0],
            reverse=True,
        ):
            try:
                event = _build_event(record)
            except ValueError:
                continue

            start, end = day_window(event["timestamp"])
            existing = api_get_json(
                make_session(datalake_token),
                f"{datalake_url.rstrip('/')}/events",
                params={
                    "source": SOURCE,
                    "event_type": EVENT_TYPE,
                    "timestamp_from": start,
                    "timestamp_to": end,
                    "page": 1,
                    "page_size": 500,
                    "order": "desc",
                },
            )
            if isinstance(existing, dict) and int(existing.get("total", 0) or 0) > 0:
                print(json.dumps({"received": received, "inserted": 0, "errors": []}))
                return 0

            create_event(
                datalake_url,
                datalake_token,
                source=SOURCE,
                event_type=EVENT_TYPE,
                timestamp=event["timestamp"],
                payload=event["payload"],
            )
            print(json.dumps({"received": received, "inserted": 1, "errors": []}))
            return 0

        print(json.dumps({"received": received, "inserted": 0, "errors": []}))
        return 0
    except requests.RequestException as exc:
        print(f"resmed_sync: request failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - scheduled job should surface unexpected failures
        print(f"resmed_sync: failed: {exc}", file=sys.stderr)
        return 1


def _extract_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("records", "data", "sessions", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        nested = payload.get("data")
        if isinstance(nested, dict):
            return _extract_records(nested)
    return []


def _record_timestamp(record: dict[str, Any]) -> datetime | None:
    for key in ("start", "startedAt", "start_time", "date", "timestamp", "sessionStart"):
        value = record.get(key)
        if isinstance(value, str) and value:
            try:
                parsed = parse_iso_datetime(value)
            except ValueError:
                continue
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
    return None


def _build_event(record: dict[str, Any]) -> dict[str, Any]:
    start = _record_timestamp(record)
    if start is None:
        raise ValueError("record missing a usable start timestamp")

    payload = {
        "duration_hours": _duration_hours(record),
        "ahi": _number_from(record, ("ahi", "apneaHypopneaIndex", "apnea_hypopnea_index")),
        "mask_leak_lpm": _number_from(record, ("mask_leak_lpm", "maskLeakLpm", "maskLeakRate", "maskLeak")),
        "mask_on_count": _int_from(record, ("mask_on_count", "maskOnCount", "maskCount")),
        "sleep_score": _int_from(record, ("sleep_score", "sleepScore", "score")),
    }
    return {
        "timestamp": start.isoformat(),
        "payload": payload,
    }


def _duration_hours(record: dict[str, Any]) -> float | None:
    for key in ("duration_hours", "durationHours", "hours"):
        value = _number_from(record, (key,))
        if value is not None:
            return value
    for key in ("duration_minutes", "durationMinutes", "minutes", "totalMinutes"):
        value = _number_from(record, (key,))
        if value is not None:
            return value / 60
    for key in ("duration_seconds", "durationSeconds", "seconds", "totalSeconds"):
        value = _number_from(record, (key,))
        if value is not None:
            return value / 3600
    nested = record.get("duration")
    if isinstance(nested, dict):
        return _duration_hours(nested)
    if isinstance(nested, (int, float, str)):
        value = _number_from({"duration": nested}, ("duration",))
        if value is not None:
            return value / 60 if value > 24 else value
    return None


def _number_from(record: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = record.get(key)
        if value is None or value == "":
            continue
        if isinstance(value, dict):
            for nested_key in ("qty", "value", "amount", "minutes", "seconds", "hours"):
                nested_value = value.get(nested_key)
                if nested_value not in (None, ""):
                    coerced = _coerce_number(nested_value)
                    if coerced is not None:
                        return coerced
            continue
        coerced = _coerce_number(value)
        if coerced is not None:
            return coerced
    return None


def _int_from(record: dict[str, Any], keys: tuple[str, ...]) -> int | None:
    value = _number_from(record, keys)
    return int(round(value)) if value is not None else None


def _coerce_number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    raise SystemExit(main())
