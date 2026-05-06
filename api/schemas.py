from datetime import datetime
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


SOURCE_PATTERN = re.compile(r"^[a-z0-9]+(?:[._][a-z0-9]+)*$")


def _validate_timestamp(value: str) -> str:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include timezone information")
    return value


class EventCreate(BaseModel):
    source: str = Field(min_length=1, max_length=64)
    event_type: str = Field(min_length=1, max_length=128)
    timestamp: str
    payload: dict[str, Any]

    model_config = ConfigDict(extra="forbid")

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        if not SOURCE_PATTERN.fullmatch(value):
            raise ValueError("source must use lowercase snake_case or dot notation")
        return value

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("event_type cannot be empty")
        return value

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, value: str) -> str:
        return _validate_timestamp(value)


class EventRead(BaseModel):
    id: str
    source: str
    event_type: str
    timestamp: str
    payload: dict[str, Any]
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class EventsPage(BaseModel):
    data: list[EventRead]
    page: int
    page_size: int
    total: int
    total_pages: int


class BatchError(BaseModel):
    index: int
    code: str
    message: str


class BatchIngestResult(BaseModel):
    inserted: int
    errors: list[BatchError]


class BatchIngestRequest(BaseModel):
    events: list[dict[str, Any]]

    model_config = ConfigDict(extra="forbid")

    @field_validator("events")
    @classmethod
    def validate_events_size(cls, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not value:
            raise ValueError("events must not be empty")
        if len(value) > 500:
            raise ValueError("events must not exceed 500 items")
        return value


class EventQueryParams(BaseModel):
    source: str | None = None
    event_type: str | None = None
    timestamp_from: str | None = None
    timestamp_to: str | None = None
    page: int = 1
    page_size: int = 25
    order: str = "desc"

    model_config = ConfigDict(extra="forbid")

    @field_validator("source")
    @classmethod
    def validate_query_source(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not SOURCE_PATTERN.fullmatch(value):
            raise ValueError("source must use lowercase snake_case or dot notation")
        return value

    @field_validator("event_type")
    @classmethod
    def validate_query_event_type(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not value.strip():
            raise ValueError("event_type cannot be empty")
        return value

    @field_validator("timestamp_from", "timestamp_to")
    @classmethod
    def validate_query_timestamp(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _validate_timestamp(value)

    @field_validator("page")
    @classmethod
    def validate_page(cls, value: int) -> int:
        if value < 1:
            raise ValueError("page must be at least 1")
        return value

    @field_validator("page_size")
    @classmethod
    def validate_page_size(cls, value: int) -> int:
        if value < 1 or value > 100:
            raise ValueError("page_size must be between 1 and 100")
        return value

    @field_validator("order")
    @classmethod
    def validate_order(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in {"asc", "desc"}:
            raise ValueError("order must be asc or desc")
        return normalized


class SourceRead(BaseModel):
    id: str
    display_name: str
    description: str | None
    first_seen_at: str
    last_seen_at: str
    event_count: int

    model_config = ConfigDict(from_attributes=True)


class SourcesList(BaseModel):
    data: list[SourceRead]
