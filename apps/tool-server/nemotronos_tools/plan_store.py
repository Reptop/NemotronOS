from __future__ import annotations

from threading import Lock
from typing import Any
from uuid import uuid4


class PlanStore:
    def __init__(self) -> None:
        self._plans: dict[str, dict[str, Any]] = {}
        self._lock = Lock()

    def create_plan(self, plan_payload: dict[str, Any]) -> dict[str, Any]:
        plan_id = str(uuid4())
        stored_plan = {"plan_id": plan_id, **plan_payload}
        with self._lock:
            self._plans[plan_id] = stored_plan
        return stored_plan

    def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._plans.get(plan_id)
