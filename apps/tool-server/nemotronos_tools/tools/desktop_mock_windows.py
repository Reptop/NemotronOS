from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .desktop_base import DesktopBackend


class MockWindowsDesktopBackend(DesktopBackend):
    def capture_screen(self) -> dict[str, Any]:
        captured_at = datetime.now(timezone.utc).isoformat()
        return {
            "mode": "mock_windows",
            "captured_at": captured_at,
            "summary": "Mock screen capture from the fake Windows desktop.",
            "visible_windows": [
                "File Explorer - Downloads",
                "NemotronOS Dashboard",
            ],
            "image_ref": "mock://screen/latest",
        }

    def launch_app(self, app_name: str) -> dict[str, Any]:
        return {
            "mode": "mock_windows",
            "app_name": app_name,
            "launched": True,
            "window_title": f"{app_name.title()} - Mock Window",
            "launched_at": datetime.now(timezone.utc).isoformat(),
        }

    def type_text(self, text: str) -> dict[str, Any]:
        return {
            "mode": "mock_windows",
            "typed": True,
            "characters": len(text),
            "typed_at": datetime.now(timezone.utc).isoformat(),
        }

    def open_browser(self, url: str) -> dict[str, Any]:
        return {
            "mode": "mock_windows",
            "opened": True,
            "url": url,
            "browser": "default",
            "opened_at": datetime.now(timezone.utc).isoformat(),
        }
