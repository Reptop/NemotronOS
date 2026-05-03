from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class DesktopBackend(ABC):
    @abstractmethod
    def capture_screen(self) -> dict[str, Any]:
        """Return a platform-specific screen capture payload."""

    @abstractmethod
    def describe_screen(self, include_screenshot: bool, max_windows: int) -> dict[str, Any]:
        """Return structured accessibility context for the current desktop."""

    @abstractmethod
    def launch_app(self, app_name: str) -> dict[str, Any]:
        """Launch an allowlisted desktop application."""

    @abstractmethod
    def type_text(self, text: str) -> dict[str, Any]:
        """Type text into the currently focused desktop application."""

    @abstractmethod
    def create_sticky_note(self, text: str) -> dict[str, Any]:
        """Create a local desktop sticky note containing text."""

    @abstractmethod
    def open_code_editor(
        self,
        code: str,
        language: str,
        open_new_window: bool,
        command: str,
    ) -> dict[str, Any]:
        """Open a code editor and insert generated code without saving a user file."""

    @abstractmethod
    def press_enter(self) -> dict[str, Any]:
        """Press Enter in the currently focused desktop application."""

    @abstractmethod
    def press_escape(self) -> dict[str, Any]:
        """Press Escape in the currently focused desktop application."""

    @abstractmethod
    def open_browser(self, url: str) -> dict[str, Any]:
        """Open the default browser to an http(s) URL."""

    @abstractmethod
    def focus_window(self, title_hint: str) -> dict[str, Any]:
        """Focus a visible desktop window whose title contains the hint."""

    @abstractmethod
    def click_at(self, x: int, y: int) -> dict[str, Any]:
        """Click an absolute desktop coordinate."""

    @abstractmethod
    def click_foreground_relative(self, x_ratio: float, y_ratio: float) -> dict[str, Any]:
        """Click a coordinate relative to the foreground window bounds."""
