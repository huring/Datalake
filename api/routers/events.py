import json
from uuid import uuid4

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from auth import require_token
from database import get_db
from models import Event, Source
from schemas import EventCreate, EventRead


router = APIRouter(
    prefix="",
    tags=["events"],
    dependencies=[Depends(require_token)],
)


def _humanize_source(source: str) -> str:
    return source.replace("_", " ").replace(".", " ").strip().title()


def _serialize_event(event: Event) -> EventRead:
    return EventRead(
        id=event.id,
        source=event.source,
        event_type=event.event_type,
        timestamp=event.timestamp,
        payload=json.loads(event.payload),
        created_at=event.created_at,
    )


@router.post("/events", status_code=status.HTTP_201_CREATED, response_model=EventRead)
def create_event(body: EventCreate, db: Session = Depends(get_db)) -> EventRead:
    source = db.get(Source, body.source)
    if source is None:
        source = Source(
            id=body.source,
            display_name=_humanize_source(body.source),
            description=None,
            first_seen_at=body.timestamp,
            last_seen_at=body.timestamp,
            event_count=0,
        )
        db.add(source)

    source.last_seen_at = body.timestamp
    source.event_count = (source.event_count or 0) + 1

    event = Event(
        id=str(uuid4()),
        source=body.source,
        event_type=body.event_type,
        timestamp=body.timestamp,
        payload=json.dumps(body.payload, separators=(",", ":")),
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    return _serialize_event(event)
