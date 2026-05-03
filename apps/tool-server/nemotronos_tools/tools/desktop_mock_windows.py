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

    def describe_screen(self, include_screenshot: bool, max_windows: int) -> dict[str, Any]:
        captured_at = datetime.now(timezone.utc).isoformat()
        visible_windows = [
            {
                "title": "NemotronOS Dashboard",
                "process_id": 1001,
                "bounds": {"left": 0, "top": 0, "right": 1280, "bottom": 900},
            },
            {
                "title": "File Explorer - Downloads",
                "process_id": 1002,
                "bounds": {"left": 80, "top": 80, "right": 980, "bottom": 720},
            },
        ][:max(1, max_windows)]
        return {
            "mode": "mock_windows",
            "captured_at": captured_at,
            "foreground_window": visible_windows[0],
            "visible_windows": visible_windows,
            "focused_element": {
                "role": "window",
                "name": visible_windows[0]["title"],
            },
            "screen_summary": "Mock desktop showing the NemotronOS dashboard and a Downloads folder.",
            **(
                {
                    "screenshot": {
                        "image_ref": "mock://screen/latest",
                        "summary": "Mock screen capture from the fake Windows desktop.",
                    }
                }
                if include_screenshot
                else {}
            ),
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

    def create_sticky_note(self, text: str) -> dict[str, Any]:
        return {
            "mode": "mock_windows",
            "app_name": "sticky_notes",
            "created": True,
            "inserted": True,
            "input_method": "mock_paste",
            "characters": len(text),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    def open_code_editor(
        self,
        code: str,
        language: str,
        open_new_window: bool,
        command: str,
    ) -> dict[str, Any]:
        return {
            "mode": "mock_windows",
            "editor": "vscode",
            "command": command,
            "opened": True,
            "open_new_window": open_new_window,
            "inserted": True,
            "input_method": "mock_paste",
            "characters": len(code),
            **({"language": language} if language else {}),
            "opened_at": datetime.now(timezone.utc).isoformat(),
        }

    def press_enter(self) -> dict[str, Any]:
        return {
            "mode": "mock_windows",
            "pressed": "enter",
            "pressed_at": datetime.now(timezone.utc).isoformat(),
        }

    def press_escape(self) -> dict[str, Any]:
        return {
            "mode": "mock_windows",
            "pressed": "escape",
            "pressed_at": datetime.now(timezone.utc).isoformat(),
        }

    def open_browser(self, url: str) -> dict[str, Any]:
        return {
            "mode": "mock_windows",
            "opened": True,
            "url": url,
            "browser": "default",
            "opened_at": datetime.now(timezone.utc).isoformat(),
        }

    def focus_window(self, title_hint: str) -> dict[str, Any]:
        return {
            "mode": "mock_windows",
            "focused": True,
            "title_hint": title_hint,
            "focused_at": datetime.now(timezone.utc).isoformat(),
        }

    def click_at(self, x: int, y: int) -> dict[str, Any]:
        return {
            "mode": "mock_windows",
            "clicked": True,
            "x": x,
            "y": y,
            "clicked_at": datetime.now(timezone.utc).isoformat(),
        }

    def click_foreground_relative(self, x_ratio: float, y_ratio: float) -> dict[str, Any]:
        return {
            "mode": "mock_windows",
            "clicked": True,
            "x_ratio": x_ratio,
            "y_ratio": y_ratio,
            "foreground_window": {
                "left": 0,
                "top": 0,
                "right": 1920,
                "bottom": 1080,
            },
            "x": int(1920 * x_ratio),
            "y": int(1080 * y_ratio),
            "clicked_at": datetime.now(timezone.utc).isoformat(),
        }
