from __future__ import annotations

import asyncio
import unittest
from typing import Any

from nemotronos_agent.coordinator import (
    AgentCoordinator,
    is_recent_activity_question,
    is_screen_narration_goal,
)
from nemotronos_agent.event_log import EventLog
from nemotronos_agent.model_client import PlannedToolCall
from nemotronos_agent.policy import PolicyEngine
from nemotronos_agent.task_store import TaskStore, ToolCallRecord
from nemotronos_agent.tool_registry import ToolRegistry


class _AccessibilityModelClient:
    async def plan_first_action(
        self,
        goal: str,
        tool_definitions: list[dict[str, Any]],
    ) -> PlannedToolCall:
        del goal, tool_definitions
        return PlannedToolCall(
            name="accessibility_describe_screen",
            arguments={"include_screenshot": True, "max_windows": 12},
            rationale="Route screen-context request to accessibility narration.",
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
        raise AssertionError("Accessibility tests do not use plan_next_action.")

    async def generate_code(self, goal: str) -> Any:
        raise AssertionError(goal)

    async def summarize_screen_context(
        self,
        goal: str,
        screen_context: dict[str, Any],
    ) -> str:
        del goal
        title = screen_context["foreground_window"]["title"]
        return f"You are focused on {title}. There are two safe next actions."

    async def summarize_recent_activity(
        self,
        goal: str,
        activity_context: dict[str, Any],
    ) -> str:
        del goal
        task = activity_context["recent_tasks"][0]
        return f"I just handled: {task['goal']}. It ended as {task['state']}."


class _ClippedAccessibilityModelClient(_AccessibilityModelClient):
    async def summarize_screen_context(
        self,
        goal: str,
        screen_context: dict[str, Any],
    ) -> str:
        del goal, screen_context
        return "**Current view breakdown:**  \n- **Active app/window**: *N"


class _ThinkingRecentActivityModelClient(_AccessibilityModelClient):
    async def summarize_recent_activity(
        self,
        goal: str,
        activity_context: dict[str, Any],
    ) -> str:
        del goal, activity_context
        return "<think>I should reason internally but this should not be spoken."


class _AccessibilityWorker:
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
        if name == "accessibility_describe_screen":
            return {
                "mode": "test",
                "foreground_window": {"title": "Canvas - Assignments"},
                "visible_windows": [
                    {"title": "Canvas - Assignments"},
                    {"title": "NemotronOS Dashboard"},
                ],
            }
        if name == "notify_user":
            return {"message": arguments["message"]}
        return {"tool": name, **arguments}


class CoordinatorAccessibilityTests(unittest.TestCase):
    def test_screen_narration_command_describes_and_notifies(self) -> None:
        task_store = TaskStore()
        worker = _AccessibilityWorker()
        coordinator = AgentCoordinator(
            task_store=task_store,
            event_log=EventLog(),
            tool_registry=ToolRegistry(),
            policy_engine=PolicyEngine(),
            model_client=_AccessibilityModelClient(),
            worker=worker,
        )
        task = task_store.create_task("Computer, what am I looking at?")

        asyncio.run(coordinator.process_task(task.id))

        updated_task = task_store.get_task(task.id)
        self.assertIsNotNone(updated_task)
        assert updated_task is not None
        self.assertEqual(updated_task.state, "completed")
        self.assertEqual(
            [call[0] for call in worker.calls],
            ["accessibility_describe_screen", "notify_user"],
        )
        self.assertIn("Canvas - Assignments", updated_task.memory["voice_response_text"])

    def test_screen_narration_falls_back_when_model_summary_is_clipped(self) -> None:
        task_store = TaskStore()
        worker = _AccessibilityWorker()
        event_log = EventLog()
        coordinator = AgentCoordinator(
            task_store=task_store,
            event_log=event_log,
            tool_registry=ToolRegistry(),
            policy_engine=PolicyEngine(),
            model_client=_ClippedAccessibilityModelClient(),
            worker=worker,
        )
        task = task_store.create_task("Computer, explain this screen.")

        asyncio.run(coordinator.process_task(task.id))

        updated_task = task_store.get_task(task.id)
        self.assertIsNotNone(updated_task)
        assert updated_task is not None
        narration = updated_task.memory["voice_response_text"]
        self.assertEqual(updated_task.state, "completed")
        self.assertIn("You are focused on Canvas - Assignments.", narration)
        self.assertIn("NemotronOS Dashboard", narration)
        self.assertIn("help navigate from the current screen", narration)
        self.assertNotIn("Current view breakdown", narration)
        self.assertNotIn("window-level context", narration)
        self.assertNotIn("This pass", narration)
        summary_events = [
            event
            for event in event_log.list_events()
            if event.type == "accessibility_summary_generated"
        ]
        self.assertEqual(summary_events[-1].details["fallback_reason"], "too_short")

    def test_recent_activity_question_summarizes_previous_task(self) -> None:
        task_store = TaskStore()
        previous = task_store.create_task("Open Canvas.")
        task_store.append_tool_call(
            previous.id,
            ToolCallRecord(
                name="browser_open",
                arguments={"url": "canvas"},
                status="completed",
                result={"opened": True},
            ),
        )
        task_store.update_task(previous.id, state="completed", result={"opened": True})

        worker = _AccessibilityWorker()
        coordinator = AgentCoordinator(
            task_store=task_store,
            event_log=EventLog(),
            tool_registry=ToolRegistry(),
            policy_engine=PolicyEngine(),
            model_client=_AccessibilityModelClient(),
            worker=worker,
        )
        task = task_store.create_task("What did you just do?")

        asyncio.run(coordinator.process_task(task.id))

        updated_task = task_store.get_task(task.id)
        self.assertIsNotNone(updated_task)
        assert updated_task is not None
        self.assertEqual(updated_task.state, "completed")
        self.assertEqual(worker.calls[0][0], "notify_user")
        self.assertIn("Open Canvas", updated_task.memory["voice_response_text"])

    def test_recent_activity_falls_back_when_model_returns_thinking_trace(self) -> None:
        task_store = TaskStore()
        previous = task_store.create_task("Explain the active window.")
        task_store.append_tool_call(
            previous.id,
            ToolCallRecord(
                name="accessibility_describe_screen",
                arguments={"include_screenshot": True},
                status="completed",
                result={"foreground_window": {"title": "Canvas"}},
            ),
        )
        task_store.update_task(previous.id, state="completed", result={"ok": True})

        worker = _AccessibilityWorker()
        event_log = EventLog()
        coordinator = AgentCoordinator(
            task_store=task_store,
            event_log=event_log,
            tool_registry=ToolRegistry(),
            policy_engine=PolicyEngine(),
            model_client=_ThinkingRecentActivityModelClient(),
            worker=worker,
        )
        task = task_store.create_task("What did the AI just do?")

        asyncio.run(coordinator.process_task(task.id))

        updated_task = task_store.get_task(task.id)
        self.assertIsNotNone(updated_task)
        assert updated_task is not None
        narration = updated_task.memory["voice_response_text"]
        self.assertEqual(updated_task.state, "completed")
        self.assertIn("I just handled: Explain the active window.", narration)
        self.assertIn("screen description", narration)
        self.assertNotIn("<think>", narration)
        summary_events = [
            event
            for event in event_log.list_events()
            if event.type == "accessibility_summary_generated"
        ]
        self.assertEqual(summary_events[-1].details["fallback_reason"], "thinking_trace")

    def test_accessibility_intent_detection(self) -> None:
        self.assertTrue(is_screen_narration_goal("Computer, explain this screen."))
        self.assertTrue(is_screen_narration_goal("Computer, explain the active window."))
        self.assertTrue(is_screen_narration_goal("Describe my active window."))
        self.assertTrue(is_screen_narration_goal("What app am I using?"))
        self.assertTrue(is_screen_narration_goal("Read the active window."))
        self.assertTrue(is_screen_narration_goal("Help me see the current page."))
        self.assertTrue(is_screen_narration_goal("Where am I?"))
        self.assertTrue(is_recent_activity_question("What did you just do?"))
        self.assertTrue(is_recent_activity_question("What did the AI just do?"))
        self.assertTrue(is_recent_activity_question("Explain what NemotronOS just did."))
        self.assertFalse(is_screen_narration_goal("Open YouTube."))


if __name__ == "__main__":
    unittest.main()
