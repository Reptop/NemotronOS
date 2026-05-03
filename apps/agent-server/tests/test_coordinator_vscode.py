from __future__ import annotations

import asyncio
import unittest
from typing import Any

from nemotronos_agent.coordinator import AgentCoordinator
from nemotronos_agent.event_log import EventLog
from nemotronos_agent.model_client import GeneratedCode, PlannedToolCall
from nemotronos_agent.policy import PolicyEngine
from nemotronos_agent.task_store import TaskStore
from nemotronos_agent.tool_registry import ToolRegistry


class _ModelClient:
    async def plan_first_action(
        self,
        goal: str,
        tool_definitions: list[dict[str, Any]],
    ) -> PlannedToolCall:
        del tool_definitions
        return PlannedToolCall(
            name="vscode_paste_code",
            arguments={"request": goal, "language": "python"},
        )

    async def plan_next_action(
        self,
        goal: str,
        tool_definitions: list[dict[str, Any]],
        previous_tool_name: str,
        previous_result: dict[str, Any],
    ) -> PlannedToolCall:
        raise AssertionError("VS Code code generation should not call plan_next_action.")

    async def generate_code(self, goal: str) -> GeneratedCode:
        del goal
        return GeneratedCode(code="print('hello from vscode')\n", language="python")


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
        return {
            "tool": name,
            "characters": len(str(arguments.get("code", ""))),
            "language": arguments.get("language"),
        }


class CoordinatorVSCodeTests(unittest.TestCase):
    def test_code_generation_pastes_generated_code_into_vscode(self) -> None:
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
        task = task_store.create_task("Code me a Python hello world script.")

        asyncio.run(coordinator.process_task(task.id))

        updated_task = task_store.get_task(task.id)
        self.assertIsNotNone(updated_task)
        assert updated_task is not None
        self.assertEqual(updated_task.state, "completed")
        self.assertEqual(updated_task.memory["generated_code"], "print('hello from vscode')\n")
        self.assertEqual(worker.calls[0][0], "vscode_paste_code")
        self.assertEqual(worker.calls[0][1]["code"], "print('hello from vscode')\n")
        self.assertEqual(worker.calls[0][1]["code_ref"], "task.memory.generated_code")
        self.assertTrue(worker.calls[0][1]["open_new_window"])


if __name__ == "__main__":
    unittest.main()
