from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class DesktopBackend(ABC):
    @abstractmethod
    def capture_screen(self) -> dict[str, Any]:
        """Return a platform-specific screen capture payload."""

    @abstractmethod
    def launch_app(self, app_name: str) -> dict[str, Any]:
        """Launch an allowlisted desktop application."""

    @abstractmethod
    def type_text(self, text: str) -> dict[str, Any]:
        """Type text into the currently focused desktop application."""

    @abstractmethod
    def open_browser(self, url: str) -> dict[str, Any]:
        """Open the default browser to an http(s) URL."""
