from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .config import ToolServerSettings
from .path_mapper import FakeWindowsPathMapper
from .plan_store import PlanStore
from .tools.desktop_base import DesktopBackend
from .tools.desktop_actions import (
    app_launch,
    browser_open,
    canvas_open_course,
    discord_send_message,
    keyboard_type,
    mouse_click,
    vscode_paste_code,
    youtube_click_video,
    youtube_open,
)
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
        "vscode_paste_code",
        lambda arguments: vscode_paste_code(
            arguments,
            desktop_backend,
            settings.vscode_command,
        ),
    )
    registry.register(
        "discord_send_message",
        lambda arguments: discord_send_message(arguments, desktop_backend),
    )
    registry.register(
        "mouse_click",
        lambda arguments: mouse_click(arguments, desktop_backend),
    )
    registry.register(
        "browser_open",
        lambda arguments: browser_open(arguments, desktop_backend),
    )
    registry.register(
        "canvas_open_course",
        lambda arguments: canvas_open_course(
            arguments,
            desktop_backend,
            settings.canvas_base_url,
            settings.canvas_course_aliases,
            settings.canvas_api_token,
        ),
    )
    registry.register(
        "youtube_open",
        lambda arguments: youtube_open(arguments, desktop_backend),
    )
    registry.register(
        "youtube_click_video",
        lambda arguments: youtube_click_video(arguments, desktop_backend),
    )
    registry.register("shell_run", shell_run)
    return registry
