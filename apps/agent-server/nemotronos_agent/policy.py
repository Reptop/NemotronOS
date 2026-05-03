from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

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

        if tool_name == "app_launch":
            app_name = str(arguments.get("app_name", "")).strip().lower()
            if app_name not in {"notepad", "calculator", "calc", "paint", "mspaint"}:
                return PolicyDecision(
                    tool_name=tool_name,
                    risk_level="medium",
                    allowed=False,
                    reason=f"App launch is restricted to known demo apps. Rejected: {app_name}",
                )
            return PolicyDecision(
                tool_name=tool_name,
                risk_level="low",
                allowed=True,
                reason="Launching an allowlisted local demo app is low risk.",
            )

        if tool_name == "keyboard_type":
            text = str(arguments.get("text", ""))
            if len(text) > 500:
                return PolicyDecision(
                    tool_name=tool_name,
                    risk_level="medium",
                    allowed=False,
                    reason="Keyboard typing is limited to 500 characters in the demo path.",
                )
            return PolicyDecision(
                tool_name=tool_name,
                risk_level="medium",
                allowed=True,
                reason="Typing into the active app changes desktop state and is limited to demo text.",
            )

        if tool_name in {"mouse_click", "youtube_click_video"}:
            return PolicyDecision(
                tool_name=tool_name,
                risk_level="medium",
                allowed=True,
                reason="Mouse clicks change desktop/browser state and are limited to demo interactions.",
            )

        if tool_name in {"browser_open", "youtube_open"}:
            raw_url = str(arguments.get("url", "")).strip()
            if tool_name == "youtube_open":
                raw_url = str(arguments.get("video_url", "") or raw_url).strip()
            if raw_url:
                parsed = urlparse(raw_url if "://" in raw_url else f"https://{raw_url}")
                if parsed.scheme not in {"http", "https"}:
                    return PolicyDecision(
                        tool_name=tool_name,
                        risk_level="medium",
                        allowed=False,
                        reason="Browser navigation is restricted to http and https targets.",
                    )
            if tool_name == "youtube_open" and raw_url:
                host = parsed.netloc.lower()
                if host not in {
                    "youtube.com",
                    "www.youtube.com",
                    "m.youtube.com",
                    "music.youtube.com",
                    "youtu.be",
                }:
                    return PolicyDecision(
                        tool_name=tool_name,
                        risk_level="medium",
                        allowed=False,
                        reason="YouTube navigation is restricted to YouTube URLs.",
                    )
            if tool_name == "browser_open":
                reason = "Opening a browser URL is a low-risk navigation action."
            else:
                reason = "Opening YouTube search/video URLs is a low-risk navigation action."
            return PolicyDecision(
                tool_name=tool_name,
                risk_level="low",
                allowed=True,
                reason=reason,
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
