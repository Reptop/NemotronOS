from __future__ import annotations

from threading import Lock
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from .task_store import utc_now


class EventRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    task_id: str | None = None
    type: str
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now)


class EventLog:
    def __init__(self) -> None:
        self._events: list[EventRecord] = []
        self._lock = Lock()

    def add_event(self, event_type: str, task_id: str | None = None, **details: Any) -> EventRecord:
        event = EventRecord(type=event_type, task_id=task_id, details=details)
        with self._lock:
            self._events.append(event)
        return event

    def list_events(self) -> list[EventRecord]:
        with self._lock:
            return list(reversed(self._events))
