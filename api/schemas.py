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
