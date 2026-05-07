from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from auth import require_token
from database import get_db
from routers.events import _create_event_record
from schemas import AppleHealthImportRequest, AppleHealthImportResult, EventCreate


router = APIRouter(
    prefix="/ingest",
    tags=["ingest"],
    dependencies=[Depends(require_token)],
)


def _sample_label(sample: dict[str, Any]) -> str:
    value = sample.get("name") or sample.get("type") or sample.get("identifier") or ""
    return str(value)


def _first_value(sample: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in sample and sample[key] is not None:
            return sample[key]
    return None


def _qty_value(sample: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = sample.get(key)
        if isinstance(value, dict):
            qty = value.get("qty")
            if qty is not None:
                return qty
        elif value is not None:
            return value
    return None


def _parse_timestamp(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None

    normalized = value.strip()
    try:
        parsed = datetime.strptime(normalized, "%Y-%m-%d %H:%M:%S %z")
    except ValueError:
        try:
            parsed = datetime.fromisoformat(normalized.replace(" ", "T"))
        except ValueError:
            return None

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat()


def _metric_to_event(sample: dict[str, Any]) -> EventCreate | None:
    label = _sample_label(sample)
    if not label or label.lower() == "headphone_audio_exposure":
        return None

    timestamp = _parse_timestamp(_first_value(sample, "date", "timestamp"))
    if timestamp is None:
        return None

    if label.lower() == "blood_pressure":
        systolic = _qty_value(sample, "systolic")
        diastolic = _qty_value(sample, "diastolic")
        if systolic is None or diastolic is None:
            return None
        payload = {
            "type": label,
            "unit": "mmHg",
            "value": systolic,
            "secondary_value": diastolic,
            "secondary_unit": "mmHg",
        }
    else:
        min_value = _first_value(sample, "Min", "min")
        avg_value = _first_value(sample, "Avg", "avg")
        max_value = _first_value(sample, "Max", "max")

        if any(value is not None for value in (min_value, avg_value, max_value)):
            value = avg_value if avg_value is not None else max_value if max_value is not None else min_value
            unit = _first_value(sample, "unit", "Unit")
            if value is None:
                return None
            payload = {
                "type": label,
                "unit": unit,
                "min": min_value,
                "avg": avg_value,
                "max": max_value,
                "value": value,
            }
        else:
            qty = _qty_value(sample, "qty")
            unit = _first_value(sample, "unit", "Unit")
            if qty is None:
                return None
            payload = {
                "type": label,
                "unit": unit,
                "value": qty,
            }

    return EventCreate(
        source="apple_health_import",
        event_type="health.measurement",
        timestamp=timestamp,
        payload=payload,
    )


def _workout_to_event(sample: dict[str, Any]) -> EventCreate | None:
    timestamp = _parse_timestamp(_first_value(sample, "start", "date", "timestamp"))
    if timestamp is None:
        return None

    duration_seconds = _qty_value(sample, "duration")
    distance_qty = _qty_value(sample, "distance")
    calories_qty = _qty_value(sample, "activeEnergyBurned", "active_energy_burned")
    avg_hr = _qty_value(sample, "avgHeartRate", "avg_heart_rate")
    max_hr = _qty_value(sample, "maxHeartRate", "max_heart_rate")
    location = _first_value(sample, "location")
    workout_type = _sample_label(sample)
    payload = {
        "type": workout_type or None,
        "duration_minutes": round(duration_seconds / 60) if duration_seconds is not None else None,
        "distance_km": distance_qty,
        "calories": round(calories_qty) if calories_qty is not None else None,
        "avg_heart_rate": avg_hr,
        "max_heart_rate": max_hr,
        "location": location,
    }

    return EventCreate(
        source="apple_health_import",
        event_type="health.workout",
        timestamp=timestamp,
        payload=payload,
    )


@router.post("/apple-health", response_model=AppleHealthImportResult, status_code=status.HTTP_201_CREATED)
def ingest_apple_health(
    body: AppleHealthImportRequest, db: Session = Depends(get_db)
) -> AppleHealthImportResult:
    received = 0
    inserted = 0

    with db.begin():
        for sample in body.data.metrics:
            received += 1
            try:
                with db.begin_nested():
                    event = _metric_to_event(sample)
                    if event is None:
                        continue
                    _create_event_record(event, db)
                    db.flush()
                inserted += 1
            except Exception:  # noqa: BLE001 - individual mapping failures should be skipped silently
                continue

        for sample in body.data.workouts:
            received += 1
            try:
                with db.begin_nested():
                    event = _workout_to_event(sample)
                    if event is None:
                        continue
                    _create_event_record(event, db)
                    db.flush()
                inserted += 1
            except Exception:  # noqa: BLE001 - individual mapping failures should be skipped silently
                continue

    return AppleHealthImportResult(received=received, inserted=inserted, errors=[])
