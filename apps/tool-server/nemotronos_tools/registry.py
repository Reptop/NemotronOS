from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .config import ToolServerSettings
from .path_mapper import FakeWindowsPathMapper
from .plan_store import PlanStore
from .tools.desktop_base import DesktopBackend
from .tools.desktop_actions import app_launch, browser_open, keyboard_type
from .tools.desktop_mock_windows import MockWindowsDesktopBackend
from .tools.desktop_windows import WindowsDesktopBackend
from .tools.filesystem import FilesystemToolService
from .tools.notify import notify_user
from .tools.screen import screen_capture
from .tools.shell import shell_run


ToolHandler = Callable[[dict[str, Any]], dict[str, Any]]


class ToolRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, ToolHandler] = {}

    def register(self, name: str, handler: ToolHandler) -> None:
        self._handlers[name] = handler

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name not in self._handlers:
            raise ValueError(f"Unknown tool: {name}")
        return self._handlers[name](arguments)

    @property
    def names(self) -> list[str]:
        return sorted(self._handlers)


def _build_desktop_backend(settings: ToolServerSettings) -> DesktopBackend:
    if settings.tool_mode == "windows":
        return WindowsDesktopBackend()
    return MockWindowsDesktopBackend()


def build_tool_registry(settings: ToolServerSettings) -> ToolRegistry:
    path_mapper = FakeWindowsPathMapper(settings.fake_windows_root)
    plan_store = PlanStore()
    filesystem_tools = FilesystemToolService(path_mapper=path_mapper, plan_store=plan_store)
    desktop_backend = _build_desktop_backend(settings)

    registry = ToolRegistry()
    registry.register("fs_plan_changes", filesystem_tools.fs_plan_changes)
    registry.register("fs_apply_changes", filesystem_tools.fs_apply_changes)
    registry.register("demo_reset_downloads", filesystem_tools.reset_demo_downloads)
    registry.register("notify_user", notify_user)
    registry.register(
        "screen_capture",
        lambda arguments: screen_capture(arguments, desktop_backend),
    )
    registry.register(
        "app_launch",
        lambda arguments: app_launch(arguments, desktop_backend),
    )
    registry.register(
        "keyboard_type",
        lambda arguments: keyboard_type(arguments, desktop_backend),
    )
    registry.register(
        "browser_open",
        lambda arguments: browser_open(arguments, desktop_backend),
    )
    registry.register("shell_run", shell_run)
    return registry
