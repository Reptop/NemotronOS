from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

import httpx
from pydantic import BaseModel

from .config import AgentServerSettings


DEFAULT_DOWNLOADS_PATH = r"C:\Users\Raed\Downloads"


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


class MockModelClient(ModelClient):
    async def plan_first_action(
        self, goal: str, tool_definitions: list[dict[str, Any]]
    ) -> PlannedToolCall:
        del tool_definitions

        lowered_goal = goal.lower()
        if "organize" in lowered_goal and "download" in lowered_goal:
            return PlannedToolCall(
                name="fs_plan_changes",
                arguments={
                    "root_path": DEFAULT_DOWNLOADS_PATH,
                    "goal": goal,
                    "allowed_operations": ["mkdir", "move"],
                },
                rationale="Create a dry-run organization plan for the Downloads folder first.",
            )

        return PlannedToolCall(
            name="notify_user",
            arguments={
                "message": f"Mock mode does not have a richer plan for: {goal}",
            },
            rationale="Fallback response for an unsupported mock goal.",
        )


class OpenAICompatibleModelClient(ModelClient):
    def __init__(self, settings: AgentServerSettings) -> None:
        self.settings = settings

    async def plan_first_action(
        self, goal: str, tool_definitions: list[dict[str, Any]]
    ) -> PlannedToolCall:
        payload = {
            "model": self.settings.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are NemotronOS, a private Windows PC agent. "
                        "Pick exactly one next tool call. Use Windows-style paths. "
                        "If the user asks to organize Downloads and see the plan first, "
                        "call fs_plan_changes on C:\\Users\\Raed\\Downloads."
                    ),
                },
                {"role": "user", "content": goal},
            ],
            "tools": [
                {"type": "function", "function": definition}
                for definition in tool_definitions
            ],
            "tool_choice": "auto",
        }

        headers = {"Authorization": f"Bearer {self.settings.model_api_key}"}
        url = f"{self.settings.model_base_url.rstrip('/')}/chat/completions"
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()

        data = response.json()
        message = data["choices"][0]["message"]
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            raise RuntimeError("OpenAI-compatible model did not return a tool call.")

        tool_call = tool_calls[0]
        raw_arguments = tool_call["function"].get("arguments", "{}")
        arguments = raw_arguments if isinstance(raw_arguments, dict) else json.loads(raw_arguments)
        return PlannedToolCall(
            name=tool_call["function"]["name"],
            arguments=arguments,
            rationale=message.get("content"),
        )


def build_model_client(settings: AgentServerSettings) -> ModelClient:
    if settings.model_mode == "openai_compatible":
        return OpenAICompatibleModelClient(settings)
    return MockModelClient()
