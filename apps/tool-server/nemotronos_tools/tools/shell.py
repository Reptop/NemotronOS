from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


DANGEROUS_PATTERNS = (
    "rm -rf",
    "del /s",
    "format",
    "shutdown",
    "reg delete",
    "sudo",
    "curl | bash",
    "invoke-webrequest",
    "chmod",
    "chown",
)


def shell_run(arguments: dict[str, Any]) -> dict[str, Any]:
    command = str(arguments.get("command", "")).strip()
    if not command:
        raise ValueError("shell_run requires a non-empty command.")

    lowered = command.lower()
    for pattern in DANGEROUS_PATTERNS:
        if pattern in lowered:
            raise ValueError(f"Rejected dangerous shell command pattern: {pattern}")

    return {
        "mode": "mock_windows",
        "command": command,
        "stdout": "",
        "stderr": "",
        "exit_code": 0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "note": "shell_run is a safe stub in TOOL_MODE=mock_windows.",
    }
