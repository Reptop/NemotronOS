from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel

from .assistant_personality import with_assistant_personality
from .config import AgentServerSettings


class PlannedToolCall(BaseModel):
    name: str
    arguments: dict[str, Any]
    rationale: str | None = None


class GeneratedCode(BaseModel):
    code: str
    language: str | None = None


class ModelClient(ABC):
    @abstractmethod
    async def plan_first_action(
        self, goal: str, tool_definitions: list[dict[str, Any]]
    ) -> PlannedToolCall:
        raise NotImplementedError

    @abstractmethod
    async def plan_next_action(
        self,
        goal: str,
        tool_definitions: list[dict[str, Any]],
        previous_tool_name: str,
        previous_result: dict[str, Any],
        recent_tool_calls: list[dict[str, Any]] | None = None,
    ) -> PlannedToolCall:
        raise NotImplementedError

    @abstractmethod
    async def generate_code(self, goal: str) -> GeneratedCode:
        raise NotImplementedError

    @abstractmethod
    async def summarize_screen_context(
        self,
        goal: str,
        screen_context: dict[str, Any],
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    async def summarize_recent_activity(
        self,
        goal: str,
        activity_context: dict[str, Any],
    ) -> str:
        raise NotImplementedError


class MockModelClient(ModelClient):
    def __init__(self, settings: AgentServerSettings) -> None:
        self.settings = settings

    async def plan_first_action(
        self, goal: str, tool_definitions: list[dict[str, Any]]
    ) -> PlannedToolCall:
        del tool_definitions

        if _looks_like_downloads_organization_goal(goal):
            return PlannedToolCall(
                name="fs_plan_changes",
                arguments={
                    "root_path": self.settings.default_downloads_path,
                    "goal": goal,
                    "allowed_operations": ["mkdir", "move"],
                },
                rationale="Create a dry-run organization plan for the Downloads folder first.",
            )

        notepad_arguments = _extract_notepad_launch_arguments(goal)
        if notepad_arguments:
            return PlannedToolCall(
                name="app_launch",
                arguments=notepad_arguments,
                rationale="Open Notepad so the coordinator can type the requested text.",
            )

        code_arguments = _extract_code_request_arguments(goal)
        if code_arguments:
            return PlannedToolCall(
                name="vscode_paste_code",
                arguments=code_arguments,
                rationale="Generate code and open it in a fresh VS Code window.",
            )

        email_arguments = _extract_email_draft_arguments(goal)
        if email_arguments:
            return PlannedToolCall(
                name="email_create_draft",
                arguments=email_arguments,
                rationale="Create a Gmail draft without sending it.",
            )

        gmail_call = _extract_gmail_action(goal)
        if gmail_call:
            return gmail_call

        discord_arguments = _extract_discord_message_arguments(goal)
        if discord_arguments:
            return PlannedToolCall(
                name="discord_send_message",
                arguments=discord_arguments,
                rationale="Send the requested message to the active Discord conversation.",
            )

        canvas_assignment_arguments = _extract_canvas_assignment_arguments(goal)
        if canvas_assignment_arguments:
            return PlannedToolCall(
                name="canvas_list_assignments_due_soon",
                arguments=canvas_assignment_arguments,
                rationale="List Canvas assignments due soon before creating a todo note.",
            )

        canvas_arguments = _extract_canvas_arguments(goal)
        if canvas_arguments:
            return PlannedToolCall(
                name="canvas_open_course",
                arguments=canvas_arguments,
                rationale="Open Canvas and navigate to the requested course.",
            )

        accessibility_arguments = _extract_accessibility_describe_arguments(goal)
        if accessibility_arguments:
            return PlannedToolCall(
                name="accessibility_describe_screen",
                arguments=accessibility_arguments,
                rationale="Describe the current desktop context for accessibility.",
            )

        youtube_arguments = _extract_youtube_arguments(goal)
        if youtube_arguments:
            return PlannedToolCall(
                name="youtube_open",
                arguments=youtube_arguments,
                rationale="Open or search YouTube for the requested video.",
            )

        browser_target = _extract_browser_target(goal)
        if browser_target:
            return PlannedToolCall(
                name="browser_open",
                arguments={"url": browser_target},
                rationale="Open the requested website in the default browser.",
            )

        return PlannedToolCall(
            name="notify_user",
            arguments={
                "message": f"Mock mode does not have a richer plan for: {goal}",
            },
            rationale="Fallback response for an unsupported mock goal.",
        )

    async def plan_next_action(
        self,
        goal: str,
        tool_definitions: list[dict[str, Any]],
        previous_tool_name: str,
        previous_result: dict[str, Any],
        recent_tool_calls: list[dict[str, Any]] | None = None,
    ) -> PlannedToolCall:
        del tool_definitions, previous_result, recent_tool_calls
        if previous_tool_name == "app_launch":
            return PlannedToolCall(
                name="keyboard_type",
                arguments={"text": goal},
                rationale="Mock follow-up typing action.",
            )
        return PlannedToolCall(
            name="notify_user",
            arguments={"message": f"Mock mode has no follow-up action for: {goal}"},
            rationale="Fallback response for an unsupported mock follow-up.",
        )

    async def generate_code(self, goal: str) -> GeneratedCode:
        language = _guess_code_language(goal) or "python"
        return GeneratedCode(
            language=language,
            code=(
                "# Mock NemotronOS code generation\n"
                f"# Request: {goal}\n\n"
                "def main():\n"
                '    print("Hello from NemotronOS.")\n\n'
                'if __name__ == "__main__":\n'
                "    main()\n"
            ),
        )

    async def summarize_screen_context(
        self,
        goal: str,
        screen_context: dict[str, Any],
    ) -> str:
        del goal
        foreground = screen_context.get("foreground_window") or {}
        title = str(foreground.get("title") or "the current desktop").strip()
        summary = str(screen_context.get("screen_summary") or "").strip()
        if summary:
            return summary
        return f"You appear to be focused on {title}. I can also see other desktop windows listed in the context."

    async def summarize_recent_activity(
        self,
        goal: str,
        activity_context: dict[str, Any],
    ) -> str:
        del goal
        recent_tasks = activity_context.get("recent_tasks") or []
        if not recent_tasks:
            return "I do not have a previous action to summarize yet."
        task = recent_tasks[0]
        state = str(task.get("state") or "unknown")
        goal_text = str(task.get("goal") or "the previous request")
        tools = ", ".join(str(call.get("name")) for call in task.get("tool_calls", []))
        if tools:
            return f"The last task was: {goal_text}. It finished with state {state} after using {tools}."
        return f"The last task was: {goal_text}. It finished with state {state}."


class OpenAICompatibleModelClient(ModelClient):
    def __init__(self, settings: AgentServerSettings) -> None:
        self.settings = settings

    async def plan_first_action(
        self, goal: str, tool_definitions: list[dict[str, Any]]
    ) -> PlannedToolCall:
        force_downloads_plan = self._should_force_downloads_plan(goal)

        payload = {
            "model": self.settings.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": self._first_action_system_prompt(),
                },
                {"role": "user", "content": goal},
            ],
            "tools": [
                {"type": "function", "function": definition}
                for definition in tool_definitions
            ],
            "tool_choice": self._tool_choice(force_downloads_plan),
            "max_tokens": 256,
        }

        try:
            planned_call = await self._request_tool_call(payload, tool_definitions)
        except (RuntimeError, ValueError, json.JSONDecodeError):
            try:
                planned_call = await self._request_json_tool_call(
                    goal,
                    tool_definitions,
                    force_downloads_plan,
                )
            except (httpx.HTTPError, RuntimeError, ValueError, json.JSONDecodeError):
                if force_downloads_plan:
                    raise
                planned_call = self._fallback_first_action(goal)
        except httpx.HTTPError:
            if force_downloads_plan:
                raise
            planned_call = self._fallback_first_action(goal)

        arguments = planned_call.arguments
        tool_name = planned_call.name
        rationale = planned_call.rationale
        email_arguments = _extract_email_draft_arguments(goal)
        if email_arguments and tool_name != "email_create_draft":
            tool_name = "email_create_draft"
            arguments = email_arguments
            rationale = "Normalize email compose workflow to Gmail draft creation."
        code_arguments = _extract_code_request_arguments(goal)
        discord_arguments = _extract_discord_message_arguments(goal)
        if discord_arguments and tool_name != "discord_send_message" and not email_arguments:
            tool_name = "discord_send_message"
            arguments = discord_arguments
            rationale = "Normalize chat/message wording to Discord message sending."
        if (
            code_arguments
            and tool_name != "vscode_paste_code"
            and not email_arguments
            and not discord_arguments
        ):
            tool_name = "vscode_paste_code"
            arguments = code_arguments
            rationale = "Normalize coding request to VS Code code generation."
        canvas_assignment_arguments = _extract_canvas_assignment_arguments(goal)
        if canvas_assignment_arguments and tool_name != "canvas_list_assignments_due_soon":
            tool_name = "canvas_list_assignments_due_soon"
            arguments = canvas_assignment_arguments
            rationale = "Normalize Canvas due-date workflow to assignment lookup first."
        canvas_arguments = _extract_canvas_arguments(goal)
        if (
            canvas_arguments
            and not canvas_assignment_arguments
            and tool_name != "canvas_open_course"
        ):
            tool_name = "canvas_open_course"
            arguments = canvas_arguments
            rationale = "Normalize Canvas course navigation wording."
        accessibility_arguments = _extract_accessibility_describe_arguments(goal)
        if accessibility_arguments and tool_name != "accessibility_describe_screen":
            tool_name = "accessibility_describe_screen"
            arguments = accessibility_arguments
            rationale = "Normalize screen-context request to accessibility narration."
        youtube_arguments = _extract_youtube_arguments(goal)
        if youtube_arguments and tool_name != "youtube_open":
            tool_name = "youtube_open"
            arguments = youtube_arguments
            rationale = "Normalize YouTube wording to YouTube opening/search."
        browser_target = _extract_browser_target(goal)
        if (
            browser_target
            and tool_name == "notify_user"
            and not any(
                (
                    email_arguments,
                    code_arguments,
                    discord_arguments,
                    canvas_assignment_arguments,
                    canvas_arguments,
                    accessibility_arguments,
                    youtube_arguments,
                )
            )
        ):
            tool_name = "browser_open"
            arguments = {"url": browser_target}
            rationale = "Normalize website navigation wording."
        notepad_arguments = _extract_notepad_launch_arguments(goal)
        if (
            notepad_arguments
            and tool_name == "notify_user"
            and not any(
                (
                    email_arguments,
                    code_arguments,
                    discord_arguments,
                    canvas_assignment_arguments,
                    canvas_arguments,
                    accessibility_arguments,
                    youtube_arguments,
                    browser_target,
                )
            )
        ):
            tool_name = "app_launch"
            arguments = notepad_arguments
            rationale = "Normalize Notepad dictation wording."

        arguments = self._normalize_first_action_arguments(goal, tool_name, arguments)

        return PlannedToolCall(
            name=tool_name,
            arguments=arguments,
            rationale=rationale,
        )

    async def plan_next_action(
        self,
        goal: str,
        tool_definitions: list[dict[str, Any]],
        previous_tool_name: str,
        previous_result: dict[str, Any],
        recent_tool_calls: list[dict[str, Any]] | None = None,
    ) -> PlannedToolCall:
        if previous_tool_name == "app_launch":
            tool_definitions = [
                definition
                for definition in tool_definitions
                if definition["name"] == "keyboard_type"
            ]
            if not tool_definitions:
                raise RuntimeError("keyboard_type is not available for desktop follow-up.")

        payload = {
            "model": self.settings.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": with_assistant_personality(
                        "You are NemotronOS, a private Windows PC agent. "
                        "A previous desktop tool has already run successfully. "
                        "Pick exactly one next tool call from the provided tool list. "
                        "When calling keyboard_type, the text argument must contain only "
                        "the literal text the user wants entered into the active app. "
                        "Do not include command words, app names, or instruction wording. "
                        "For managed browser automation, reason over the latest browser page "
                        "state, use the provided browser target ids instead of inventing selectors, "
                        "and call notify_user when the browser task is complete."
                    ),
                },
                {
                    "role": "user",
                    "content": goal,
                },
                {
                    "role": "assistant",
                    "content": (
                        f"Previous tool: {previous_tool_name}. "
                        f"Previous result: {json.dumps(previous_result)}"
                    ),
                },
                *(
                    [
                        {
                            "role": "assistant",
                            "content": f"Recent tool history: {json.dumps(recent_tool_calls)}",
                        }
                    ]
                    if recent_tool_calls
                    else []
                ),
            ],
            "tools": [
                {"type": "function", "function": definition}
                for definition in tool_definitions
            ],
            "tool_choice": (
                {
                    "type": "function",
                    "function": {"name": "keyboard_type"},
                }
                if previous_tool_name == "app_launch"
                else "auto"
            ),
            "max_tokens": 256,
        }
        return await self._request_tool_call(payload, tool_definitions)

    async def generate_code(self, goal: str) -> GeneratedCode:
        headers = {"Authorization": f"Bearer {self.settings.model_api_key}"}
        url = f"{self.settings.model_base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self.settings.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are NemotronOS's local coding agent. Generate the code the "
                        "user asked for. Return only code, with no markdown fence, no "
                        "explanation, no preamble, and no trailing commentary. Prefer a "
                        "single self-contained file when the user does not ask for a "
                        "multi-file project. Do not claim you saved or ran anything."
                    ),
                },
                {"role": "user", "content": goal},
            ],
            "temperature": 0.2,
            "max_tokens": self.settings.model_code_max_tokens,
        }
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()

        data = response.json()
        content = str(data["choices"][0]["message"].get("content") or "")
        code, fenced_language = self._clean_generated_code(content)
        if not code.strip():
            raise RuntimeError("Model returned empty code.")
        return GeneratedCode(
            code=code,
            language=fenced_language or _guess_code_language(goal, code),
        )

    async def summarize_screen_context(
        self,
        goal: str,
        screen_context: dict[str, Any],
    ) -> str:
        context_json = _compact_json(screen_context, max_characters=9000)
        return await self._request_text_response(
            system_prompt=with_assistant_personality(
                "You are NemotronOS in accessibility narration mode for a blind or "
                "low-vision Windows user. Explain the current screen from the provided "
                "structured desktop context. Return plain spoken text only: no markdown, "
                "no bullets, no headings, and no raw JSON. Use two to four complete "
                "sentences. Start with 'You are focused on ...' when the foreground "
                "window is known. Mention important visible windows or controls, then "
                "suggest one safe next action the user can ask for. Do not claim certainty "
                "about pixels you cannot inspect. If screenshot metadata is present but no "
                "image content is provided, do not pretend to visually inspect the image."
            ),
            user_prompt=(
                f"User request: {goal}\n\n"
                f"Structured screen context JSON:\n{context_json}"
            ),
            max_tokens=420,
        )

    async def summarize_recent_activity(
        self,
        goal: str,
        activity_context: dict[str, Any],
    ) -> str:
        context_json = _compact_json(activity_context, max_characters=9000)
        return await self._request_text_response(
            system_prompt=with_assistant_personality(
                "You are NemotronOS explaining your own recent actions to a blind or "
                "low-vision user. Summarize what you just did in first person, based only "
                "on the task and tool-event context. Mention whether it completed, failed, "
                "or needs approval. Return plain spoken text only: no markdown, no raw JSON, "
                "no hidden reasoning, and no <think> blocks. Use two complete sentences at most."
            ),
            user_prompt=(
                f"User question: {goal}\n\n"
                f"Recent activity context JSON:\n{context_json}"
            ),
            max_tokens=320,
        )

    def _first_action_system_prompt(self) -> str:
        return with_assistant_personality(
            "You are NemotronOS, a private Windows PC agent. "
            "Interpret the user's request, including short or noisy voice transcripts, "
            "and pick exactly one next tool call from the provided tool list. "
            "Do not answer in prose. Do not invent tools. "
            "Use Windows-style paths when paths are needed. "
            "If the user asks to organize Downloads and see the plan first, call "
            f"fs_plan_changes on {self.settings.default_downloads_path}. "
            "Treat semantically equivalent phrasing as the same command: open, launch, "
            "start, pull up, bring up, take me to, go to, navigate to, put on, play, "
            "watch, search for, find, show me, write, type, enter, compose, draft, "
            "send, post, describe, read, explain, make, build, create, generate, and code. "
            "If the user asks to type, write, enter, dictate, paste, or put text in Notepad, "
            "call app_launch with app_name='notepad'; the coordinator will type the requested "
            "text afterward. "
            "If the user asks for a website/domain/URL, including phrasing like visit, "
            "load, pull up, bring up, take me to, or go to, call browser_open. "
            "If the user asks for a general browser task that requires reading or interacting "
            "with page content over multiple steps, prefer the managed browser automation tools: "
            "browser_session_ensure, browser_navigate, browser_snapshot, browser_click, "
            "browser_type, browser_select_option, and browser_press. "
            "If the user asks for Canvas course/class navigation with wording like open, "
            "show, bring up, pull up, take me to, or go to, call canvas_open_course with "
            "the natural course name in course_query. "
            "If the user asks to open or search Gmail, use gmail_open or gmail_search. "
            "If the user asks to write, compose, draft, create, prepare, or send an email, "
            "mail, e-mail, Gmail, or note to an email address, "
            "call email_create_draft with to, subject when present, and body; never send it. "
            "Use gmail_compose_draft only as a browser-session backup for composing a draft, "
            "and never call gmail_send_current_draft unless a separate explicit approval flow "
            "has requested sending the current draft. Never send email with generic browser clicks. "
            "If the user asks for Canvas assignments, homework, to-do items, or due dates, "
            "call canvas_list_assignments_due_soon with days_ahead; use 7 for 'next week'. "
            "If the user asks what is on screen, what they are looking at, to describe, "
            "read, summarize, or explain the active/current/foreground window, app, "
            "page, screen, desktop, or visible context, call accessibility_describe_screen "
            "with include_screenshot=true and max_windows=12. "
            "If the user asks for YouTube content, call youtube_open. Use action='random' "
            "for random/recommended/any/surprise video requests, action='search' with query and "
            "prefer_video_results=true for play/watch/find/search/look up/pull up video, title, "
            "creator, or channel searches, and action='video' only for exact YouTube URLs or IDs. "
            "If the user asks to send/post/type/write/paste/reply/say a message to Discord "
            "or the active chat, "
            "call discord_send_message with only the message body in text. "
            "If the user asks you to write, code, build, make, create, generate, prototype, "
            "implement, or whip up software, scripts, functions, components, games, mobile apps, "
            "websites, web pages, or code snippets, call "
            "vscode_paste_code with request set to the full coding request and optional "
            "language if obvious. Do not put generated code in the tool arguments. "
            "If no available tool can reasonably help, call notify_user with a brief message."
        )

    def _json_router_system_prompt(
        self,
        tool_definitions: list[dict[str, Any]],
        force_downloads_plan: bool,
    ) -> str:
        tool_names = ", ".join(definition["name"] for definition in tool_definitions)
        tool_schemas = json.dumps(tool_definitions, separators=(",", ":"))
        forced_tool = (
            " You must choose fs_plan_changes for this request."
            if force_downloads_plan
            else ""
        )
        return with_assistant_personality(
            "You are NemotronOS's tool router. Return only one compact JSON object "
            "and no other text. Do not include markdown, XML tags, <think>, or explanation. "
            "The JSON schema is exactly: "
            '{"name":"tool_name","arguments":{},"rationale":"short reason"}. '
            f"Allowed tools: {tool_names}.{forced_tool} "
            "Interpret short or noisy voice transcripts naturally. "
            "For generic web tasks that require reading or interacting with live page content, "
            "prefer browser_session_ensure, browser_navigate, browser_snapshot, browser_click, "
            "browser_type, browser_select_option, and browser_press. "
            "Map equivalent phrases to the same tool: open/launch/start/pull up/bring up, "
            "go to/take me to/navigate to/visit/load, play/watch/find/search/look up, "
            "write/type/enter/paste, compose/draft/prepare, describe/read/explain, "
            "make/build/create/generate/code/prototype. "
            "For Gmail open/search tasks, use gmail_open or gmail_search. "
            "For email, e-mail, mail, or Gmail compose/draft/prepare requests, use "
            "email_create_draft and include to, subject when present, and body; do not send email. "
            "Use gmail_compose_draft only as a browser-session backup for composing a draft. "
            "Never send email with generic browser clicks. "
            "For YouTube searches, use youtube_open with action='search', query, "
            "and prefer_video_results=true. "
            "For random, recommended, any, or surprise YouTube video requests, use youtube_open "
            "with action='random'. "
            "For Notepad typing, writing, entering, dictation, or paste requests, use app_launch "
            "with app_name='notepad'. "
            "For accessibility or screen-context requests, including describing, reading, "
            "summarizing, or explaining the current screen, active window, foreground app, "
            "visible page, or desktop context, use accessibility_describe_screen with "
            "include_screenshot=true and max_windows=12. "
            "For Discord or active-chat messages, use discord_send_message and put only the message body "
            "in text. For Canvas assignment/homework due-date requests, use "
            "canvas_list_assignments_due_soon. For Canvas course navigation, use "
            "canvas_open_course. "
            "For email, e-mail, mail, or Gmail compose/draft/prepare requests, use email_create_draft and include "
            "to, subject when present, and body; do not send email. "
            "For normal websites/domains/URLs, including visit/load/pull up/take me to phrasing, "
            "use browser_open. "
            "For coding requests, including programs, games, mobile apps, websites, scripts, functions, "
            "components, and code snippets, use vscode_paste_code with request set to "
            "the full coding request and language only when obvious; do not include generated code. "
            f"Tool schemas: {tool_schemas}"
        )

    async def _request_text_response(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
    ) -> str:
        headers = {}
        if self.settings.model_api_key:
            headers["Authorization"] = f"Bearer {self.settings.model_api_key}"
        payload = {
            "model": self.settings.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
            "max_tokens": max_tokens,
        }
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            response = await client.post(self._chat_completions_url(), headers=headers, json=payload)
            response.raise_for_status()

        data = response.json()
        content = str(data["choices"][0]["message"].get("content") or "")
        cleaned = self._clean_text_response(content)
        if not cleaned:
            raise RuntimeError("Model returned an empty accessibility summary.")
        return cleaned

    async def _request_tool_call(
        self,
        payload: dict[str, Any],
        tool_definitions: list[dict[str, Any]],
    ) -> PlannedToolCall:
        headers = {}
        if self.settings.model_api_key:
            headers["Authorization"] = f"Bearer {self.settings.model_api_key}"
        url = self._chat_completions_url()
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()

        data = response.json()
        message = data["choices"][0]["message"]
        tool_call = self._extract_tool_call(message)
        if not tool_call:
            raise RuntimeError("OpenAI-compatible model did not return a tool call.")

        raw_arguments = tool_call["function"].get("arguments", "{}")
        arguments = self._parse_arguments(raw_arguments)
        tool_name = tool_call["function"]["name"]
        if tool_name not in {definition["name"] for definition in tool_definitions}:
            raise RuntimeError(f"OpenAI-compatible model requested unknown tool: {tool_name}")

        return PlannedToolCall(
            name=tool_name,
            arguments=arguments,
            rationale=message.get("content"),
        )

    def _chat_completions_url(self) -> str:
        base_url = self.settings.model_base_url.rstrip("/")
        if self.settings.model_provider == "ollama" and not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"
        return f"{base_url}/chat/completions"

    async def _request_json_tool_call(
        self,
        goal: str,
        tool_definitions: list[dict[str, Any]],
        force_downloads_plan: bool,
    ) -> PlannedToolCall:
        headers = {}
        if self.settings.model_api_key:
            headers["Authorization"] = f"Bearer {self.settings.model_api_key}"
        url = self._chat_completions_url()
        payload = {
            "model": self.settings.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": self._json_router_system_prompt(
                        tool_definitions,
                        force_downloads_plan,
                    ),
                },
                {"role": "user", "content": goal},
            ],
            "temperature": 0,
            "max_tokens": 192,
        }
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()

        data = response.json()
        content = str(data["choices"][0]["message"].get("content") or "")
        parsed = self._parse_json_tool_content(content)
        tool_name = str(parsed.get("name") or "").strip()
        if tool_name not in {definition["name"] for definition in tool_definitions}:
            raise RuntimeError(f"JSON planner requested unknown tool: {tool_name}")
        arguments = parsed.get("arguments") or {}
        if not isinstance(arguments, dict):
            raise RuntimeError("JSON planner returned non-object arguments.")
        return PlannedToolCall(
            name=tool_name,
            arguments=arguments,
            rationale=str(parsed.get("rationale") or "").strip() or None,
        )

    def _extract_tool_call(self, message: dict[str, Any]) -> dict[str, Any] | None:
        tool_calls = message.get("tool_calls") or []
        if tool_calls:
            return tool_calls[0]

        function_call = message.get("function_call")
        if function_call:
            return {"function": function_call}

        return None

    def _parse_arguments(self, raw_arguments: Any) -> dict[str, Any]:
        if isinstance(raw_arguments, dict):
            return raw_arguments

        if not raw_arguments:
            return {}

        parsed = json.loads(raw_arguments)
        if not isinstance(parsed, dict):
            raise RuntimeError("OpenAI-compatible model returned non-object tool arguments.")
        return parsed

    def _parse_json_tool_content(self, content: str) -> dict[str, Any]:
        cleaned = content.strip()
        if not cleaned:
            raise RuntimeError("JSON planner returned empty content.")

        fenced_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, flags=re.DOTALL)
        if fenced_match:
            cleaned = fenced_match.group(1)
        elif "<think>" in cleaned:
            cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start < 0 or end <= start:
                raise
            parsed = json.loads(cleaned[start : end + 1])

        if not isinstance(parsed, dict):
            raise RuntimeError("JSON planner returned a non-object payload.")
        return parsed

    def _clean_generated_code(self, content: str) -> tuple[str, str | None]:
        cleaned = content.strip()
        if "<think>" in cleaned:
            cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()

        fenced_match = re.fullmatch(
            r"```([a-zA-Z0-9_+#.-]+)?\s*\n?(.*?)\s*```",
            cleaned,
            flags=re.DOTALL,
        )
        if fenced_match:
            language = (fenced_match.group(1) or "").strip().lower() or None
            return fenced_match.group(2).strip("\n\r"), language

        return cleaned, None

    def _clean_text_response(self, content: str) -> str:
        cleaned = content.strip()
        if re.search(r"<think\b", cleaned, flags=re.IGNORECASE):
            cleaned = re.sub(
                r"<think\b[^>]*>.*?</think>",
                "",
                cleaned,
                flags=re.DOTALL | re.IGNORECASE,
            ).strip()
            cleaned = re.sub(
                r"<think\b[^>]*>.*",
                "",
                cleaned,
                flags=re.DOTALL | re.IGNORECASE,
            ).strip()
        cleaned = re.sub(r"^```(?:text|markdown)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        return cleaned.strip()

    def _should_force_downloads_plan(self, goal: str) -> bool:
        return _looks_like_downloads_organization_goal(goal)

    def _should_force_notepad_launch(self, goal: str) -> bool:
        return _extract_notepad_launch_arguments(goal) is not None

    def _tool_choice(self, force_downloads_plan: bool) -> str | dict[str, Any]:
        if force_downloads_plan:
            return {
                "type": "function",
                "function": {"name": "fs_plan_changes"},
            }
        return "auto"

    def _normalize_downloads_plan_arguments(
        self,
        goal: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        allowed_operations = arguments.get("allowed_operations")
        if not isinstance(allowed_operations, list):
            allowed_operations = []

        normalized_operations = {
            str(operation).strip().lower()
            for operation in allowed_operations
        }
        normalized_operations.update({"mkdir", "move"})

        return {
            **arguments,
            "root_path": self.settings.default_downloads_path,
            "goal": goal,
            "allowed_operations": sorted(normalized_operations),
        }

    def _normalize_first_action_arguments(
        self,
        goal: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        if self._should_force_downloads_plan(goal) and tool_name == "fs_plan_changes":
            return self._normalize_downloads_plan_arguments(goal, arguments)

        if tool_name == "youtube_open":
            action = str(arguments.get("action") or "").strip().lower()
            if action in {"search", "specific", "play", "watch"}:
                return {
                    **arguments,
                    "action": "search",
                    "prefer_video_results": bool(
                        arguments.get("prefer_video_results", True)
                    ),
                }
        if tool_name == "discord_send_message":
            text = str(arguments.get("text") or "").strip()
            if text:
                return {
                    **arguments,
                    "text": text,
                    "open_if_needed": bool(arguments.get("open_if_needed", True)),
                }
        if tool_name == "vscode_paste_code":
            request = str(arguments.get("request") or goal).strip()
            language = str(arguments.get("language") or _guess_code_language(goal) or "").strip()
            return {
                **arguments,
                "request": request,
                **({"language": language} if language else {}),
                "open_new_window": bool(arguments.get("open_new_window", True)),
            }
        if tool_name == "email_create_draft":
            extracted = _extract_email_draft_arguments(goal) or {}
            to_value = (
                arguments.get("to")
                or arguments.get("recipient")
                or arguments.get("recipients")
                or extracted.get("to")
            )
            body = str(
                arguments.get("body")
                or arguments.get("message")
                or arguments.get("text")
                or extracted.get("body")
                or ""
            ).strip()
            subject = str(arguments.get("subject") or extracted.get("subject") or "").strip()
            normalized = {
                **arguments,
                "to": to_value,
                "body": body,
            }
            if subject:
                normalized["subject"] = subject
            for optional_name in ("cc", "bcc"):
                if arguments.get(optional_name):
                    normalized[optional_name] = arguments[optional_name]
            normalized.pop("recipient", None)
            normalized.pop("recipients", None)
            normalized.pop("message", None)
            normalized.pop("text", None)
            return normalized
        if tool_name == "canvas_list_assignments_due_soon":
            extracted = _extract_canvas_assignment_arguments(goal) or {}
            return {
                **extracted,
                **arguments,
                "days_ahead": int(arguments.get("days_ahead") or extracted.get("days_ahead") or 7),
                "include_completed": bool(arguments.get("include_completed", False)),
            }
        if tool_name == "accessibility_describe_screen":
            return {
                **arguments,
                "include_screenshot": bool(arguments.get("include_screenshot", True)),
                "max_windows": int(arguments.get("max_windows") or 12),
            }
        if tool_name == "gmail_compose_draft":
            return {
                **arguments,
                "to": str(arguments.get("to") or "").strip(),
                "subject": str(arguments.get("subject") or "").strip(),
                "body": str(arguments.get("body") or "").strip(),
            }
        if tool_name == "gmail_search":
            return {
                **arguments,
                "query": str(arguments.get("query") or "").strip(),
            }
        if tool_name == "gmail_open":
            return {
                **arguments,
                "view": str(arguments.get("view") or "inbox").strip().lower() or "inbox",
            }
        return arguments

    def _fallback_first_action(self, goal: str) -> PlannedToolCall:
        code_arguments = _extract_code_request_arguments(goal)
        if code_arguments:
            return PlannedToolCall(
                name="vscode_paste_code",
                arguments=code_arguments,
                rationale="Fallback parser routed a coding request to VS Code.",
            )

        email_arguments = _extract_email_draft_arguments(goal)
        if email_arguments:
            return PlannedToolCall(
                name="email_create_draft",
                arguments=email_arguments,
                rationale="Fallback parser routed an email draft request.",
            )

        gmail_call = _extract_gmail_action(goal)
        if gmail_call:
            return gmail_call

        browser_agent_start_url = _extract_browser_agent_start_url(goal)
        if browser_agent_start_url:
            return PlannedToolCall(
                name="browser_session_ensure",
                arguments={"start_url": browser_agent_start_url},
                rationale="Fallback parser routed a general browser automation request.",
            )

        discord_arguments = _extract_discord_message_arguments(goal)
        if discord_arguments:
            return PlannedToolCall(
                name="discord_send_message",
                arguments=discord_arguments,
                rationale="Fallback parser routed a Discord message request.",
            )

        canvas_assignment_arguments = _extract_canvas_assignment_arguments(goal)
        if canvas_assignment_arguments:
            return PlannedToolCall(
                name="canvas_list_assignments_due_soon",
                arguments=canvas_assignment_arguments,
                rationale="Fallback parser routed a Canvas assignment due-date request.",
            )

        canvas_arguments = _extract_canvas_arguments(goal)
        if canvas_arguments:
            return PlannedToolCall(
                name="canvas_open_course",
                arguments=canvas_arguments,
                rationale="Fallback parser routed Canvas course navigation.",
            )

        accessibility_arguments = _extract_accessibility_describe_arguments(goal)
        if accessibility_arguments:
            return PlannedToolCall(
                name="accessibility_describe_screen",
                arguments=accessibility_arguments,
                rationale="Fallback parser routed a screen narration request.",
            )

        youtube_arguments = _extract_youtube_arguments(goal)
        if youtube_arguments:
            return PlannedToolCall(
                name="youtube_open",
                arguments=youtube_arguments,
                rationale="Fallback parser routed a YouTube request.",
            )

        browser_target = _extract_browser_target(goal)
        if browser_target:
            return PlannedToolCall(
                name="browser_open",
                arguments={"url": browser_target},
                rationale="Fallback parser routed browser navigation.",
            )
        if self._should_force_notepad_launch(goal):
            return PlannedToolCall(
                name="app_launch",
                arguments={"app_name": "notepad"},
                rationale="Fallback parser routed Notepad typing setup.",
            )

        return PlannedToolCall(
            name="notify_user",
            arguments={"message": f"I do not know how to do that yet: {goal}"},
            rationale="Fallback response for an unsupported goal.",
        )


class OpenAIResponsesModelClient(OpenAICompatibleModelClient):
    """OpenAI Responses API transport with the existing NemotronOS planner behavior."""

    async def generate_code(self, goal: str) -> GeneratedCode:
        content = await self._request_text_response(
            system_prompt=(
                "You are NemotronOS's coding agent. Generate the code the user asked for. "
                "Return only code, with no markdown fence, explanation, preamble, or "
                "trailing commentary. Prefer a single self-contained file when the user "
                "does not ask for a multi-file project. Do not claim you saved or ran anything."
            ),
            user_prompt=goal,
            max_tokens=self.settings.model_code_max_tokens,
        )
        code, fenced_language = self._clean_generated_code(content)
        if not code.strip():
            raise RuntimeError("Model returned empty code.")
        return GeneratedCode(
            code=code,
            language=fenced_language or _guess_code_language(goal, code),
        )

    async def _request_text_response(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
    ) -> str:
        data = await self._post_response(
            {
                "model": self.settings.model_name,
                "instructions": system_prompt,
                "input": user_prompt,
                "max_output_tokens": max(max_tokens, 512),
                **self._response_behavior(),
            }
        )
        cleaned = self._clean_text_response(self._extract_response_text(data))
        if not cleaned:
            raise RuntimeError("OpenAI Responses API returned an empty text response.")
        return cleaned

    async def _request_tool_call(
        self,
        payload: dict[str, Any],
        tool_definitions: list[dict[str, Any]],
    ) -> PlannedToolCall:
        response_payload = self._convert_chat_payload(payload)
        response_payload["tools"] = [
            {
                "type": "function",
                **definition,
                "strict": False,
            }
            for definition in tool_definitions
        ]
        response_payload["tool_choice"] = self._responses_tool_choice(
            payload.get("tool_choice")
        )
        response_payload["parallel_tool_calls"] = False

        data = await self._post_response(response_payload)
        tool_call = next(
            (
                item
                for item in data.get("output", [])
                if isinstance(item, dict) and item.get("type") == "function_call"
            ),
            None,
        )
        if tool_call is None:
            raise RuntimeError("OpenAI Responses API did not return a function call.")

        tool_name = str(tool_call.get("name") or "")
        if tool_name not in {definition["name"] for definition in tool_definitions}:
            raise RuntimeError(f"OpenAI Responses API requested unknown tool: {tool_name}")

        return PlannedToolCall(
            name=tool_name,
            arguments=self._parse_arguments(tool_call.get("arguments", "{}")),
            rationale=self._extract_response_text(data) or None,
        )

    async def _request_json_tool_call(
        self,
        goal: str,
        tool_definitions: list[dict[str, Any]],
        force_downloads_plan: bool,
    ) -> PlannedToolCall:
        content = await self._request_text_response(
            system_prompt=self._json_router_system_prompt(
                tool_definitions,
                force_downloads_plan,
            ),
            user_prompt=goal,
            max_tokens=192,
        )
        parsed = self._parse_json_tool_content(content)
        tool_name = str(parsed.get("name") or "").strip()
        if tool_name not in {definition["name"] for definition in tool_definitions}:
            raise RuntimeError(f"JSON planner requested unknown tool: {tool_name}")
        arguments = parsed.get("arguments") or {}
        if not isinstance(arguments, dict):
            raise RuntimeError("JSON planner returned non-object arguments.")
        return PlannedToolCall(
            name=tool_name,
            arguments=arguments,
            rationale=str(parsed.get("rationale") or "").strip() or None,
        )

    async def _post_response(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {}
        if self.settings.model_api_key:
            headers["Authorization"] = f"Bearer {self.settings.model_api_key}"
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            response = await client.post(
                self._responses_url(),
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("OpenAI Responses API returned a non-object response.")
        return data

    def _convert_chat_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        instructions: list[str] = []
        input_messages: list[dict[str, str]] = []
        for message in payload.get("messages", []):
            role = str(message.get("role") or "user")
            content = str(message.get("content") or "")
            if role in {"system", "developer"}:
                instructions.append(content)
            else:
                input_messages.append({"role": role, "content": content})

        converted: dict[str, Any] = {
            "model": payload.get("model") or self.settings.model_name,
            "input": input_messages,
            "max_output_tokens": max(int(payload.get("max_tokens", 256)), 512),
            **self._response_behavior(),
        }
        if instructions:
            converted["instructions"] = "\n\n".join(instructions)
        return converted

    def _response_behavior(self) -> dict[str, Any]:
        return {
            "reasoning": {"effort": self.settings.model_reasoning_effort},
            "text": {"verbosity": self.settings.model_text_verbosity},
            "store": False,
        }

    def _responses_tool_choice(self, chat_tool_choice: Any) -> str | dict[str, str]:
        if isinstance(chat_tool_choice, dict):
            function = chat_tool_choice.get("function") or {}
            name = str(function.get("name") or "")
            if name:
                return {"type": "function", "name": name}
        return "required"

    def _responses_url(self) -> str:
        return f"{self.settings.model_base_url.rstrip('/')}/responses"

    def _extract_response_text(self, data: dict[str, Any]) -> str:
        direct_text = data.get("output_text")
        if isinstance(direct_text, str) and direct_text.strip():
            return direct_text

        text_parts: list[str] = []
        for item in data.get("output", []):
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if not isinstance(content, dict):
                    continue
                if content.get("type") in {"output_text", "text"}:
                    text = content.get("text")
                    if isinstance(text, str) and text.strip():
                        text_parts.append(text)
        return "\n".join(text_parts)


def build_model_client(settings: AgentServerSettings) -> ModelClient:
    if settings.model_mode == "openai_compatible":
        if settings.model_api.strip().lower() == "responses":
            return OpenAIResponsesModelClient(settings)
        return OpenAICompatibleModelClient(settings)
    return MockModelClient(settings)


def _compact_json(value: Any, max_characters: int) -> str:
    text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= max_characters:
        return text
    return f"{text[: max_characters - 28]}... <truncated for prompt>"


def _looks_like_downloads_organization_goal(goal: str) -> bool:
    lowered_goal = goal.lower()
    has_downloads = re.search(r"\bdownloads?\b", lowered_goal)
    has_organize_intent = re.search(
        r"\b(?:organize|organise|sort|clean\s+up|cleanup|tidy|arrange|"
        r"group|categorize|categorise|file|move)\b",
        lowered_goal,
    )
    return bool(has_downloads and has_organize_intent)


def _extract_notepad_launch_arguments(goal: str) -> dict[str, Any] | None:
    lowered_goal = goal.lower()
    if "notepad" not in lowered_goal:
        return None
    if not re.search(
        r"\b(?:type|write|enter|paste|put|dictate|take\s+(?:a\s+)?note|"
        r"jot|note\s+down)\b",
        lowered_goal,
    ):
        return None
    return {"app_name": "notepad"}


def _extract_gmail_action(goal: str) -> PlannedToolCall | None:
    lowered_goal = goal.lower()
    if not _looks_like_email_goal(lowered_goal):
        return None

    compose_arguments = _extract_gmail_compose_arguments(goal)
    if compose_arguments:
        return PlannedToolCall(
            name="gmail_compose_draft",
            arguments=compose_arguments,
            rationale="Fallback parser routed the email request to Gmail draft composition.",
        )

    search_query = _extract_gmail_search_query(goal)
    if search_query:
        return PlannedToolCall(
            name="gmail_search",
            arguments={"query": search_query},
            rationale="Fallback parser routed the email request to Gmail search.",
        )

    view = "inbox"
    if re.search(r"\b(sent|sent mail)\b", lowered_goal):
        view = "sent"
    elif re.search(r"\b(draft|drafts)\b", lowered_goal):
        view = "drafts"
    elif "starred" in lowered_goal:
        view = "starred"
    elif re.search(r"\ball mail\b", lowered_goal):
        view = "all"

    return PlannedToolCall(
        name="gmail_open",
        arguments={"view": view},
        rationale="Fallback parser routed the email request to Gmail.",
    )


def _looks_like_email_goal(lowered_goal: str) -> bool:
    return bool(re.search(r"\b(gmail|e-mail|email|mail|inbox)\b", lowered_goal))


def _extract_gmail_compose_arguments(goal: str) -> dict[str, Any] | None:
    lowered_goal = goal.lower()
    if not re.search(r"\b(compose|draft|write|send|email|e-mail|mail)\b", lowered_goal):
        return None
    if not re.search(r"\b(to|for)\b", lowered_goal) and not re.search(
        r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        goal,
        flags=re.IGNORECASE,
    ):
        return None

    recipient = _extract_email_recipient(goal)
    body = _extract_email_body(goal)
    subject = _extract_email_subject(goal)
    if not recipient or not body:
        return None

    return {
        "to": recipient,
        "subject": subject or "",
        "body": body,
    }


def _extract_email_recipient(goal: str) -> str | None:
    email_match = re.search(
        r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        goal,
        flags=re.IGNORECASE,
    )
    if email_match:
        return email_match.group(0).strip()

    match = re.search(
        r"\b(?:to|for)\s+(.+?)(?:\s+(?:with\s+)?subject\b|\s+(?:saying|that\s+says|body|message)\b|$)",
        goal,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    recipient = match.group(1).strip(" \t\n\r.,;:\"'")
    recipient = re.sub(r"^(?:my|the)\s+", "", recipient, flags=re.IGNORECASE)
    return recipient or None


def _extract_email_subject(goal: str) -> str | None:
    match = re.search(
        r"\bsubject\s*(?:is|of|:)?\s*(.+?)(?:\s+(?:saying|that\s+says|body|message)\b|$)",
        goal,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    subject = match.group(1).strip(" \t\n\r.,;:\"'")
    return subject or None


def _extract_email_body(goal: str) -> str | None:
    quoted_match = re.search(r'"([^"\r\n]+)"', goal)
    if quoted_match:
        body = quoted_match.group(1).strip()
        if body:
            return body

    patterns = (
        r"\b(?:saying|that\s+says)\s*[,;:-]?\s*(.+)$",
        r"\b(?:body|message)\s*(?:is|:)?\s*(.+)$",
    )
    for pattern in patterns:
        match = re.search(pattern, goal, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            continue
        body = match.group(1).strip(" \t\n\r.,;:\"'")
        if body:
            return body
    return None


def _extract_gmail_search_query(goal: str) -> str | None:
    patterns = (
        r"\b(?:search|find|look\s+for)\s+(?:my\s+)?(?:gmail|email|e-mail|mail|inbox)\s+(?:for\s+)?(.+)$",
        r"\b(?:search|find|look\s+for)\s+(.+?)\s+(?:in|on)\s+(?:gmail|email|e-mail|mail|my\s+inbox)\b",
        r"\b(?:gmail|email|e-mail|mail|inbox)\s+(?:search|find)\s+(?:for\s+)?(.+)$",
    )
    for pattern in patterns:
        match = re.search(pattern, goal, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            continue
        query = match.group(1).strip(" \t\n\r.,;:\"'")
        query = re.sub(r"^(?:for|about)\s+", "", query, flags=re.IGNORECASE)
        if query:
            return query
    return None


def _extract_browser_target(goal: str) -> str | None:
    lowered_goal = goal.lower()
    direct_web_target = _extract_direct_web_target(goal)
    if direct_web_target:
        return direct_web_target
    direct_alias_target = _extract_direct_site_alias(goal)
    if direct_alias_target:
        return direct_alias_target

    browser_intent = any(
        phrase in lowered_goal
        for phrase in (
            "browser",
            "website",
            "web site",
            "navigate to",
            "go to",
            "goto",
            "take me to",
            "bring up",
            "pull up",
            "load",
            "visit",
            "open site",
            "open webpage",
            "open web page",
        )
    )
    if not browser_intent:
        return None

    patterns = (
        r"\b(?:navigate|go|goto|browse|visit|load)\s+(?:to\s+)?(.+)$",
        r"\b(?:take|bring)\s+me\s+to\s+(.+)$",
        r"\bpull\s+up\s+(.+)$",
        r"\bbring\s+up\s+(.+)$",
        r"\bopen\s+(?:my\s+)?(?:web\s*)?browser\s+(?:and\s+)?(?:navigate\s+to|go\s+to|to|on|at)?\s*(.+)$",
        r"\bopen\s+(?:the\s+)?(?:website|web\s+site|webpage|web\s+page)\s+(.+)$",
    )
    for pattern in patterns:
        match = re.search(pattern, goal, flags=re.IGNORECASE)
        if match:
            target = _clean_browser_target(match.group(1))
            if target:
                return target

    for alias in ("canvas", "youtube", "google", "gmail", "github"):
        if re.search(rf"\b{re.escape(alias)}\b", lowered_goal):
            return alias

    return None


def _extract_browser_agent_start_url(goal: str) -> str | None:
    lowered_goal = goal.lower()
    if "youtube" in lowered_goal or "canvas" in lowered_goal or "discord" in lowered_goal:
        return None
    if "browser" not in lowered_goal and not re.search(r"\b(open|search|click|type|fill|tell me|read)\b", lowered_goal):
        return None

    direct_target = _extract_direct_web_target(goal)
    if direct_target:
        return direct_target
    alias_target = _extract_direct_site_alias(goal)
    if alias_target:
        return alias_target
    return None


def _extract_direct_site_alias(goal: str) -> str | None:
    cleaned = _clean_direct_navigation_fragment(goal)
    cleaned = re.sub(r"\b(?:url|website|web\s+site|page|webpage)\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" \t\n\r.,;:\"'")
    aliases = ("canvas", "youtube", "google", "gmail", "github")
    for alias in aliases:
        if cleaned.lower() == alias:
            return alias
    return None


def _extract_direct_web_target(goal: str) -> str | None:
    cleaned = _clean_direct_navigation_fragment(goal)

    direct_match = re.fullmatch(
        r"(?:https?://)?(?:www\.)?[a-z0-9][a-z0-9-]*"
        r"(?:\.[a-z0-9][a-z0-9-]*)+"
        r"(?:/[^\s]*)?",
        cleaned,
        flags=re.IGNORECASE,
    )
    if not direct_match:
        return None

    parsed = urlparse(cleaned if "://" in cleaned else f"https://{cleaned}")
    host = parsed.netloc.lower()
    if "." not in host:
        return None

    tld = host.rsplit(".", 1)[-1]
    if tld not in {
        "com",
        "edu",
        "org",
        "net",
        "gov",
        "io",
        "ai",
        "dev",
        "app",
        "co",
        "news",
    }:
        return None

    return cleaned


def _clean_direct_navigation_fragment(goal: str) -> str:
    cleaned = goal.strip(" \t\n\r.,;:\"'")
    cleaned = re.sub(r"^(?:computer|jarvis)\s*[,;:-]?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"^(?:please\s+)?(?:open|launch|start|navigate|go|goto|browse|visit|load)\s+(?:to\s+)?",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"^(?:please\s+)?(?:take\s+me\s+to|bring\s+up|pull\s+up)\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"^(?:please\s+)?to\s+", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip(" \t\n\r.,;:\"'")


def _extract_code_request_arguments(goal: str) -> dict[str, Any] | None:
    lowered_goal = goal.lower()
    has_code_intent = re.search(
        r"\b(?:code|coding|program|software|script|function|component|web\s?page|"
        r"website|app|application|html|css|"
        r"javascript|typescript|python|react|node|api|game|swift|swiftui|kotlin|"
        r"java|rust|golang|go|ruby|lua|csharp|c#|c\+\+|cpp|sql|bash|"
        r"shell|powershell)\b",
        lowered_goal,
    )
    has_creation_verb = re.search(
        r"\b(?:write|make|build|create|generate|code|implement|program|prototype|"
        r"draft|give\s+me|make\s+me|create\s+me|build\s+me|whip\s+up)\b",
        lowered_goal,
    )
    mentions_vscode = re.search(r"\b(?:vs\s*code|vscode|visual\s+studio\s+code)\b", lowered_goal)
    if not ((has_code_intent and has_creation_verb) or mentions_vscode):
        return None

    request = _clean_code_request(goal)
    if not request:
        return None

    language = _guess_code_language(goal)
    return {
        "request": request,
        **({"language": language} if language else {}),
        "open_new_window": True,
    }


def _extract_email_draft_arguments(goal: str) -> dict[str, Any] | None:
    lowered_goal = goal.lower()
    has_email_intent = re.search(r"\b(?:email|gmail|e-mail|mail)\b", lowered_goal)
    has_email_address = re.search(
        r"\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b",
        lowered_goal,
    )
    has_compose_verb = re.search(
        r"\b(?:write|compose|draft|create|make|send|prepare)\b",
        lowered_goal,
    )
    if not ((has_email_intent or has_email_address) and has_compose_verb):
        return None

    patterns = (
        r"\b(?:write|compose|draft|create|make|send|prepare)\s+(?:an?\s+)?"
        r"(?:gmail\s+)?(?:e-?mail|mail|message|note)\s+to\s+(.+?)\s+"
        r"(?:with\s+(?:the\s+)?)?subject(?:\s+line)?\s+(.+?)\s+"
        r"(?:and\s+)?(?:body|message|saying|that\s+says)\s+(.+)$",
        r"\b(?:write|compose|draft|create|make|send|prepare)\s+(?:an?\s+)?"
        r"(?:gmail\s+)?(?:e-?mail|mail|message|note)\s+to\s+(.+?)\s+"
        r"(?:saying|that\s+says|with\s+the\s+message|with\s+message|body|message)\s+(.+)$",
        r"\b(?:email|gmail|e-mail|mail)\s+(.+?)\s+"
        r"(?:saying|that\s+says|with\s+the\s+message|with\s+message|body|message)\s+(.+)$",
    )
    for index, pattern in enumerate(patterns):
        match = re.search(pattern, goal, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            continue
        recipient = _clean_email_recipient(match.group(1))
        if index == 0:
            subject = _clean_email_subject(match.group(2))
            body = _clean_email_body(match.group(3))
        else:
            subject = ""
            body = _clean_email_body(match.group(2))
        if recipient and body:
            return {
                "to": recipient,
                **({"subject": subject} if subject else {}),
                "body": body,
            }

    return None


def _extract_canvas_assignment_arguments(goal: str) -> dict[str, Any] | None:
    lowered_goal = goal.lower()
    if "canvas" not in lowered_goal:
        return None
    if not re.search(
        r"\b(?:assignment|assignments|homework|work|task|tasks|to-?do|todo|due|"
        r"upcoming|deadline|deadlines|quiz|quizzes|project|projects)\b",
        lowered_goal,
    ):
        return None

    days_ahead = 7
    days_match = re.search(
        r"\b(?:next|within|in|coming)\s+(\d{1,2})\s+(?:day|days)\b",
        lowered_goal,
    )
    if days_match:
        days_ahead = max(1, min(int(days_match.group(1)), 30))
    elif re.search(r"\b(?:week|next week)\b", lowered_goal):
        days_ahead = 7

    arguments: dict[str, Any] = {
        "days_ahead": days_ahead,
        "include_completed": False,
    }
    course_arguments = _extract_canvas_arguments(goal)
    if course_arguments:
        arguments["course_query"] = course_arguments["course_query"]
    else:
        course_match = re.search(
            r"\b(?:for|from|in)\s+(?:my\s+|the\s+)?(.+?)\s+(?:course|class)\b",
            goal,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if course_match:
            course_query = _clean_course_query(course_match.group(1))
            if course_query:
                arguments["course_query"] = course_query
    return arguments


def _extract_canvas_arguments(goal: str) -> dict[str, Any] | None:
    lowered_goal = goal.lower()
    if "canvas" not in lowered_goal:
        return None
    if not re.search(r"\b(course|class)\b", lowered_goal):
        return None

    patterns = (
        r"\bcanvas\b.*?\b(?:navigate|go|open|show|bring|pull|load|take)\s+(?:me\s+)?(?:up\s+)?(?:to\s+)?"
        r"(?:my\s+|the\s+)?(.+?)\s+(?:course|class)\b",
        r"\b(?:navigate|go|open|show|bring|pull|load|take)\s+(?:me\s+)?(?:up\s+)?(?:to\s+)?"
        r"(?:my\s+|the\s+)?(.+?)\s+(?:course|class)\s+(?:on|in)\s+canvas\b",
    )
    for pattern in patterns:
        match = re.search(pattern, goal, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            continue
        course_query = _clean_course_query(match.group(1))
        if course_query:
            return {"course_query": course_query}

    return None


def _extract_accessibility_describe_arguments(goal: str) -> dict[str, Any] | None:
    lowered_goal = goal.lower()
    if re.search(
        r"\b(?:what\s+am\s+i\s+looking\s+at|what\s+do\s+you\s+see|"
        r"what(?:'s| is)?\s+on\s+(?:my\s+)?screen|where\s+am\s+i|"
        r"what\s+is\s+this|help\s+me\s+see|screen\s+context)\b",
        lowered_goal,
    ):
        return {
            "include_screenshot": True,
            "max_windows": 12,
        }

    has_visual_context_noun = re.search(
        r"\b(?:screen|window|desktop|foreground|active|current|visible|view|page|"
        r"app|application|program|ui|interface|context)\b",
        lowered_goal,
    )
    has_describe_intent = re.search(
        r"\b(?:describe|explain|summarize|read|inspect|look\s+at|looking\s+at|"
        r"identify|orient|orientation|help\s+me\s+see|"
        r"what\s+(?:am\s+i\s+looking\s+at|do\s+you\s+see|is\s+on)|"
        r"what(?:'s| is)\s+(?:on|this|the|my|active|current)|"
        r"where\s+am\s+i|"
        r"tell\s+me\s+(?:what|about)|give\s+me|show\s+me|guide\s+me)\b",
        lowered_goal,
    )
    if not (has_visual_context_noun and has_describe_intent):
        return None
    return {
        "include_screenshot": True,
        "max_windows": 12,
    }


def _extract_youtube_arguments(goal: str) -> dict[str, Any] | None:
    lowered_goal = goal.lower()
    if "youtube" not in lowered_goal and "youtu.be" not in lowered_goal:
        return None

    url_match = re.search(r"https?://(?:www\.)?(?:youtube\.com|youtu\.be)\S+", goal, flags=re.IGNORECASE)
    if url_match:
        return {"action": "video", "video_url": url_match.group(0).rstrip(".,;")}

    if re.search(r"\b(random|recommend|recommended|recommendation|any|surprise\s+me|something)\b", lowered_goal):
        return {"action": "random"}

    query_patterns = (
        r"\b(?:search|look\s+up|find)\s+(?:youtube\s+)?(?:for\s+)?(.+?)\s+(?:on\s+youtube)\b",
        r"\b(?:search|look\s+up|find)\s+(?:youtube\s+)?for\s+(.+)$",
        r"\b(?:play|watch|open|find|put\s+on|queue\s+up|pull\s+up|bring\s+up)\s+"
        r"(?:a\s+video\s+(?:called|named)\s+|the\s+video\s+|video\s+)?(.+?)\s+(?:on\s+youtube)\b",
        r"\bon\s+youtube\s+(?:search\s+for|look\s+up|play|watch|find|put\s+on|queue\s+up|pull\s+up)\s+(.+)$",
        r"^(.+?)\s+(?:on\s+youtube)\b",
    )
    for pattern in query_patterns:
        match = re.search(pattern, goal, flags=re.IGNORECASE)
        if not match:
            continue
        query = _clean_youtube_query(match.group(1))
        if query:
            return {
                "action": "search",
                "query": query,
                "prefer_video_results": True,
            }

    if re.search(r"\b(open|launch|start|go to|navigate to|pull up|bring up)\b", lowered_goal):
        return {"action": "home"}

    return {"action": "home"}


def _extract_discord_message_arguments(goal: str) -> dict[str, Any] | None:
    lowered_goal = goal.lower()
    if not _looks_like_discord_message_goal(lowered_goal):
        return None

    discord_name = r"(?:discord|disc\s*cord|dis\s*cord|chord|cord)"
    patterns = (
        rf"\bsend\s+(?:a\s+)?{discord_name}\s+(?:a\s+)?message\s*"
        r"(?:saying|that\s+says|with|:)?\s*[,;:-]?\s*(.+)$",
        rf"\bopen\s+(?:a\s+)?{discord_name}\s*[,;-]?\s*(?:and\s+)?"
        r"(?:send|post|paste|type|write|reply|say|drop)\s+"
        r"(?:a\s+)?(?:message\s+)?(?:saying|that\s+says|with|:)?\s*[,;:-]?\s*(.+)$",
        r"\b(?:send|post|paste|type|write|reply|say|drop)\s+(?:a\s+)?(?:message\s+)?"
        rf"(?:to|in|on)\s+(?:a\s+)?{discord_name}(?:\s+(?:saying|that\s+says|with)|\s*[:,-])?\s+(.+)$",
        rf"\b{discord_name}(?:,)?\s*(?:and\s+)?(?:send|post|paste|type|write|reply|say|drop)\s+"
        r"(?:a\s+)?(?:message\s+)?(?:saying|that\s+says|with|:)?\s*[,;:-]?\s*(.+)$",
        r"\b(?:send|post)\s+(?:this\s+)?(?:message\s+)?"
        rf"(?:to\s+)?(?:the\s+)?(?:active\s+)?(?:a\s+)?{discord_name}\s+"
        r"(?:chat|channel|conversation)?(?:\s*[:,-])?\s+(.+)$",
        r"\b(?:send|post|paste|type|write|reply|drop)\s+(?:a\s+)?message\s*"
        r"(?:saying|that\s+says|with|:)?\s*[,;:-]?\s*(.+)$",
    )
    for pattern in patterns:
        match = re.search(pattern, goal, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            continue
        text = _clean_message_text(match.group(1))
        if text:
            return {
                "text": text,
                "open_if_needed": True,
            }

    parts = re.split(rf"\b{discord_name}\b", goal, flags=re.IGNORECASE, maxsplit=1)
    if len(parts) == 2:
        text = _clean_message_text(
            re.sub(
                r"^\s*[,;:-]?\s*(?:and\s+)?(?:please\s+)?"
                r"(?:(?:send|post|paste|type|write|reply|say|drop)\s+)?"
                r"(?:a\s+)?(?:message\s+)?(?:saying|that\s+says|with)?\s*[,;:-]?\s*",
                "",
                parts[1],
                flags=re.IGNORECASE,
            )
        )
        if text:
            return {
                "text": text,
                "open_if_needed": True,
            }

    return None


def _looks_like_discord_message_goal(lowered_goal: str) -> bool:
    has_discordish_word = re.search(
        r"\b(?:discord|disc\s*cord|dis\s*cord|chord|cord)\b",
        lowered_goal,
    )
    has_send_message_shape = re.search(
        r"\b(?:send|post|paste|type|write|reply|drop)\s+(?:a\s+)?message\b",
        lowered_goal,
    )
    return bool(has_discordish_word or has_send_message_shape)


def _clean_message_text(text: str) -> str:
    cleaned = text.strip(" \t\n\r")
    cleaned = re.sub(
        r"^(?:saying|say|that\s+says|message\s+is|message)\s*[,;:-]?\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned.strip(" \t\n\r.,;:\"'")


def _clean_email_recipient(text: str) -> str:
    cleaned = text.strip(" \t\n\r.,;:\"'")
    cleaned = re.sub(r"^(?:my|the|a|an)\s+", "", cleaned, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", cleaned).strip(" \t\n\r.,;:\"'")


def _clean_email_subject(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text.strip(" \t\n\r.,;:\"'"))
    return cleaned[:300].strip()


def _clean_email_body(text: str) -> str:
    cleaned = text.strip(" \t\n\r")
    cleaned = re.sub(
        r"^(?:saying|say|that\s+says|body|message|the\s+message\s+is)\s*[,;:-]?\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned.strip(" \t\n\r\"'")


def _clean_course_query(text: str) -> str:
    cleaned = text.strip(" \t\n\r.,;:\"'")
    cleaned = re.sub(r"^(?:my|the|a|an)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"\b(?:please|canvas|navigate|open|show|bring|pull|load|go|take|me|up)\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" \t\n\r.,;:\"'")


def _clean_youtube_query(query: str) -> str:
    cleaned = query.strip(" \t\n\r.,;:\"'")
    cleaned = re.sub(r"\s+(?:on\s+youtube|youtube)$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(?:youtube\s+)?", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip(" \t\n\r.,;:\"'")


def _clean_code_request(goal: str) -> str:
    cleaned = goal.strip(" \t\n\r")
    cleaned = re.sub(r"^(?:computer|jarvis)\s*[,;:-]?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"\b(?:open|put|paste)\s+(?:it\s+)?(?:in|into)\s+"
        r"(?:vs\s*code|vscode|visual\s+studio\s+code)\b",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\b(?:and\s+)?(?:open|show)\s+(?:a\s+)?(?:new\s+)?"
        r"(?:vs\s*code|vscode|visual\s+studio\s+code)\s+(?:window|instance)?\b",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\s+(?:in|into|inside)\s+(?:vs\s*code|vscode|visual\s+studio\s+code)\b",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" \t\n\r.,;:?!\"'")


def _guess_code_language(goal: str, code: str = "") -> str | None:
    combined = f"{goal}\n{code}".lower()
    language_markers = (
        ("typescript", ("typescript", " ts ", ".ts", "tsx")),
        ("javascript", ("javascript", " js ", ".js", "node", "express")),
        ("python", ("python", ".py", "fastapi", "flask", "django", "pytest")),
        ("swift", ("swift", "swiftui", ".swift", "xcode")),
        ("html", ("html", "<!doctype html", "<html")),
        ("css", ("css", "stylesheet")),
        ("react", ("react", "jsx", "tsx")),
        ("csharp", ("c#", "csharp", ".cs")),
        ("cpp", ("c++", "cpp", ".cpp")),
        ("java", ("java", ".java")),
        ("go", ("golang", " go ")),
        ("rust", ("rust", ".rs")),
        ("kotlin", ("kotlin", ".kt")),
        ("ruby", ("ruby", ".rb", "rails")),
        ("lua", ("lua", ".lua")),
        ("bash", ("bash", "shell script", ".sh")),
        ("powershell", ("powershell", ".ps1")),
        ("sql", ("sql", "database query")),
    )
    padded = f" {combined} "
    for language, markers in language_markers:
        if any(marker in padded for marker in markers):
            return language
    return None


def _clean_browser_target(target: str) -> str:
    cleaned = target.strip(" \t\n\r.,;:\"'")
    cleaned = re.sub(r"^(?:the\s+)?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+(?:website|web\s+site|webpage|web\s+page)$", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip(" \t\n\r.,;:\"'")
