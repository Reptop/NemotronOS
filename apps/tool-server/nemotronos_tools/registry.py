from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .config import ToolServerSettings
from .path_mapper import FakeWindowsPathMapper
from .plan_store import PlanStore
from .tools.desktop_base import DesktopBackend
from .tools.browser_actions import (
    browser_click,
    browser_navigate,
    browser_press,
    browser_select_option,
    browser_session_ensure,
    browser_snapshot,
    browser_type,
    gmail_compose_draft,
    gmail_open,
    gmail_search,
    gmail_send_current_draft,
)
from .tools.browser_automation import build_browser_automation_service
from .tools.desktop_actions import (
    app_launch,
    browser_open,
    canvas_open_course,
    discord_send_message,
    keyboard_type,
    mouse_click,
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
    browser_service = build_browser_automation_service(settings)

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
        "browser_session_ensure",
        lambda arguments: browser_session_ensure(arguments, browser_service),
    )
    registry.register(
        "browser_navigate",
        lambda arguments: browser_navigate(arguments, browser_service),
    )
    registry.register(
        "browser_snapshot",
        lambda arguments: browser_snapshot(arguments, browser_service),
    )
    registry.register(
        "browser_click",
        lambda arguments: browser_click(arguments, browser_service),
    )
    registry.register(
        "browser_type",
        lambda arguments: browser_type(arguments, browser_service),
    )
    registry.register(
        "browser_select_option",
        lambda arguments: browser_select_option(arguments, browser_service),
    )
    registry.register(
        "browser_press",
        lambda arguments: browser_press(arguments, browser_service),
    )
    registry.register(
        "gmail_open",
        lambda arguments: gmail_open(arguments, browser_service),
    )
    registry.register(
        "gmail_search",
        lambda arguments: gmail_search(arguments, browser_service),
    )
    registry.register(
        "gmail_compose_draft",
        lambda arguments: gmail_compose_draft(arguments, browser_service),
    )
    registry.register(
        "gmail_send_current_draft",
        lambda arguments: gmail_send_current_draft(arguments, browser_service),
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
