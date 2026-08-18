from __future__ import annotations

from typing import Any

from .desktop_base import DesktopBackend


def screen_capture(arguments: dict[str, Any], desktop_backend: DesktopBackend) -> dict[str, Any]:
    del arguments
    return desktop_backend.capture_screen()


def screenshot_open(arguments: dict[str, Any], desktop_backend: DesktopBackend) -> dict[str, Any]:
    del arguments
    return desktop_backend.open_last_screenshot()
