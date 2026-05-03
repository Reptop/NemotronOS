from __future__ import annotations

import asyncio
import unittest
from typing import Any

from nemotronos_agent.coordinator import AgentCoordinator
from nemotronos_agent.event_log import EventLog
from nemotronos_agent.model_client import PlannedToolCall
from nemotronos_agent.policy import PolicyEngine
from nemotronos_agent.task_store import TaskStore
from nemotronos_agent.tool_registry import ToolRegistry


class _BrowserModelClient:
    def __init__(self) -> None:
        self.next_calls = 0

    async def plan_first_action(
        self,
        goal: str,
        tool_definitions: list[dict[str, Any]],
    ) -> PlannedToolCall:
        del goal, tool_definitions
        return PlannedToolCall(
            name="browser_session_ensure",
            arguments={"start_url": "https://mail.google.com"},
        )

    async def plan_next_action(
        self,
        goal: str,
        tool_definitions: list[dict[str, Any]],
        previous_tool_name: str,
        previous_result: dict[str, Any],
        recent_tool_calls: list[dict[str, Any]] | None = None,
    ) -> PlannedToolCall:
        del goal, tool_definitions, previous_tool_name, previous_result, recent_tool_calls
        self.next_calls += 1
        if self.next_calls == 1:
            return PlannedToolCall(name="browser_click", arguments={"target_id": "t1"})
        return PlannedToolCall(
            name="notify_user",
            arguments={"message": "Browser task complete."},
        )


class _BrowserWorker:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call_tool(
        self,
        task_id: str,
        name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        del task_id
        self.calls.append((name, arguments))
        if name == "browser_session_ensure":
            return {
                "url": "https://mail.google.com",
                "title": "Gmail",
                "load_state": "complete",
                "visible_text_excerpt": "Inbox Compose",
                "targets": [
                    {
                        "target_id": "t1",
                        "tag": "button",
                        "role": "button",
                        "name": "Compose",
                        "text": "Compose",
                        "type": "",
                        "actionable": ["click"],
                        "disabled": False,
                    }
                ],
            }
        if name == "browser_click":
            return {
                "url": "https://mail.google.com",
                "title": "Gmail",
                "load_state": "complete",
                "visible_text_excerpt": "New Message",
                "targets": [],
            }
        return {"tool": name, **arguments}


class CoordinatorBrowserTests(unittest.TestCase):
    def test_browser_mutation_waits_for_approval_then_resumes(self) -> None:
        task_store = TaskStore()
        worker = _BrowserWorker()
        coordinator = AgentCoordinator(
            task_store=task_store,
            event_log=EventLog(),
            tool_registry=ToolRegistry(),
            policy_engine=PolicyEngine(),
            model_client=_BrowserModelClient(),
            worker=worker,
        )
        task = task_store.create_task("Open Gmail and click Compose.")

        asyncio.run(coordinator.process_task(task.id))

        waiting_task = task_store.get_task(task.id)
        self.assertIsNotNone(waiting_task)
        assert waiting_task is not None
        self.assertEqual(waiting_task.state, "waiting_for_approval")
        self.assertEqual(waiting_task.pending_approval.tool_name, "browser_click")
        self.assertEqual(worker.calls[0][0], "browser_session_ensure")

        asyncio.run(coordinator.approve_task(task.id, True))
        asyncio.run(coordinator.run_approved_action(task.id))

        completed_task = task_store.get_task(task.id)
        self.assertIsNotNone(completed_task)
        assert completed_task is not None
        self.assertEqual(completed_task.state, "completed")
        self.assertEqual(
            [call[0] for call in worker.calls],
            ["browser_session_ensure", "browser_click", "notify_user"],
        )
        self.assertEqual(
            completed_task.memory["voice_response_text"],
            "Browser task complete.",
        )
        self.assertEqual(
            completed_task.result["voice_response_text"],
            "Browser task complete.",
        )


if __name__ == "__main__":
    unittest.main()
