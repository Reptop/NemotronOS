from __future__ import annotations

import asyncio
import unittest
from typing import Any

from nemotronos_agent.coordinator import (
    AgentCoordinator,
    build_canvas_assignment_todo_note_text,
)
from nemotronos_agent.event_log import EventLog
from nemotronos_agent.model_client import PlannedToolCall
from nemotronos_agent.policy import PolicyEngine
from nemotronos_agent.task_store import TaskStore
from nemotronos_agent.tool_registry import ToolRegistry


class _CanvasModelClient:
    async def plan_first_action(
        self,
        goal: str,
        tool_definitions: list[dict[str, Any]],
    ) -> PlannedToolCall:
        del goal, tool_definitions
        return PlannedToolCall(
            name="canvas_list_assignments_due_soon",
            arguments={"days_ahead": 7, "include_completed": False},
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
        return PlannedToolCall(name="notify_user", arguments={"message": "done"})

    async def generate_code(self, goal: str) -> Any:
        raise NotImplementedError(goal)


class _CanvasWorker:
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
        if name == "canvas_list_assignments_due_soon":
            return {
                "canvas_base_url": "https://canvas.oregonstate.edu",
                "days_ahead": 7,
                "assignments": [
                    {
                        "name": "Later writeup",
                        "course_name": "Intro to AI",
                        "due_at": "2026-05-08T06:59:00+00:00",
                        "due_display": "Thu May 07, 11:59 PM",
                        "url": "https://canvas.oregonstate.edu/courses/2055259/assignments/2",
                    },
                    {
                        "name": "Soon quiz",
                        "course_name": "Intro to AI",
                        "due_at": "2026-05-04T06:59:00+00:00",
                        "due_display": "Sun May 03, 11:59 PM",
                        "url": "https://canvas.oregonstate.edu/courses/2055259/assignments/1",
                    },
                ],
            }
        if name == "browser_open":
            return {"opened": True, "url": arguments["url"]}
        if name == "sticky_note_create":
            return {"created": True, "characters": len(arguments["text"])}
        return {"tool": name, **arguments}


class CoordinatorCanvasTests(unittest.TestCase):
    def test_canvas_assignment_workflow_creates_sorted_sticky_note(self) -> None:
        task_store = TaskStore()
        worker = _CanvasWorker()
        coordinator = AgentCoordinator(
            task_store=task_store,
            event_log=EventLog(),
            tool_registry=ToolRegistry(),
            policy_engine=PolicyEngine(),
            model_client=_CanvasModelClient(),
            worker=worker,
        )
        task = task_store.create_task(
            "Open up canvas, find assignments due within the next week, "
            "and create a todo sticky note."
        )

        asyncio.run(coordinator.process_task(task.id))

        completed_task = task_store.get_task(task.id)
        self.assertIsNotNone(completed_task)
        assert completed_task is not None
        self.assertEqual(completed_task.state, "completed")
        self.assertEqual(
            [call[0] for call in worker.calls],
            [
                "canvas_list_assignments_due_soon",
                "browser_open",
                "sticky_note_create",
            ],
        )
        sticky_text = worker.calls[2][1]["text"]
        self.assertLess(sticky_text.index("Soon quiz"), sticky_text.index("Later writeup"))
        self.assertIn("Link: https://canvas.oregonstate.edu/courses/2055259/assignments/1", sticky_text)
        self.assertIn("canvas_assignment_todo_note", completed_task.memory)
        self.assertEqual(
            completed_task.memory["voice_response_text"],
            "I opened Canvas and created a local TODO note with the upcoming assignments.",
        )
        self.assertEqual(
            completed_task.result["voice_response_text"],
            "I opened Canvas and created a local TODO note with the upcoming assignments.",
        )

    def test_canvas_note_explains_missing_api_token(self) -> None:
        note = build_canvas_assignment_todo_note_text(
            {
                "canvas_base_url": "https://canvas.oregonstate.edu",
                "days_ahead": 7,
                "needs_canvas_api_token": True,
                "assignments": [],
            }
        )

        self.assertIn("CANVAS_API_TOKEN", note)
        self.assertIn("https://canvas.oregonstate.edu", note)


if __name__ == "__main__":
    unittest.main()
