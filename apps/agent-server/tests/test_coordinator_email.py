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


class _EmailModelClient:
    async def plan_first_action(
        self,
        goal: str,
        tool_definitions: list[dict[str, Any]],
    ) -> PlannedToolCall:
        del goal, tool_definitions
        return PlannedToolCall(
            name="email_create_draft",
            arguments={
                "to": "alex@example.com",
                "subject": "Hackathon update",
                "body": "Private body text.",
            },
        )


class _EmailWorker:
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
        if name == "email_create_draft":
            return {
                "provider": "gmail",
                "created": True,
                "draft_id": "draft-123",
                "draft_url": "https://mail.google.com/mail/u/0/#drafts",
                "sent": False,
            }
        if name == "browser_open":
            return {"opened": True, "url": arguments["url"]}
        return {"tool": name, **arguments}


class CoordinatorEmailTests(unittest.TestCase):
    def test_email_draft_creation_opens_drafts_and_redacts_body(self) -> None:
        task_store = TaskStore()
        event_log = EventLog()
        worker = _EmailWorker()
        coordinator = AgentCoordinator(
            task_store=task_store,
            event_log=event_log,
            tool_registry=ToolRegistry(),
            policy_engine=PolicyEngine(),
            model_client=_EmailModelClient(),
            worker=worker,
        )
        task = task_store.create_task("Compose an email to Alex saying private body text.")

        asyncio.run(coordinator.process_task(task.id))

        completed_task = task_store.get_task(task.id)
        self.assertIsNotNone(completed_task)
        assert completed_task is not None
        self.assertEqual(completed_task.state, "completed")
        self.assertEqual(
            [call[0] for call in worker.calls],
            ["email_create_draft", "browser_open"],
        )
        self.assertEqual(
            worker.calls[0][1]["body_ref"],
            "task.memory.email_draft_body",
        )
        self.assertEqual(
            completed_task.memory["email_draft_body"],
            "Private body text.",
        )
        self.assertEqual(
            completed_task.memory["voice_response_text"],
            "I created a Gmail draft and opened your Drafts page. I did not send it.",
        )
        self.assertEqual(
            completed_task.result["voice_response_text"],
            "I created a Gmail draft and opened your Drafts page. I did not send it.",
        )

        model_events = [
            event
            for event in event_log.list_events()
            if event.type == "model_requested_tool"
            and event.details.get("tool_name") == "email_create_draft"
        ]
        self.assertEqual(
            model_events[0].details["arguments"]["body"],
            "<18 chars from task.memory.email_draft_body>",
        )
        self.assertNotIn("Private body text", str(model_events[0].details))


if __name__ == "__main__":
    unittest.main()
