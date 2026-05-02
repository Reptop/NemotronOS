from __future__ import annotations

from typing import Any

from .tool_defs import tool_definitions


class ToolRegistry:
    def __init__(self) -> None:
        self._definitions = {tool["name"]: tool for tool in tool_definitions()}

    def definitions(self) -> list[dict[str, Any]]:
        return list(self._definitions.values())

    def get(self, name: str) -> dict[str, Any] | None:
        return self._definitions.get(name)
