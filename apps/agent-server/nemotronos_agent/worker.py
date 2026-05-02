from __future__ import annotations

from typing import Any

import httpx

from .config import AgentServerSettings
from .event_log import EventLog
from .task_store import TaskStore, ToolCallRecord


class AgentWorker:
    def __init__(
        self,
        settings: AgentServerSettings,
        task_store: TaskStore,
        event_log: EventLog,
    ) -> None:
        self.settings = settings
        self.task_store = task_store
        self.event_log = event_log

    async def call_tool(self, task_id: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.event_log.add_event(
            "tool_started",
            task_id=task_id,
            tool_name=name,
            arguments=arguments,
        )

        try:
            async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
                response = await client.post(
                    f"{self.settings.tool_server_url.rstrip('/')}/tool",
                    json={"name": name, "arguments": arguments},
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            error_text = str(exc)
            self.task_store.append_tool_call(
                task_id,
                ToolCallRecord(
                    name=name,
                    arguments=arguments,
                    status="failed",
                    error=error_text,
                ),
            )
            raise RuntimeError(f"Tool call failed for {name}: {error_text}") from exc

        payload = response.json()
        result = payload["result"]
        self.task_store.append_tool_call(
            task_id,
            ToolCallRecord(
                name=name,
                arguments=arguments,
                status="completed",
                result=result,
            ),
        )
        self.event_log.add_event(
            "tool_completed",
            task_id=task_id,
            tool_name=name,
            result=result,
        )
        return result

    async def fetch_tool_server_health(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
                response = await client.get(f"{self.settings.tool_server_url.rstrip('/')}/health")
                response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            return {
                "status": "error",
                "detail": str(exc),
            }
