from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel

from .config import AgentServerSettings


class PlannedToolCall(BaseModel):
    name: str
    arguments: dict[str, Any]
    rationale: str | None = None


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


class MockModelClient(ModelClient):
    def __init__(self, settings: AgentServerSettings) -> None:
        self.settings = settings

    async def plan_first_action(
        self, goal: str, tool_definitions: list[dict[str, Any]]
    ) -> PlannedToolCall:
        del tool_definitions

        lowered_goal = goal.lower()
        if "organize" in lowered_goal and "download" in lowered_goal:
            return PlannedToolCall(
                name="fs_plan_changes",
                arguments={
                    "root_path": self.settings.default_downloads_path,
                    "goal": goal,
                    "allowed_operations": ["mkdir", "move"],
                },
                rationale="Create a dry-run organization plan for the Downloads folder first.",
            )

        discord_arguments = _extract_discord_message_arguments(goal)
        if discord_arguments:
            return PlannedToolCall(
                name="discord_send_message",
                arguments=discord_arguments,
                rationale="Send the requested message to the active Discord conversation.",
            )

        canvas_arguments = _extract_canvas_arguments(goal)
        if canvas_arguments:
            return PlannedToolCall(
                name="canvas_open_course",
                arguments=canvas_arguments,
                rationale="Open Canvas and navigate to the requested course.",
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
        arguments = self._normalize_first_action_arguments(goal, tool_name, arguments)

        return PlannedToolCall(
            name=tool_name,
            arguments=arguments,
            rationale=planned_call.rationale,
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
                    "content": (
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

    def _first_action_system_prompt(self) -> str:
        return (
            "You are NemotronOS, a private Windows PC agent. "
            "Interpret the user's request, including short or noisy voice transcripts, "
            "and pick exactly one next tool call from the provided tool list. "
            "Do not answer in prose. Do not invent tools. "
            "Use Windows-style paths when paths are needed. "
            "If the user asks to organize Downloads and see the plan first, call "
            f"fs_plan_changes on {self.settings.default_downloads_path}. "
            "If the user asks to type in Notepad, call app_launch with app_name='notepad'; "
            "the coordinator will type the requested text afterward. "
            "If the user asks for a website/domain/URL, call browser_open. "
            "If the user asks for a general browser task that requires reading or interacting "
            "with page content over multiple steps, prefer the managed browser automation tools: "
            "browser_session_ensure, browser_navigate, browser_snapshot, browser_click, "
            "browser_type, browser_select_option, and browser_press. "
            "If the user asks for Canvas course navigation, call canvas_open_course with "
            "the natural course name in course_query. "
            "If the user asks for YouTube content, call youtube_open. Use action='random' "
            "for random/recommended video requests, action='search' with query and "
            "prefer_video_results=true for video/title/channel searches, and action='video' "
            "only for exact YouTube URLs or IDs. "
            "If the user asks to send/post/type a message to Discord or the active chat, "
            "call discord_send_message with only the message body in text. "
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
        return (
            "You are NemotronOS's tool router. Return only one compact JSON object "
            "and no other text. Do not include markdown, XML tags, <think>, or explanation. "
            "The JSON schema is exactly: "
            '{"name":"tool_name","arguments":{},"rationale":"short reason"}. '
            f"Allowed tools: {tool_names}.{forced_tool} "
            "Interpret short or noisy voice transcripts naturally. "
            "For generic web tasks that require reading or interacting with live page content, "
            "prefer browser_session_ensure, browser_navigate, browser_snapshot, browser_click, "
            "browser_type, browser_select_option, and browser_press. "
            "For YouTube searches, use youtube_open with action='search', query, "
            "and prefer_video_results=true. "
            "For random YouTube video requests, use youtube_open with action='random'. "
            "For Notepad typing, use app_launch with app_name='notepad'. "
            "For Discord messages, use discord_send_message and put only the message body "
            "in text. For Canvas course navigation, use canvas_open_course. "
            "For normal websites/domains/URLs, use browser_open. "
            f"Tool schemas: {tool_schemas}"
        )

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

    def _should_force_downloads_plan(self, goal: str) -> bool:
        lowered_goal = goal.lower()
        return "organize" in lowered_goal and "download" in lowered_goal

    def _should_force_notepad_launch(self, goal: str) -> bool:
        lowered_goal = goal.lower()
        return "notepad" in lowered_goal and "type" in lowered_goal

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
        return arguments

    def _fallback_first_action(self, goal: str) -> PlannedToolCall:
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

        canvas_arguments = _extract_canvas_arguments(goal)
        if canvas_arguments:
            return PlannedToolCall(
                name="canvas_open_course",
                arguments=canvas_arguments,
                rationale="Fallback parser routed Canvas course navigation.",
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


def build_model_client(settings: AgentServerSettings) -> ModelClient:
    if settings.model_mode == "openai_compatible":
        return OpenAICompatibleModelClient(settings)
    return MockModelClient(settings)


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
            "open site",
            "open webpage",
            "open web page",
        )
    )
    if not browser_intent:
        return None

    patterns = (
        r"\b(?:navigate|go|browse)\s+to\s+(.+)$",
        r"\bopen\s+(?:my\s+)?(?:web\s*)?browser\s+(?:and\s+)?(?:navigate\s+to|go\s+to|to)\s+(.+)$",
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
        r"^(?:please\s+)?(?:open|navigate|go|browse)\s+(?:to\s+)?",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"^(?:please\s+)?to\s+", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip(" \t\n\r.,;:\"'")


def _extract_canvas_arguments(goal: str) -> dict[str, Any] | None:
    lowered_goal = goal.lower()
    if "canvas" not in lowered_goal:
        return None
    if not re.search(r"\b(course|class)\b", lowered_goal):
        return None

    patterns = (
        r"\bcanvas\b.*?\b(?:navigate|go|open|take)\s+(?:me\s+)?(?:to\s+)?"
        r"(?:my\s+|the\s+)?(.+?)\s+(?:course|class)\b",
        r"\b(?:navigate|go|open|take)\s+(?:me\s+)?(?:to\s+)?"
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


def _extract_youtube_arguments(goal: str) -> dict[str, Any] | None:
    lowered_goal = goal.lower()
    if "youtube" not in lowered_goal and "youtu.be" not in lowered_goal:
        return None

    url_match = re.search(r"https?://(?:www\.)?(?:youtube\.com|youtu\.be)\S+", goal, flags=re.IGNORECASE)
    if url_match:
        return {"action": "video", "video_url": url_match.group(0).rstrip(".,;")}

    if re.search(r"\b(random|recommend|recommended|surprise me)\b", lowered_goal):
        return {"action": "random"}

    query_patterns = (
        r"\b(?:search\s+(?:youtube\s+)?for)\s+(.+)$",
        r"\b(?:play|watch|open|find)\s+(?:a\s+video\s+(?:called|named)\s+|the\s+video\s+|video\s+)?(.+?)\s+(?:on\s+youtube)\b",
        r"\bon\s+youtube\s+(?:search\s+for|play|watch|find)\s+(.+)$",
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

    if re.search(r"\b(open|go to|navigate to)\b", lowered_goal):
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
        r"(?:send|post|paste|type|write)\s+"
        r"(?:a\s+)?(?:message\s+)?(?:saying|that\s+says|with|:)?\s*[,;:-]?\s*(.+)$",
        r"\b(?:send|post|paste|type|write)\s+(?:a\s+)?(?:message\s+)?"
        rf"(?:to|in|on)\s+(?:a\s+)?{discord_name}(?:\s+(?:saying|that\s+says|with)|\s*[:,-])?\s+(.+)$",
        rf"\b{discord_name}(?:,)?\s*(?:and\s+)?(?:send|post|paste|type|write)\s+"
        r"(?:a\s+)?(?:message\s+)?(?:saying|that\s+says|with|:)?\s*[,;:-]?\s*(.+)$",
        r"\b(?:send|post)\s+(?:this\s+)?(?:message\s+)?"
        rf"(?:to\s+)?(?:the\s+)?(?:active\s+)?(?:a\s+)?{discord_name}\s+"
        r"(?:chat|channel|conversation)?(?:\s*[:,-])?\s+(.+)$",
        r"\b(?:send|post|paste|type|write)\s+(?:a\s+)?message\s*"
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
                r"(?:(?:send|post|paste|type|write)\s+)?"
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
        r"\b(?:send|post|paste|type|write)\s+(?:a\s+)?message\b",
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


def _clean_course_query(text: str) -> str:
    cleaned = text.strip(" \t\n\r.,;:\"'")
    cleaned = re.sub(r"^(?:my|the|a|an)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"\b(?:please|canvas|navigate|open|go|take|me)\b",
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


def _clean_browser_target(target: str) -> str:
    cleaned = target.strip(" \t\n\r.,;:\"'")
    cleaned = re.sub(r"^(?:the\s+)?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+(?:website|web\s+site|webpage|web\s+page)$", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip(" \t\n\r.,;:\"'")
