from __future__ import annotations

from typing import Any

from .desktop_base import DesktopBackend


class WindowsDesktopBackend(DesktopBackend):
    def capture_screen(self) -> dict[str, Any]:
        raise NotImplementedError("The real Windows desktop backend is not implemented yet.")
