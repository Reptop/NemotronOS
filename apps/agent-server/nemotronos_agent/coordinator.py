from __future__ import annotations

import asyncio
from typing import Any

from .event_log import EventLog
from .model_client import ModelClient
from .policy import PolicyEngine
from .task_store import ApprovalRequest, TaskRecord, TaskStore
from .tool_registry import ToolRegistry
from .worker import AgentWorker


class AgentCoordinator:
    def __init__(
        self,
        task_store: TaskStore,
        event_log: EventLog,
        tool_registry: ToolRegistry,
        policy_engine: PolicyEngine,
        model_client: ModelClient,
        worker: AgentWorker,
    ) -> None:
        self.task_store = task_store
        self.event_log = event_log
        self.tool_registry = tool_registry
        self.policy_engine = policy_engine
        self.model_client = model_client
        self.worker = worker

    async def process_task(self, task_id: str) -> None:
        task = self.task_store.get_task(task_id)
        if not task:
            return

        self.task_store.update_task(task_id, state="planning")
        try:
            planned_call = await self.model_client.plan_first_action(
                task.goal,
                self.tool_registry.definitions(),
            )
            self.event_log.add_event(
                "model_requested_tool",
                task_id=task_id,
                tool_name=planned_call.name,
                arguments=planned_call.arguments,
                rationale=planned_call.rationale,
            )

            planning_policy = self.policy_engine.classify(
                planned_call.name,
                planned_call.arguments,
            )
            self.event_log.add_event(
                "policy_checked",
                task_id=task_id,
                tool_name=planned_call.name,
                risk_level=planning_policy.risk_level,
                allowed=planning_policy.allowed,
                reason=planning_policy.reason,
            )
            if not planning_policy.allowed:
                raise RuntimeError(planning_policy.reason)

            result = await self.worker.call_tool(
                task_id=task_id,
                name=planned_call.name,
                arguments=planned_call.arguments,
            )

            if planned_call.name == "fs_plan_changes":
                await self._queue_approval_for_plan(task_id, result)
                return

            if planned_call.name == "app_launch" and self._is_notepad_typing_goal(task.goal):
                typed_result = await self._type_notepad_demo_text(task_id, task.goal)
                self.task_store.update_task(
                    task_id,
                    state="completed",
                    result={
                        "app_launch": result,
                        "keyboard_type": typed_result,
                    },
                )
                self.event_log.add_event(
                    "task_completed",
                    task_id=task_id,
                    result={
                        "app_launch": result,
                        "keyboard_type": typed_result,
                    },
                )
                return

            self.task_store.update_task(task_id, state="completed", result=result)
            self.event_log.add_event("task_completed", task_id=task_id, result=result)
        except Exception as exc:  # noqa: BLE001
            self.task_store.update_task(task_id, state="failed", error=str(exc))
            self.event_log.add_event("task_failed", task_id=task_id, error=str(exc))

    async def approve_task(self, task_id: str, approved: bool) -> TaskRecord:
        task = self.task_store.get_task(task_id)
        if not task:
            raise ValueError("Task not found.")
        if not task.pending_approval:
            raise ValueError("Task is not waiting for approval.")

        if not approved:
            updated_task = self.task_store.update_task(
                task_id,
                state="cancelled",
                pending_approval=None,
                result={"approved": False},
            )
            self.event_log.add_event(
                "task_failed",
                task_id=task_id,
                error="User declined the approval request.",
            )
            return updated_task

        self.event_log.add_event(
            "approval_granted",
            task_id=task_id,
            tool_name=task.pending_approval.tool_name,
            arguments=task.pending_approval.arguments,
        )
        updated_task = self.task_store.update_task(
            task_id,
            state="running",
            pending_approval=None,
        )
        return updated_task

    async def apply_approved_plan(self, task_id: str) -> None:
        task = self.task_store.get_task(task_id)
        if not task:
            return

        pending_action = self._build_apply_arguments(task)
        try:
            policy = self.policy_engine.classify("fs_apply_changes", pending_action)
            self.event_log.add_event(
                "policy_checked",
                task_id=task_id,
                tool_name="fs_apply_changes",
                risk_level=policy.risk_level,
                allowed=policy.allowed,
                reason=policy.reason,
            )
            if not policy.allowed:
                raise RuntimeError(policy.reason)

            result = await self.worker.call_tool(task_id, "fs_apply_changes", pending_action)
            self.task_store.update_task(
                task_id,
                state="completed",
                result=result,
                risk_level=policy.risk_level,
            )
            self.event_log.add_event("task_completed", task_id=task_id, result=result)
        except Exception as exc:  # noqa: BLE001
            self.task_store.update_task(task_id, state="failed", error=str(exc))
            self.event_log.add_event("task_failed", task_id=task_id, error=str(exc))

    async def _queue_approval_for_plan(self, task_id: str, plan_result: dict[str, Any]) -> None:
        apply_arguments = {
            "plan_id": plan_result["plan_id"],
            "create_undo_log": True,
        }
        apply_policy = self.policy_engine.classify("fs_apply_changes", apply_arguments)
        self.event_log.add_event(
            "policy_checked",
            task_id=task_id,
            tool_name="fs_apply_changes",
            risk_level=apply_policy.risk_level,
            allowed=apply_policy.allowed,
            reason=apply_policy.reason,
        )

        approval = ApprovalRequest(
            tool_name="fs_apply_changes",
            arguments=apply_arguments,
            risk_level=apply_policy.risk_level,
            reason=apply_policy.reason,
        )
        self.task_store.update_task(
            task_id,
            state="waiting_for_approval",
            risk_level=apply_policy.risk_level,
            plan_id=plan_result["plan_id"],
            plan_preview=plan_result["proposed_changes"],
            pending_approval=approval,
        )
        self.event_log.add_event(
            "approval_required",
            task_id=task_id,
            tool_name="fs_apply_changes",
            risk_level=apply_policy.risk_level,
            reason=apply_policy.reason,
            plan_id=plan_result["plan_id"],
            proposed_changes=plan_result["proposed_changes"],
        )

    def _build_apply_arguments(self, task: TaskRecord) -> dict[str, Any]:
        if not task.plan_id:
            raise ValueError("Task does not have a stored plan to apply.")
        return {
            "plan_id": task.plan_id,
            "create_undo_log": True,
        }

    def _is_notepad_typing_goal(self, goal: str) -> bool:
        lowered_goal = goal.lower()
        return "notepad" in lowered_goal and "type" in lowered_goal

    async def _type_notepad_demo_text(self, task_id: str, goal: str) -> dict[str, Any]:
        task = self.task_store.get_task(task_id)
        if not task or not task.tool_calls:
            raise RuntimeError("Cannot plan desktop follow-up without the app launch result.")

        planned_call = await self.model_client.plan_next_action(
            goal,
            self.tool_registry.definitions(),
            previous_tool_name="app_launch",
            previous_result=task.tool_calls[-1].result or {},
        )
        arguments = planned_call.arguments
        if task.memory.get("voice_dictation_text"):
            arguments = {
                **arguments,
                "text": task.memory["voice_dictation_text"],
                "text_ref": "task.memory.voice_dictation_text",
            }

        self.event_log.add_event(
            "model_requested_tool",
            task_id=task_id,
            tool_name=planned_call.name,
            arguments=arguments,
            rationale=planned_call.rationale,
        )
        if planned_call.name != "keyboard_type":
            raise RuntimeError(f"Expected keyboard_type follow-up, got {planned_call.name}.")

        policy = self.policy_engine.classify("keyboard_type", arguments)
        self.event_log.add_event(
            "policy_checked",
            task_id=task_id,
            tool_name="keyboard_type",
            risk_level=policy.risk_level,
            allowed=policy.allowed,
            reason=policy.reason,
        )
        if not policy.allowed:
            raise RuntimeError(policy.reason)

        await asyncio.sleep(1.0)
        return await self.worker.call_tool(task_id, "keyboard_type", arguments)
