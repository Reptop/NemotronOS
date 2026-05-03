from __future__ import annotations

import asyncio
import re
from typing import Any
from urllib.parse import urlparse

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
            if is_recent_activity_question(task.goal):
                result = await self._answer_recent_activity_question(task_id, task.goal)
                self.task_store.update_task(task_id, state="completed", result=result)
                self.event_log.add_event("task_completed", task_id=task_id, result=result)
                return

            planned_call = await self.model_client.plan_first_action(
                task.goal,
                self.tool_registry.definitions(),
            )
            if planned_call.name == "accessibility_describe_screen":
                result = await self._describe_screen_for_accessibility(
                    task_id,
                    task.goal,
                    arguments=planned_call.arguments,
                    rationale=(
                        planned_call.rationale
                        or "Model routed the request to screen accessibility narration."
                    ),
                )
                self.task_store.update_task(task_id, state="completed", result=result)
                self.event_log.add_event("task_completed", task_id=task_id, result=result)
                return

            planned_arguments = self._prepare_planned_arguments(
                task_id,
                planned_call.name,
                planned_call.arguments,
            )
            self.event_log.add_event(
                "model_requested_tool",
                task_id=task_id,
                tool_name=planned_call.name,
                arguments=redact_tool_arguments(planned_call.name, planned_arguments),
                rationale=planned_call.rationale,
            )

            planning_policy = self.policy_engine.classify(
                planned_call.name,
                planned_arguments,
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

            if planned_call.name == "vscode_paste_code":
                result = await self._generate_and_paste_code(
                    task_id,
                    task.goal,
                    planned_arguments,
                )
                self._complete_task(
                    task_id,
                    result,
                    narration=build_safe_action_narration(
                        planned_call.name,
                        result,
                        planned_arguments,
                    ),
                )
                return

            result = await self.worker.call_tool(
                task_id=task_id,
                name=planned_call.name,
                arguments=planned_arguments,
            )

            if planned_call.name == "fs_plan_changes":
                await self._queue_approval_for_plan(task_id, result)
                return

            if planned_call.name == "canvas_list_assignments_due_soon":
                workflow_result = await self._create_canvas_assignment_todo(
                    task_id,
                    result,
                )
                self._complete_task(
                    task_id,
                    workflow_result,
                    narration=(
                        "I opened Canvas and created a local TODO note with the "
                        "upcoming assignments."
                    ),
                )
                return

            if planned_call.name == "app_launch" and self._is_notepad_typing_goal(task.goal):
                typed_result = await self._type_notepad_demo_text(task_id, task.goal)
                self._complete_task(
                    task_id=task_id,
                    result={
                        "app_launch": result,
                        "keyboard_type": typed_result,
                    },
                    narration="I opened Notepad and typed the requested text.",
                )
                return

            if planned_call.name == "youtube_open" and self._should_click_youtube_video(
                planned_arguments
            ):
                clicked_result = await self._click_youtube_video(
                    task_id,
                    planned_arguments,
                )
                self._complete_task(
                    task_id=task_id,
                    result={
                        "youtube_open": result,
                        "youtube_click_video": clicked_result,
                    },
                    narration="I opened YouTube and selected a video result.",
                )
                return

            if planned_call.name in BROWSER_AGENT_TOOLS:
                await self._continue_browser_task(task_id, task.goal, planned_call.name, result)
                return

            if planned_call.name == "email_create_draft":
                workflow_result = await self._open_email_draft_preview(task_id, result)
                self._complete_task(
                    task_id,
                    workflow_result,
                    narration=build_safe_action_narration(
                        planned_call.name,
                        workflow_result,
                        planned_arguments,
                    ),
                )
                return

            self._complete_task(
                task_id,
                result,
                narration=build_safe_action_narration(
                    planned_call.name,
                    result,
                    planned_arguments,
                ),
            )
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
            if pending_action.continue_after_approval and pending_action.tool_name in BROWSER_AGENT_TOOLS:
                await self._continue_browser_task(
                    task_id,
                    task.goal,
                    pending_action.tool_name,
                    result,
                )
                return

            self._complete_task(
                task_id,
                risk_level=policy.risk_level,
                result=result,
                narration=build_safe_action_narration(
                    pending_action.tool_name,
                    result,
                    pending_action.arguments,
                ),
            )
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

    async def _describe_screen_for_accessibility(
        self,
        task_id: str,
        goal: str,
        arguments: dict[str, Any] | None = None,
        rationale: str = "Gather screen context for accessibility narration.",
    ) -> dict[str, Any]:
        arguments = {
            "include_screenshot": True,
            "max_windows": 12,
            **(arguments or {}),
        }
        arguments["include_screenshot"] = bool(arguments.get("include_screenshot", True))
        arguments["max_windows"] = int(arguments.get("max_windows") or 12)
        self.event_log.add_event(
            "model_requested_tool",
            task_id=task_id,
            tool_name="accessibility_describe_screen",
            arguments=arguments,
            rationale=rationale,
        )
        policy = self.policy_engine.classify("accessibility_describe_screen", arguments)
        self.event_log.add_event(
            "policy_checked",
            task_id=task_id,
            tool_name="accessibility_describe_screen",
            risk_level=policy.risk_level,
            allowed=policy.allowed,
            reason=policy.reason,
        )
        if not policy.allowed:
            raise RuntimeError(policy.reason)

        screen_context = await self.worker.call_tool(
            task_id,
            "accessibility_describe_screen",
            arguments,
        )
        fallback_reason = None
        try:
            model_narration = await self.model_client.summarize_screen_context(
                goal,
                screen_context,
            )
            narration, fallback_reason = build_screen_narration_response(
                model_narration,
                screen_context,
            )
        except Exception as exc:  # noqa: BLE001 - screen context is still useful
            fallback_reason = f"model_error:{_format_exception(exc)}"
            narration = fallback_screen_narration(screen_context)
        self.event_log.add_event(
            "accessibility_summary_generated",
            task_id=task_id,
            characters=len(narration),
            fallback_reason=fallback_reason,
        )
        notify_result = await self._notify_user_response(
            task_id=task_id,
            message=narration,
            memory_key="accessibility_narration",
            rationale="Speak and display the screen narration.",
        )
        return {
            "accessibility_describe_screen": screen_context,
            "notify_user": notify_result,
            "voice_response_text": narration,
        }

    async def _answer_recent_activity_question(
        self,
        task_id: str,
        goal: str,
    ) -> dict[str, Any]:
        activity_context = self._recent_activity_context(current_task_id=task_id)
        fallback_reason = None
        try:
            model_summary = await self.model_client.summarize_recent_activity(
                goal,
                activity_context,
            )
            summary, fallback_reason = build_recent_activity_response(
                model_summary,
                activity_context,
            )
        except Exception as exc:  # noqa: BLE001 - recent task context is still useful
            fallback_reason = f"model_error:{_format_exception(exc)}"
            summary = fallback_recent_activity_narration(activity_context)
        self.event_log.add_event(
            "accessibility_summary_generated",
            task_id=task_id,
            characters=len(summary),
            summary_type="recent_activity",
            fallback_reason=fallback_reason,
        )
        notify_result = await self._notify_user_response(
            task_id=task_id,
            message=summary,
            memory_key="recent_activity_narration",
            rationale="Speak and display the recent action explanation.",
        )
        return {
            "recent_activity": activity_context,
            "notify_user": notify_result,
            "voice_response_text": summary,
        }

    async def _notify_user_response(
        self,
        task_id: str,
        message: str,
        memory_key: str,
        rationale: str,
    ) -> dict[str, Any]:
        self._store_voice_response_text(task_id, memory_key, message)
        arguments = {
            "message": message,
            "text_ref": f"task.memory.{memory_key}",
        }
        self.event_log.add_event(
            "model_requested_tool",
            task_id=task_id,
            tool_name="notify_user",
            arguments={
                **arguments,
                "message": f"<{len(message)} chars from task.memory.{memory_key}>",
            },
            rationale=rationale,
        )
        policy = self.policy_engine.classify("notify_user", arguments)
        self.event_log.add_event(
            "policy_checked",
            task_id=task_id,
            tool_name="notify_user",
            risk_level=policy.risk_level,
            allowed=policy.allowed,
            reason=policy.reason,
        )
        if not policy.allowed:
            raise RuntimeError(policy.reason)
        return await self.worker.call_tool(task_id, "notify_user", arguments)

    def _prepare_planned_arguments(
        self,
        task_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        if tool_name != "email_create_draft":
            return arguments

        body = str(arguments.get("body") or "")
        if not body:
            return arguments

        memory_key = "email_draft_body"
        task = self.task_store.get_task(task_id)
        current_memory = dict(task.memory) if task else {}
        self.task_store.update_task(
            task_id,
            memory={**current_memory, memory_key: body},
        )
        return {
            **arguments,
            "body": body,
            "body_ref": f"task.memory.{memory_key}",
        }

    def _complete_task(
        self,
        task_id: str,
        result: dict[str, Any],
        *,
        risk_level: str | None = None,
        narration: str | None = None,
    ) -> None:
        completed_result = self._result_with_safe_action_narration(
            task_id,
            result,
            narration,
        )
        updates: dict[str, Any] = {
            "state": "completed",
            "result": completed_result,
        }
        if risk_level is not None:
            updates["risk_level"] = risk_level
        self.task_store.update_task(task_id, **updates)
        self.event_log.add_event("task_completed", task_id=task_id, result=completed_result)

    def _result_with_safe_action_narration(
        self,
        task_id: str,
        result: dict[str, Any],
        narration: str | None,
    ) -> dict[str, Any]:
        message = clean_spoken_narration(narration or "")
        if not message or result.get("voice_response_text"):
            return result

        self._store_voice_response_text(
            task_id,
            memory_key="safe_action_narration",
            message=message,
        )
        self.event_log.add_event(
            "safe_action_narration_generated",
            task_id=task_id,
            characters=len(message),
        )
        return {**result, "voice_response_text": message}

    def _store_voice_response_text(
        self,
        task_id: str,
        memory_key: str,
        message: str,
    ) -> None:
        task = self.task_store.get_task(task_id)
        current_memory = dict(task.memory) if task else {}
        self.task_store.update_task(
            task_id,
            memory={
                **current_memory,
                memory_key: message,
                "voice_response_text": message,
            },
        )

    def _recent_activity_context(self, current_task_id: str) -> dict[str, Any]:
        recent_tasks = [
            _task_activity_snapshot(task)
            for task in self.task_store.list_tasks()
            if task.id != current_task_id
        ][:5]
        recent_events = [
            _event_activity_snapshot(event)
            for event in self.event_log.list_events()
            if event.task_id != current_task_id
        ][:12]
        return {
            "recent_tasks": recent_tasks,
            "recent_events": recent_events,
        }

    async def _create_canvas_assignment_todo(
        self,
        task_id: str,
        assignment_result: dict[str, Any],
    ) -> dict[str, Any]:
        browser_arguments = {"url": assignment_result.get("canvas_base_url") or "canvas"}
        self.event_log.add_event(
            "model_requested_tool",
            task_id=task_id,
            tool_name="browser_open",
            arguments=browser_arguments,
            rationale="Open Canvas while preparing the assignment todo note.",
        )
        browser_policy = self.policy_engine.classify("browser_open", browser_arguments)
        self.event_log.add_event(
            "policy_checked",
            task_id=task_id,
            tool_name="browser_open",
            risk_level=browser_policy.risk_level,
            allowed=browser_policy.allowed,
            reason=browser_policy.reason,
        )
        if not browser_policy.allowed:
            raise RuntimeError(browser_policy.reason)
        browser_result = await self.worker.call_tool(task_id, "browser_open", browser_arguments)

        note_text = build_canvas_assignment_todo_note_text(assignment_result)
        task = self.task_store.get_task(task_id)
        current_memory = dict(task.memory) if task else {}
        self.task_store.update_task(
            task_id,
            memory={
                **current_memory,
                "canvas_assignment_todo_note": note_text,
            },
        )

        sticky_arguments = {
            "text": note_text,
            "title": "Canvas TODO",
            "text_ref": "task.memory.canvas_assignment_todo_note",
        }
        self.event_log.add_event(
            "model_requested_tool",
            task_id=task_id,
            tool_name="sticky_note_create",
            arguments={
                **sticky_arguments,
                "text": f"<{len(note_text)} chars from task.memory.canvas_assignment_todo_note>",
            },
            rationale="Create a local todo sticky note sorted by earliest Canvas due date.",
        )
        sticky_policy = self.policy_engine.classify("sticky_note_create", sticky_arguments)
        self.event_log.add_event(
            "policy_checked",
            task_id=task_id,
            tool_name="sticky_note_create",
            risk_level=sticky_policy.risk_level,
            allowed=sticky_policy.allowed,
            reason=sticky_policy.reason,
        )
        if not sticky_policy.allowed:
            raise RuntimeError(sticky_policy.reason)

        sticky_result = await self.worker.call_tool(
            task_id,
            "sticky_note_create",
            sticky_arguments,
        )
        return {
            "canvas_list_assignments_due_soon": assignment_result,
            "browser_open": browser_result,
            "sticky_note_create": sticky_result,
            "note_preview": note_text[:1000],
        }

    async def _open_email_draft_preview(
        self,
        task_id: str,
        draft_result: dict[str, Any],
    ) -> dict[str, Any]:
        draft_url = str(draft_result.get("draft_url") or "https://mail.google.com/mail/u/0/#drafts")
        browser_arguments = {"url": draft_url}
        self.event_log.add_event(
            "model_requested_tool",
            task_id=task_id,
            tool_name="browser_open",
            arguments=browser_arguments,
            rationale="Open Gmail drafts so the user can inspect the created email draft.",
        )
        browser_policy = self.policy_engine.classify("browser_open", browser_arguments)
        self.event_log.add_event(
            "policy_checked",
            task_id=task_id,
            tool_name="browser_open",
            risk_level=browser_policy.risk_level,
            allowed=browser_policy.allowed,
            reason=browser_policy.reason,
        )
        if not browser_policy.allowed:
            return {
                "email_create_draft": draft_result,
                "browser_open_error": browser_policy.reason,
            }

        try:
            browser_result = await self.worker.call_tool(task_id, "browser_open", browser_arguments)
        except Exception as exc:  # noqa: BLE001 - the draft was already created
            return {
                "email_create_draft": draft_result,
                "browser_open_error": _format_exception(exc),
            }
        return {
            "email_create_draft": draft_result,
            "browser_open": browser_result,
        }

    async def _generate_and_paste_code(
        self,
        task_id: str,
        goal: str,
        planned_arguments: dict[str, Any],
    ) -> dict[str, Any]:
        generated = await self.model_client.generate_code(goal)
        task = self.task_store.get_task(task_id)
        current_memory = dict(task.memory) if task else {}
        self.task_store.update_task(
            task_id,
            memory={
                **current_memory,
                "generated_code": generated.code,
                "generated_code_language": generated.language,
            },
        )
        self.event_log.add_event(
            "code_generated",
            task_id=task_id,
            language=generated.language,
            characters=len(generated.code),
        )

        arguments = {
            **planned_arguments,
            "code": generated.code,
            "code_ref": "task.memory.generated_code",
            "language": generated.language or planned_arguments.get("language") or "",
            "open_new_window": bool(planned_arguments.get("open_new_window", True)),
        }
        policy = self.policy_engine.classify("vscode_paste_code", arguments)
        self.event_log.add_event(
            "policy_checked",
            task_id=task_id,
            tool_name="vscode_paste_code",
            risk_level=policy.risk_level,
            allowed=policy.allowed,
            reason=policy.reason,
        )
        if not policy.allowed:
            raise RuntimeError(policy.reason)

        return await self.worker.call_tool(task_id, "vscode_paste_code", arguments)

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
            planned_arguments = self._prepare_planned_arguments(
                task_id,
                planned_call.name,
                planned_call.arguments,
            )
            self.event_log.add_event(
                "model_requested_tool",
                task_id=task_id,
                tool_name=planned_call.name,
                arguments=redact_tool_arguments(planned_call.name, planned_arguments),
                rationale=planned_call.rationale,
            )

            policy = self.policy_engine.classify(planned_call.name, planned_arguments)
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
                    arguments=planned_arguments,
                    risk_level=policy.risk_level,
                    reason=policy.reason,
                    continue_after_approval=True,
                )
                return

            result = await self.worker.call_tool(
                task_id=task_id,
                name=planned_call.name,
                arguments=planned_arguments,
            )
            if planned_call.name == "notify_user":
                self._complete_task(
                    task_id,
                    result,
                    narration=str(result.get("message") or "").strip(),
                )
                return
            if planned_call.name not in BROWSER_AGENT_TOOLS:
                self._complete_task(
                    task_id,
                    result,
                    narration=build_safe_action_narration(
                        planned_call.name,
                        result,
                        planned_arguments,
                    ),
                )
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


def build_canvas_assignment_todo_note_text(canvas_result: dict[str, Any]) -> str:
    days_ahead = int(canvas_result.get("days_ahead") or 7)
    base_url = str(canvas_result.get("canvas_base_url") or "https://canvas.oregonstate.edu")
    title = f"Canvas TODO - next {days_ahead} days"
    if canvas_result.get("needs_canvas_api_token"):
        return _fit_note_text(
            "\n".join(
                [
                    title,
                    "",
                    "Could not list assignments yet.",
                    "Set CANVAS_API_TOKEN in .env so NemotronOS can read Canvas due dates.",
                    f"Canvas: {base_url}",
                ]
            )
        )
    if canvas_result.get("lookup_error"):
        return _fit_note_text(
            "\n".join(
                [
                    title,
                    "",
                    "Could not list assignments.",
                    str(canvas_result["lookup_error"]),
                    f"Canvas: {base_url}",
                ]
            )
        )

    assignments = sorted(
        [
            assignment
            for assignment in canvas_result.get("assignments", [])
            if isinstance(assignment, dict)
        ],
        key=lambda assignment: (
            str(assignment.get("due_at") or ""),
            str(assignment.get("course_name") or ""),
            str(assignment.get("name") or ""),
        ),
    )
    if not assignments:
        return "\n".join(
            [
                title,
                "",
                f"No Canvas assignments found due in the next {days_ahead} days.",
                f"Canvas: {base_url}",
            ]
        )

    lines = [title, "", "Earliest due first:"]
    shown_assignments = assignments[:10]
    for index, assignment in enumerate(shown_assignments, start=1):
        due_display = str(assignment.get("due_display") or assignment.get("due_at") or "No due date")
        course_name = str(assignment.get("course_name") or "Canvas")
        name = str(assignment.get("name") or "Untitled assignment")
        url = str(assignment.get("url") or "").strip()
        lines.append(f"{index}. Due {due_display} - {course_name}: {name}")
        lines.append(f"   Link: {url or base_url}")

    remaining_count = len(assignments) - len(shown_assignments)
    if remaining_count > 0:
        lines.extend(["", f"+ {remaining_count} more Canvas assignment(s) due soon."])
    return _fit_note_text("\n".join(lines))


def _fit_note_text(text: str, max_characters: int = 3900) -> str:
    if len(text) <= max_characters:
        return text
    return f"{text[: max_characters - 31].rstrip()}\n... truncated for sticky note"


def build_safe_action_narration(
    tool_name: str,
    result: dict[str, Any] | None = None,
    arguments: dict[str, Any] | None = None,
) -> str | None:
    result = result or {}
    arguments = arguments or {}

    if tool_name == "browser_open":
        target = _spoken_browser_target(
            str(result.get("url") or arguments.get("url") or arguments.get("target") or "")
        )
        return f"I opened {target}." if target else "I opened the requested website."

    if tool_name == "canvas_open_course":
        return "I opened Canvas to the requested course."

    if tool_name == "email_create_draft":
        draft_result = result.get("email_create_draft")
        if not isinstance(draft_result, dict):
            draft_result = result
        provider = str(draft_result.get("provider") or "Gmail").strip()
        provider_name = "Gmail" if provider.lower() == "gmail" else provider
        if result.get("browser_open") or result.get("browser_open_error"):
            return f"I created a {provider_name} draft and opened your Drafts page. I did not send it."
        return f"I created a {provider_name} draft. I did not send it."

    if tool_name == "youtube_open":
        action = str(result.get("action") or arguments.get("action") or "").strip().lower()
        if action in {"video", "specific", "watch", "play"}:
            return "I opened the YouTube video."
        if action == "random":
            return "I opened YouTube for a random video."
        if str(result.get("query") or arguments.get("query") or "").strip():
            return "I opened YouTube search results."
        return "I opened YouTube."

    if tool_name == "discord_send_message":
        return "I sent the message in the active Discord conversation."

    if tool_name == "app_launch":
        app_name = _spoken_app_name(
            str(result.get("app_name") or arguments.get("app_name") or "").strip()
        )
        return f"I opened {app_name}." if app_name else "I opened the requested app."

    if tool_name == "keyboard_type":
        return "I typed the requested text."

    if tool_name == "sticky_note_create":
        title = str(arguments.get("title") or "").strip().lower()
        if "canvas" in title:
            return "I created the Canvas TODO note."
        return "I created a local note."

    if tool_name == "vscode_paste_code":
        language = _spoken_language_name(
            str(result.get("language") or arguments.get("language") or "").strip()
        )
        if language:
            return f"I opened VS Code and inserted the generated {language} code."
        return "I opened VS Code and inserted the generated code."

    if tool_name == "fs_apply_changes":
        return "I applied the approved file organization plan and created an undo log."

    if tool_name == "mouse_click":
        return "I clicked the requested location."

    if tool_name == "browser_click":
        return "I clicked the requested browser element."

    if tool_name == "browser_type":
        return "I typed into the requested browser field."

    if tool_name == "browser_press":
        return "I pressed the requested browser key."

    if tool_name == "browser_select_option":
        return "I selected the requested browser option."

    return None


def redact_tool_arguments(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    redacted = dict(arguments)
    if tool_name == "email_create_draft" and "body" in redacted:
        body = str(redacted.get("body") or "")
        body_ref = str(redacted.get("body_ref") or "task.memory.email_draft_body")
        redacted["body"] = f"<{len(body)} chars from {body_ref}>"
    return redacted


def _spoken_browser_target(target: str) -> str:
    cleaned = target.strip()
    if not cleaned:
        return ""

    alias = cleaned.lower().strip("/ ")
    aliases = {
        "canvas": "Canvas",
        "youtube": "YouTube",
        "google": "Google",
        "gmail": "Gmail",
        "github": "GitHub",
    }
    if alias in aliases:
        return aliases[alias]

    parse_target = cleaned if re.match(r"^[a-z][a-z0-9+.-]*://", cleaned) else f"https://{cleaned}"
    parsed = urlparse(parse_target)
    host = (parsed.netloc or parsed.path).split("/")[0].strip().lower()
    host = re.sub(r"^www\.", "", host)
    if host:
        if host in {"canvas.oregonstate.edu", "oregonstate.instructure.com"}:
            return "Canvas"
        if host.endswith("youtube.com") or host == "youtu.be":
            return "YouTube"
        if host == "mail.google.com":
            return "Gmail"
        return _fit_spoken_fragment(host)

    return _fit_spoken_fragment(cleaned)


def _spoken_app_name(app_name: str) -> str:
    cleaned = app_name.strip().lower()
    return {
        "notepad": "Notepad",
        "calculator": "Calculator",
        "calc": "Calculator",
        "paint": "Paint",
        "mspaint": "Paint",
        "discord": "Discord",
    }.get(cleaned, _fit_spoken_fragment(app_name.strip()))


def _spoken_language_name(language: str) -> str:
    cleaned = language.strip().lower()
    return {
        "py": "Python",
        "python": "Python",
        "js": "JavaScript",
        "javascript": "JavaScript",
        "ts": "TypeScript",
        "typescript": "TypeScript",
        "html": "HTML",
        "css": "CSS",
        "cpp": "C++",
        "c++": "C++",
        "cs": "C#",
        "csharp": "C#",
    }.get(cleaned, _fit_spoken_fragment(language.strip()))


def _fit_spoken_fragment(text: str, max_characters: int = 60) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip().strip(".,;:")
    if len(cleaned) <= max_characters:
        return cleaned
    return f"{cleaned[: max_characters - 3].rstrip(' ./')}..."


def build_screen_narration_response(
    model_narration: str,
    screen_context: dict[str, Any],
) -> tuple[str, str | None]:
    cleaned = clean_spoken_narration(model_narration)
    fallback_reason = incomplete_screen_narration_reason(model_narration, cleaned)
    if fallback_reason:
        return fallback_screen_narration(screen_context), fallback_reason
    return cleaned, None


def build_recent_activity_response(
    model_summary: str,
    activity_context: dict[str, Any],
) -> tuple[str, str | None]:
    cleaned = clean_spoken_narration(model_summary)
    fallback_reason = incomplete_spoken_summary_reason(model_summary, cleaned)
    if fallback_reason:
        return fallback_recent_activity_narration(activity_context), fallback_reason
    return cleaned, None


def clean_spoken_narration(text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        return ""
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"^\s*[-*]\s+", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"[*_`#>]+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def incomplete_screen_narration_reason(raw_text: str, cleaned_text: str) -> str | None:
    stripped = cleaned_text.strip()
    raw_stripped = raw_text.strip()
    if "<think" in raw_stripped.lower():
        return "thinking_trace"
    if not stripped:
        return "empty_model_summary"
    if cleaned_text.strip().lower() in {"current view breakdown", "screen breakdown"}:
        return "heading_only"
    if len(stripped) < 45:
        return "too_short"
    if len(stripped.split()) < 8:
        return "too_few_words"
    if raw_stripped.count("*") % 2:
        return "unbalanced_markdown"
    if stripped[-1] not in ".?!":
        return "missing_sentence_end"
    return None


def incomplete_spoken_summary_reason(raw_text: str, cleaned_text: str) -> str | None:
    stripped = cleaned_text.strip()
    raw_stripped = raw_text.strip()
    if "<think" in raw_stripped.lower():
        return "thinking_trace"
    if not stripped:
        return "empty_model_summary"
    if len(stripped) < 80:
        return "too_short"
    if len(stripped.split()) < 14:
        return "too_few_words"
    if raw_stripped.count("*") % 2:
        return "unbalanced_markdown"
    if stripped[-1] not in ".?!":
        return "missing_sentence_end"
    return None


def fallback_recent_activity_narration(activity_context: dict[str, Any]) -> str:
    recent_tasks = [
        task
        for task in activity_context.get("recent_tasks", [])
        if isinstance(task, dict)
    ]
    if not recent_tasks:
        return "I do not have a previous action to summarize yet."

    task = recent_tasks[0]
    goal = str(task.get("goal") or "your previous request").strip().rstrip(" .?!")
    state = str(task.get("state") or "unknown").strip().lower()
    tool_names = _recent_activity_tool_names(task)
    tool_sentence = ""
    if tool_names:
        tool_sentence = f" I used {_join_spoken_list(tool_names)}."

    if state == "completed":
        return f"I just handled: {goal}. It completed successfully.{tool_sentence}"
    if state in {"planning", "running", "queued"}:
        return f"I was working on: {goal}. It is currently {state}.{tool_sentence}"
    if state == "waiting_for_approval":
        return f"I was working on: {goal}. It is waiting for your approval.{tool_sentence}"
    if state in {"failed", "cancelled", "blocked"}:
        error = str(task.get("error") or "").strip()
        if error:
            return f"I tried to handle: {goal}. It ended as {state} because {error}."
        return f"I tried to handle: {goal}. It ended as {state}.{tool_sentence}"
    return f"The last task was: {goal}. It is currently {state}.{tool_sentence}"


def _recent_activity_tool_names(task: dict[str, Any]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    tool_calls = task.get("tool_calls")
    if not isinstance(tool_calls, list):
        return names
    for call in tool_calls:
        if not isinstance(call, dict):
            continue
        name = str(call.get("name") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(_spoken_tool_name(name))
    return names


def _spoken_tool_name(name: str) -> str:
    return {
        "accessibility_describe_screen": "screen description",
        "notify_user": "a spoken response",
    }.get(name, name.replace("_", " "))


def fallback_screen_narration(screen_context: dict[str, Any]) -> str:
    foreground = screen_context.get("foreground_window") or {}
    foreground_title = _clean_window_title(str(foreground.get("title") or "your desktop"))
    if foreground_title.lower() == "your desktop":
        first_sentence = "You are on the Windows desktop."
    else:
        first_sentence = f"You are focused on {foreground_title}."

    focused_sentence = _focused_element_sentence(screen_context, foreground_title)
    visible_titles = _important_visible_window_titles(screen_context, foreground_title)

    sentences = [first_sentence]
    if focused_sentence:
        sentences.append(focused_sentence)
    if visible_titles:
        sentences.append(f"Other visible windows include {_join_spoken_list(visible_titles)}.")

    sentences.append(
        "You can ask me to switch apps, open one of these windows, or help navigate "
        "from the current screen."
    )
    return " ".join(sentences)


def _focused_element_sentence(screen_context: dict[str, Any], foreground_title: str) -> str:
    focused = screen_context.get("focused_element")
    if not isinstance(focused, dict):
        return ""
    role = str(focused.get("role") or "").strip().lower()
    name = _clean_window_title(str(focused.get("name") or ""))
    if not role and not name:
        return ""
    if name and name.lower() != foreground_title.lower():
        if role:
            return f"The focused element is a {role} named {name}."
        return f"The focused element is named {name}."
    if role and role != "window":
        return f"The focused element is a {role}."
    return ""


def _important_visible_window_titles(
    screen_context: dict[str, Any],
    foreground_title: str,
    max_titles: int = 5,
) -> list[str]:
    visible_windows = screen_context.get("visible_windows")
    if not isinstance(visible_windows, list):
        return []

    titles: list[str] = []
    seen: set[str] = {foreground_title.lower()}
    for window in visible_windows:
        if not isinstance(window, dict) or not _window_has_visible_area(window):
            continue
        title = _clean_window_title(str(window.get("title") or ""))
        if not title or _is_noisy_window_title(title):
            continue
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        titles.append(title)
        if len(titles) >= max_titles:
            break
    return titles


def _window_has_visible_area(window: dict[str, Any]) -> bool:
    bounds = window.get("bounds")
    if not isinstance(bounds, dict):
        return True
    try:
        left = int(bounds.get("left", 0))
        top = int(bounds.get("top", 0))
        right = int(bounds.get("right", 0))
        bottom = int(bounds.get("bottom", 0))
    except (TypeError, ValueError):
        return True
    if left <= -30000 or top <= -30000:
        return False
    return right > left and bottom > top


def _is_noisy_window_title(title: str) -> bool:
    lowered = title.lower()
    return lowered in {
        "rzmonitorforegroundwindow",
        "windows input experience",
        "program manager",
    }


def _clean_window_title(title: str, max_characters: int = 110) -> str:
    cleaned = re.sub(r"\s+", " ", title).strip()
    if len(cleaned) <= max_characters:
        return cleaned
    return f"{cleaned[: max_characters - 3].rstrip(' .')}..."


def _join_spoken_list(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return f"{', '.join(items[:-1])}, and {items[-1]}"


def is_screen_narration_goal(goal: str) -> bool:
    lowered_goal = goal.lower()
    return bool(
        re.search(
            r"\b(?:what(?:'s| is)?\s+(?:on\s+)?(?:my\s+)?screen|"
            r"what\s+am\s+i\s+looking\s+at|what\s+do\s+you\s+see|"
            r"describe\s+(?:my\s+|this\s+|the\s+|current\s+)?screen|"
            r"explain\s+(?:my\s+|this\s+|the\s+|current\s+)?screen|"
            r"(?:explain|describe|summarize|read|tell\s+me\s+about)\s+"
            r"(?:(?:my|the|this|current|active|foreground)\s+)*"
            r"(?:active\s+)?(?:window|app|application|desktop|screen|page|view)|"
            r"what\s+(?:window|app|application)\s+am\s+i\s+(?:on|in|using)|"
            r"what(?:'s| is)?\s+(?:this|the|my|active)\s+window|"
            r"read\s+(?:the\s+)?(?:active\s+)?window|"
            r"guide\s+me\s+through\s+(?:this\s+)?(?:screen|page|window)|"
            r"screen\s+context)\b",
            lowered_goal,
        )
    )


def is_recent_activity_question(goal: str) -> bool:
    lowered_goal = goal.lower()
    return bool(
        re.search(
            r"\b(?:what\s+did\s+(?:you|the\s+ai|ai|the\s+agent|"
            r"the\s+assistant|nemotron|nemotron\s*os)\s+(?:just\s+)?do|"
            r"what\s+happened|explain\s+what\s+(?:you|the\s+ai|ai|"
            r"the\s+agent|the\s+assistant|nemotron|nemotron\s*os)\s+"
            r"(?:just\s+)?did|describe\s+what\s+(?:you|the\s+ai|ai|"
            r"the\s+agent|the\s+assistant|nemotron|nemotron\s*os)\s+"
            r"(?:just\s+)?did|what\s+action\s+did\s+(?:you|the\s+ai|ai|"
            r"the\s+agent|the\s+assistant|nemotron|nemotron\s*os)\s+take)\b",
            lowered_goal,
        )
    )


def _task_activity_snapshot(task: TaskRecord) -> dict[str, Any]:
    return {
        "id": task.id,
        "goal": task.goal,
        "state": task.state,
        "error": task.error,
        "tool_calls": [
            {
                "name": call.name,
                "status": call.status,
                "error": call.error,
                "result": _truncate_activity_value(call.result),
            }
            for call in task.tool_calls[-5:]
        ],
        "result": _truncate_activity_value(task.result),
        "updated_at": task.updated_at,
    }


def _event_activity_snapshot(event: Any) -> dict[str, Any]:
    return {
        "type": event.type,
        "task_id": event.task_id,
        "details": _truncate_activity_value(event.details),
        "created_at": event.created_at,
    }


def _truncate_activity_value(value: Any, max_characters: int = 1200) -> Any:
    if value is None:
        return None
    text = str(value)
    if len(text) <= max_characters:
        return value
    return f"{text[: max_characters - 24]}... <truncated>"


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
