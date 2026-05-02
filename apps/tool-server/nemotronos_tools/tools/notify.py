from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def notify_user(arguments: dict[str, Any]) -> dict[str, Any]:
    message = str(arguments.get("message", "")).strip()
    if not message:
        raise ValueError("notify_user requires a non-empty message.")

    return {
        "delivered": True,
        "message": message,
        "channel": "mock_dashboard",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
