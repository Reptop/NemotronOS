from __future__ import annotations

import asyncio
import unittest
from typing import Any

from nemotronos_agent.coordinator import AgentCoordinator, build_safe_action_narration
from nemotronos_agent.event_log import EventLog
from nemotronos_agent.model_client import PlannedToolCall
from nemotronos_agent.policy import PolicyEngine
from nemotronos_agent.task_store import TaskStore
from nemotronos_agent.tool_registry import ToolRegistry


class _ModelClient:
    async def plan_first_action(
        self,
        goal: str,
        tool_definitions: list[dict[str, Any]],
    ) -> PlannedToolCall:
        del goal, tool_definitions
        return PlannedToolCall(
            name="youtube_open",
            arguments={"action": "search", "query": "lofi hip hop"},
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
        raise AssertionError("YouTube follow-up should not call plan_next_action.")


class _Worker:
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
        return {"tool": name, **arguments}


class CoordinatorYouTubeTests(unittest.TestCase):
    def test_youtube_search_auto_clicks_first_video_result(self) -> None:
        task_store = TaskStore()
        worker = _Worker()
        coordinator = AgentCoordinator(
            task_store=task_store,
            event_log=EventLog(),
            tool_registry=ToolRegistry(),
            policy_engine=PolicyEngine(),
            model_client=_ModelClient(),
            worker=worker,
        )
        task = task_store.create_task("Play lofi hip hop on YouTube.")

        asyncio.run(coordinator.process_task(task.id))

        updated_task = task_store.get_task(task.id)
        self.assertIsNotNone(updated_task)
        self.assertEqual(updated_task.state, "completed")
        self.assertEqual(worker.calls[0][0], "youtube_open")
        self.assertEqual(worker.calls[1][0], "youtube_click_video")
        self.assertEqual(worker.calls[1][1]["selection"], "first_video_result")
        self.assertEqual(
            updated_task.memory["voice_response_text"],
            "I opened YouTube and selected a video result.",
        )
        self.assertEqual(
            updated_task.result["voice_response_text"],
            "I opened YouTube and selected a video result.",
        )

    def test_safe_discord_narration_does_not_echo_message_text(self) -> None:
        narration = build_safe_action_narration(
            "discord_send_message",
            result={"sent": True, "characters": 19},
            arguments={"text": "private message text"},
        )

        self.assertEqual(narration, "I sent the message in the active Discord conversation.")
        self.assertNotIn("private", narration)

    def test_browser_narration_uses_site_without_query(self) -> None:
        narration = build_safe_action_narration(
            "browser_open",
            result={"url": "https://www.cnn.com/search?q=private+search"},
            arguments={},
        )

        self.assertEqual(narration, "I opened cnn.com.")
        self.assertNotIn("private", narration)


if __name__ == "__main__":
    unittest.main()
