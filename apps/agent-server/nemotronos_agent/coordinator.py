from __future__ import annotations

import asyncio
import re
from typing import Any

from .event_log import EventLog
from .model_client import ModelClient
from .policy import PolicyEngine
from .task_store import ApprovalRequest, TaskRecord, TaskStore
from .tool_registry import ToolRegistry
from .worker import AgentWorker

BROWSER_AGENT_TOOLS = {
    "browser_session_ensure",
    "browser_navigate",
    "browser_snapshot",
    "browser_click",
    "browser_type",
    "browser_select_option",
    "browser_press",
}
BROWSER_AGENT_MUTATION_TOOLS = {
    "browser_click",
    "browser_type",
    "browser_select_option",
    "browser_press",
}
BROWSER_AGENT_STEP_BUDGET = 8
EMAIL_AGENT_MUTATION_TOOLS = {
    "gmail_compose_draft",
    "gmail_send_current_draft",
}


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

            if planned_call.name in BROWSER_AGENT_MUTATION_TOOLS:
                self._queue_pending_tool_approval(
                    task_id=task_id,
                    tool_name=planned_call.name,
                    arguments=planned_call.arguments,
                    risk_level=planning_policy.risk_level,
                    reason=planning_policy.reason,
                    continue_after_approval=True,
                )
                return
            if planned_call.name in EMAIL_AGENT_MUTATION_TOOLS:
                self._queue_pending_tool_approval(
                    task_id=task_id,
                    tool_name=planned_call.name,
                    arguments=planned_call.arguments,
                    risk_level=planning_policy.risk_level,
                    reason=planning_policy.reason,
                    continue_after_approval=False,
                )
                return

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

            if planned_call.name == "youtube_open" and self._should_click_youtube_video(
                planned_call.arguments
            ):
                clicked_result = await self._click_youtube_video(
                    task_id,
                    planned_call.arguments,
                )
                self.task_store.update_task(
                    task_id,
                    state="completed",
                    result={
                        "youtube_open": result,
                        "youtube_click_video": clicked_result,
                    },
                )
                self.event_log.add_event(
                    "task_completed",
                    task_id=task_id,
                    result={
                        "youtube_open": result,
                        "youtube_click_video": clicked_result,
                    },
                )
                return

            if planned_call.name in BROWSER_AGENT_TOOLS:
                await self._continue_browser_task(task_id, task.goal, planned_call.name, result)
                return

            self.task_store.update_task(task_id, state="completed", result=result)
            self.event_log.add_event("task_completed", task_id=task_id, result=result)
        except Exception as exc:  # noqa: BLE001
            error = _format_exception(exc)
            self.task_store.update_task(task_id, state="failed", error=error)
            self.event_log.add_event("task_failed", task_id=task_id, error=error)

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
            approved_action=task.pending_approval,
        )
        return updated_task

    async def apply_approved_plan(self, task_id: str) -> None:
        await self.run_approved_action(task_id)

    async def run_approved_action(self, task_id: str) -> None:
        task = self.task_store.get_task(task_id)
        if not task:
            return

        pending_action = task.approved_action
        if not pending_action:
            return

        try:
            policy = self.policy_engine.classify(
                pending_action.tool_name,
                pending_action.arguments,
            )
            self.event_log.add_event(
                "policy_checked",
                task_id=task_id,
                tool_name=pending_action.tool_name,
                risk_level=policy.risk_level,
                allowed=policy.allowed,
                reason=policy.reason,
            )
            if not policy.allowed:
                raise RuntimeError(policy.reason)

            result = await self.worker.call_tool(
                task_id,
                pending_action.tool_name,
                pending_action.arguments,
            )
            self.task_store.update_task(
                task_id,
                approved_action=None,
                risk_level=policy.risk_level,
            )
            task = self.task_store.get_task(task_id)
            if not task:
                return
            if (
                pending_action.tool_name == "gmail_compose_draft"
                and self._is_send_email_goal(task.goal)
            ):
                await self._queue_send_email_approval(task_id)
                return
            if pending_action.continue_after_approval and pending_action.tool_name in BROWSER_AGENT_TOOLS:
                await self._continue_browser_task(
                    task_id,
                    task.goal,
                    pending_action.tool_name,
                    result,
                )
                return

            self.task_store.update_task(
                task_id,
                state="completed",
                result=result,
                risk_level=policy.risk_level,
            )
            self.event_log.add_event("task_completed", task_id=task_id, result=result)
        except Exception as exc:  # noqa: BLE001
            error = _format_exception(exc)
            self.task_store.update_task(task_id, state="failed", error=error, approved_action=None)
            self.event_log.add_event("task_failed", task_id=task_id, error=error)

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
            continue_after_approval=False,
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

    def _should_click_youtube_video(self, arguments: dict[str, Any]) -> bool:
        action = str(arguments.get("action", "")).strip().lower()
        return action in {"search", "specific", "video", "play", "watch", "random"}
    
    def _is_send_email_goal(self, goal: str) -> bool:
        return bool(
            re.search(
                r"\b(send|send it|send the email|email it|deliver)\b",
                goal,
                flags=re.IGNORECASE,
            )
        )
    
    async def _queue_send_email_approval(self, task_id: str) -> None:
        arguments: dict[str, Any] = {}
        policy = self.policy_engine.classify("gmail_send_current_draft", arguments)

        self.event_log.add_event(
            "model_requested_tool",
            task_id=task_id,
            tool_name="gmail_send_current_draft",
            arguments=arguments,
            rationale="Send the Gmail draft after the user requested sending the email.",
        )
        self.event_log.add_event(
            "policy_checked",
            task_id=task_id,
            tool_name="gmail_send_current_draft",
            risk_level=policy.risk_level,
            allowed=policy.allowed,
            reason=policy.reason,
        )

        if not policy.allowed:
            raise RuntimeError(policy.reason)

        self._queue_pending_tool_approval(
            task_id=task_id,
            tool_name="gmail_send_current_draft",
            arguments=arguments,
            risk_level=policy.risk_level,
            reason=policy.reason,
            continue_after_approval=False,
        )


    async def _click_youtube_video(
        self,
        task_id: str,
        youtube_arguments: dict[str, Any],
    ) -> dict[str, Any]:
        action = str(youtube_arguments.get("action", "")).strip().lower()
        selection = "random_visible" if action == "random" else "first_video_result"
        arguments = {
            "selection": selection,
            "wait_seconds": 5.0,
        }

        self.event_log.add_event(
            "model_requested_tool",
            task_id=task_id,
            tool_name="youtube_click_video",
            arguments=arguments,
            rationale="Click a visible YouTube video after opening the relevant page.",
        )
        policy = self.policy_engine.classify("youtube_click_video", arguments)
        self.event_log.add_event(
            "policy_checked",
            task_id=task_id,
            tool_name="youtube_click_video",
            risk_level=policy.risk_level,
            allowed=policy.allowed,
            reason=policy.reason,
        )
        if not policy.allowed:
            raise RuntimeError(policy.reason)

        return await self.worker.call_tool(task_id, "youtube_click_video", arguments)

    async def _type_notepad_demo_text(self, task_id: str, goal: str) -> dict[str, Any]:
        task = self.task_store.get_task(task_id)
        if not task or not task.tool_calls:
            raise RuntimeError("Cannot plan desktop follow-up without the app launch result.")

        arguments, rationale = self._notepad_follow_up_arguments(task, goal)
        if arguments is None:
            planned_call = await self.model_client.plan_next_action(
                goal,
                self.tool_registry.definitions(),
                previous_tool_name="app_launch",
                previous_result=task.tool_calls[-1].result or {},
            )
            arguments = planned_call.arguments
            rationale = planned_call.rationale
            if task.memory.get("voice_dictation_text"):
                arguments = {
                    **arguments,
                    "text": task.memory["voice_dictation_text"],
                    "text_ref": "task.memory.voice_dictation_text",
                }

        self.event_log.add_event(
            "model_requested_tool",
            task_id=task_id,
            tool_name="keyboard_type",
            arguments=arguments,
            rationale=rationale,
        )

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

    async def _continue_browser_task(
        self,
        task_id: str,
        goal: str,
        previous_tool_name: str,
        previous_result: dict[str, Any],
    ) -> None:
        while True:
            task = self.task_store.get_task(task_id)
            if not task:
                return
            if self._browser_step_count(task) >= BROWSER_AGENT_STEP_BUDGET:
                raise RuntimeError(
                    f"Browser automation exceeded the step budget of {BROWSER_AGENT_STEP_BUDGET}."
                )

            planned_call = await self.model_client.plan_next_action(
                goal,
                self.tool_registry.definitions(),
                previous_tool_name=previous_tool_name,
                previous_result=previous_result,
                recent_tool_calls=self._recent_tool_history(task),
            )
            self.event_log.add_event(
                "model_requested_tool",
                task_id=task_id,
                tool_name=planned_call.name,
                arguments=planned_call.arguments,
                rationale=planned_call.rationale,
            )

            policy = self.policy_engine.classify(planned_call.name, planned_call.arguments)
            self.event_log.add_event(
                "policy_checked",
                task_id=task_id,
                tool_name=planned_call.name,
                risk_level=policy.risk_level,
                allowed=policy.allowed,
                reason=policy.reason,
            )
            if not policy.allowed:
                raise RuntimeError(policy.reason)

            if planned_call.name in BROWSER_AGENT_MUTATION_TOOLS:
                self._queue_pending_tool_approval(
                    task_id=task_id,
                    tool_name=planned_call.name,
                    arguments=planned_call.arguments,
                    risk_level=policy.risk_level,
                    reason=policy.reason,
                    continue_after_approval=True,
                )
                return
            if planned_call.name in EMAIL_AGENT_MUTATION_TOOLS:
                self._queue_pending_tool_approval(
                    task_id=task_id,
                    tool_name=planned_call.name,
                    arguments=planned_call.arguments,
                    risk_level=policy.risk_level,
                    reason=policy.reason,
                    continue_after_approval=False,
                )
                return

            result = await self.worker.call_tool(
                task_id=task_id,
                name=planned_call.name,
                arguments=planned_call.arguments,
            )
            if planned_call.name == "notify_user":
                self.task_store.update_task(task_id, state="completed", result=result)
                self.event_log.add_event("task_completed", task_id=task_id, result=result)
                return
            if planned_call.name not in BROWSER_AGENT_TOOLS:
                self.task_store.update_task(task_id, state="completed", result=result)
                self.event_log.add_event("task_completed", task_id=task_id, result=result)
                return

            previous_tool_name = planned_call.name
            previous_result = result

    def _notepad_follow_up_arguments(
        self,
        task: TaskRecord,
        goal: str,
    ) -> tuple[dict[str, Any] | None, str | None]:
        if task.memory.get("voice_dictation_text"):
            return (
                {
                    "text": task.memory["voice_dictation_text"],
                    "text_ref": "task.memory.voice_dictation_text",
                },
                "Use the stored voice dictation text for the Notepad follow-up.",
            )

        extracted_text = extract_notepad_text(goal)
        if not extracted_text:
            return None, None

        return (
            {"text": extracted_text},
            "Extract the quoted or trailing literal text from the Notepad request.",
        )

    def _queue_pending_tool_approval(
        self,
        task_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        risk_level: str,
        reason: str,
        continue_after_approval: bool,
    ) -> None:
        approval = ApprovalRequest(
            tool_name=tool_name,
            arguments=arguments,
            risk_level=risk_level,
            reason=reason,
            continue_after_approval=continue_after_approval,
        )
        self.task_store.update_task(
            task_id,
            state="waiting_for_approval",
            risk_level=risk_level,
            pending_approval=approval,
        )
        self.event_log.add_event(
            "approval_required",
            task_id=task_id,
            tool_name=tool_name,
            risk_level=risk_level,
            reason=reason,
            arguments=arguments,
        )

    def _browser_step_count(self, task: TaskRecord) -> int:
        return sum(1 for call in task.tool_calls if call.name in BROWSER_AGENT_TOOLS)

    def _recent_tool_history(self, task: TaskRecord) -> list[dict[str, Any]]:
        history = []
        for call in task.tool_calls[-5:]:
            history.append(
                {
                    "name": call.name,
                    "arguments": call.arguments,
                    "status": call.status,
                    "result": call.result,
                }
            )
        return history


def extract_notepad_text(goal: str) -> str | None:
    quoted_match = re.search(r'"([^"\r\n]+)"', goal)
    if quoted_match:
        text = quoted_match.group(1).strip()
        if text:
            return text

    command_match = re.search(
        r"\btype\b(?:\s+(?:in|out|down|up|this|that|the|text|note))*"
        r"\s*[:,-]?\s+(.+?)(?:\s+(?:in|on)\s+it\.?)?$",
        goal,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not command_match:
        return None

    text = command_match.group(1).strip(" \t\n\r\"'")
    return text or None


def _format_exception(exc: Exception) -> str:
    message = str(exc).strip()
    if message:
        return message
    return f"{exc.__class__.__name__} raised without a message."


    
