from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class DesktopBackend(ABC):
    @abstractmethod
    def capture_screen(self) -> dict[str, Any]:
        """Return a platform-specific screen capture payload."""
