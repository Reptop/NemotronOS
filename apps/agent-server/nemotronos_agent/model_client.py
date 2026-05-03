from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any

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
    ) -> PlannedToolCall:
        del tool_definitions, previous_result
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
        browser_target = _extract_browser_target(goal)
        if browser_target:
            return PlannedToolCall(
                name="browser_open",
                arguments={"url": browser_target},
                rationale="Open the requested website in the default browser.",
            )
        if self._should_force_notepad_launch(goal):
            return PlannedToolCall(
                name="app_launch",
                arguments={"app_name": "notepad"},
                rationale="Launch Notepad before typing the requested note.",
            )

        payload = {
            "model": self.settings.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are NemotronOS, a private Windows PC agent. "
                        "Pick exactly one next tool call. Use Windows-style paths. "
                        "If the user asks to organize Downloads and see the plan first, "
                        f"call fs_plan_changes on {self.settings.default_downloads_path}. "
                        "Do not invent tools that are not in the provided tool list."
                    ),
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

        planned_call = await self._request_tool_call(payload, tool_definitions)
        arguments = planned_call.arguments
        tool_name = planned_call.name
        if force_downloads_plan and tool_name == "fs_plan_changes":
            arguments = self._normalize_downloads_plan_arguments(goal, arguments)

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
                        "Do not include command words, app names, or instruction wording."
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
            ],
            "tools": [
                {"type": "function", "function": definition}
                for definition in tool_definitions
            ],
            "tool_choice": {
                "type": "function",
                "function": {"name": "keyboard_type"},
            },
            "max_tokens": 256,
        }
        return await self._request_tool_call(payload, tool_definitions)

    async def _request_tool_call(
        self,
        payload: dict[str, Any],
        tool_definitions: list[dict[str, Any]],
    ) -> PlannedToolCall:
        headers = {"Authorization": f"Bearer {self.settings.model_api_key}"}
        url = f"{self.settings.model_base_url.rstrip('/')}/chat/completions"
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


def build_model_client(settings: AgentServerSettings) -> ModelClient:
    if settings.model_mode == "openai_compatible":
        return OpenAICompatibleModelClient(settings)
    return MockModelClient(settings)


def _extract_browser_target(goal: str) -> str | None:
    lowered_goal = goal.lower()
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


def _clean_browser_target(target: str) -> str:
    cleaned = target.strip(" \t\n\r.,;:\"'")
    cleaned = re.sub(r"^(?:the\s+)?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+(?:website|web\s+site|webpage|web\s+page)$", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip(" \t\n\r.,;:\"'")
