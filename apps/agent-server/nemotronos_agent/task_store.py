from __future__ import annotations

from threading import Lock
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


TaskState = Literal[
    "queued",
    "planning",
    "waiting_for_approval",
    "running",
    "paused",
    "blocked",
    "completed",
    "failed",
    "cancelled",
]


def utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


class ToolCallRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    status: str
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str = Field(default_factory=utc_now)


class ApprovalRequest(BaseModel):
    required: bool = True
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    risk_level: str
    reason: str
    requested_at: str = Field(default_factory=utc_now)


class TaskRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    goal: str
    state: TaskState = "queued"
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)
    risk_level: str | None = None
    plan_id: str | None = None
    plan_preview: list[dict[str, Any]] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    pending_approval: ApprovalRequest | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


class TaskStore:
    def __init__(self) -> None:
        self._tasks: dict[str, TaskRecord] = {}
        self._lock = Lock()

    def create_task(self, goal: str) -> TaskRecord:
        task = TaskRecord(goal=goal)
        with self._lock:
            self._tasks[task.id] = task
        return task

    def list_tasks(self) -> list[TaskRecord]:
        with self._lock:
            return sorted(
                self._tasks.values(),
                key=lambda task: task.updated_at,
                reverse=True,
            )

    def get_task(self, task_id: str) -> TaskRecord | None:
        with self._lock:
            return self._tasks.get(task_id)

    def update_task(self, task_id: str, **changes: Any) -> TaskRecord:
        with self._lock:
            task = self._tasks[task_id]
            updated_task = task.model_copy(update={**changes, "updated_at": utc_now()})
            self._tasks[task_id] = updated_task
            return updated_task

    def append_tool_call(self, task_id: str, tool_call: ToolCallRecord) -> TaskRecord:
        with self._lock:
            task = self._tasks[task_id]
            updated_calls = [*task.tool_calls, tool_call]
            updated_task = task.model_copy(
                update={"tool_calls": updated_calls, "updated_at": utc_now()}
            )
            self._tasks[task_id] = updated_task
            return updated_task
