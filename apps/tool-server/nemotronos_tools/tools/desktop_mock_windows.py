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
