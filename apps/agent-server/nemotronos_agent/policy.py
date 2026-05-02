from __future__ import annotations

from typing import Any

from pydantic import BaseModel


DANGEROUS_SHELL_PATTERNS = (
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


class PolicyDecision(BaseModel):
    tool_name: str
    risk_level: str
    allowed: bool
    reason: str


class PolicyEngine:
    def classify(self, tool_name: str, arguments: dict[str, Any]) -> PolicyDecision:
        if tool_name in {"screen_capture", "fs_plan_changes", "notify_user"}:
            return PolicyDecision(
                tool_name=tool_name,
                risk_level="low",
                allowed=True,
                reason=f"{tool_name} is read-only or user-informing.",
            )

        if tool_name == "fs_apply_changes":
            return PolicyDecision(
                tool_name=tool_name,
                risk_level="medium",
                allowed=True,
                reason="Applying filesystem changes modifies user files and needs approval.",
            )

        if tool_name == "shell_run":
            command = str(arguments.get("command", "")).lower()
            for pattern in DANGEROUS_SHELL_PATTERNS:
                if pattern in command:
                    return PolicyDecision(
                        tool_name=tool_name,
                        risk_level="high",
                        allowed=False,
                        reason=f"Blocked shell command containing dangerous pattern: {pattern}",
                    )
            return PolicyDecision(
                tool_name=tool_name,
                risk_level="medium",
                allowed=True,
                reason="Shell access is allowed only through the safe mock policy path.",
            )

        if tool_name in {"email_send_draft", "purchase_submit", "payment_finalize"}:
            return PolicyDecision(
                tool_name=tool_name,
                risk_level="high",
                allowed=True,
                reason="High-impact action requires explicit confirmation.",
            )

        return PolicyDecision(
            tool_name=tool_name,
            risk_level="medium",
            allowed=True,
            reason="Defaulting unknown tool usage to medium risk.",
        )
