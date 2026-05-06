import json
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from auth import require_token
from database import get_db
from models import Event, Source
from schemas import EventCreate, EventQueryParams, EventRead, EventsPage


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


def _parse_query(
    source: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    timestamp_from: str | None = Query(default=None, alias="timestamp_from"),
    timestamp_to: str | None = Query(default=None, alias="timestamp_to"),
    page: int = Query(default=1),
    page_size: int = Query(default=25, alias="page_size"),
    order: str = Query(default="desc"),
) -> EventQueryParams:
    return EventQueryParams(
        source=source,
        event_type=event_type,
        timestamp_from=timestamp_from,
        timestamp_to=timestamp_to,
        page=page,
        page_size=page_size,
        order=order,
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


@router.get("/events", response_model=EventsPage)
def list_events(
    params: EventQueryParams = Depends(_parse_query),
    db: Session = Depends(get_db),
) -> EventsPage:
    conditions = []
    if params.source is not None:
        conditions.append(Event.source == params.source)
    if params.event_type is not None:
        conditions.append(Event.event_type == params.event_type)
    if params.timestamp_from is not None:
        conditions.append(Event.timestamp >= params.timestamp_from)
    if params.timestamp_to is not None:
        conditions.append(Event.timestamp <= params.timestamp_to)

    query = select(Event)
    count_query = select(func.count()).select_from(Event)
    if conditions:
        query = query.where(and_(*conditions))
        count_query = count_query.where(and_(*conditions))

    total = db.scalar(count_query) or 0
    total_pages = max(1, (total + params.page_size - 1) // params.page_size) if total else 0
    offset = (params.page - 1) * params.page_size

    query = query.order_by(
        Event.timestamp.asc() if params.order == "asc" else Event.timestamp.desc(),
        Event.created_at.asc() if params.order == "asc" else Event.created_at.desc(),
    ).offset(offset).limit(params.page_size)

    events = db.scalars(query).all()
    return EventsPage(
        data=[_serialize_event(event) for event in events],
        page=params.page,
        page_size=params.page_size,
        total=total,
        total_pages=total_pages,
    )


@router.get("/events/{event_id}", response_model=EventRead)
def get_event(event_id: str, db: Session = Depends(get_db)) -> EventRead:
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="event not found")
    return _serialize_event(event)
