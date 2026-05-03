from __future__ import annotations

from email.utils import parseaddr
import re
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
EMAIL_ADDRESS_PATTERN = re.compile(r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$")


class PolicyDecision(BaseModel):
    tool_name: str
    risk_level: str
    allowed: bool
    reason: str


class PolicyEngine:
    def classify(self, tool_name: str, arguments: dict[str, Any]) -> PolicyDecision:
        if tool_name in {
            "screen_capture",
            "accessibility_describe_screen",
            "fs_plan_changes",
            "notify_user",
            "browser_session_ensure",
            "browser_navigate",
            "browser_snapshot",
            "canvas_list_assignments_due_soon",
        }:
            return PolicyDecision(
                tool_name=tool_name,
                risk_level="low",
                allowed=True,
                reason=f"{tool_name} is read-only or user-informing.",
            )

        if tool_name == "app_launch":
            app_name = str(arguments.get("app_name", "")).strip().lower()
            if app_name not in {"notepad", "calculator", "calc", "paint", "mspaint", "discord"}:
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

        if tool_name == "discord_send_message":
            text = str(arguments.get("text", ""))
            if len(text) > 1000:
                return PolicyDecision(
                    tool_name=tool_name,
                    risk_level="medium",
                    allowed=False,
                    reason="Discord messages are limited to 1000 characters in the demo path.",
                )
            return PolicyDecision(
                tool_name=tool_name,
                risk_level="medium",
                allowed=True,
                reason=(
                    "Sending a Discord message changes external chat state and is limited "
                    "to the currently active conversation."
                ),
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

        if tool_name == "sticky_note_create":
            text = str(arguments.get("text", ""))
            if len(text) > 4000:
                return PolicyDecision(
                    tool_name=tool_name,
                    risk_level="medium",
                    allowed=False,
                    reason="Sticky notes are limited to 4000 characters in the demo path.",
                )
            return PolicyDecision(
                tool_name=tool_name,
                risk_level="medium",
                allowed=True,
                reason="Creating a sticky note changes local desktop state.",
            )

        if tool_name == "email_create_draft":
            body = str(arguments.get("body", ""))
            subject = str(arguments.get("subject", ""))
            recipients = arguments.get("to") or arguments.get("recipients") or []
            recipient_values = _recipient_values(recipients)
            invalid_recipients = [
                recipient
                for recipient in recipient_values
                if not _is_valid_email_recipient(recipient)
            ]
            if len(recipient_values) < 1:
                return PolicyDecision(
                    tool_name=tool_name,
                    risk_level="medium",
                    allowed=False,
                    reason="Gmail draft creation requires at least one email address.",
                )
            if invalid_recipients:
                return PolicyDecision(
                    tool_name=tool_name,
                    risk_level="medium",
                    allowed=False,
                    reason=(
                        "Gmail draft recipients must be email addresses, such as "
                        f"alex@example.com. Rejected recipient: {invalid_recipients[0]}"
                    ),
                )
            if len(recipient_values) > 20:
                return PolicyDecision(
                    tool_name=tool_name,
                    risk_level="medium",
                    allowed=False,
                    reason="Gmail draft creation is limited to 20 recipients in the demo path.",
                )
            if len(subject) > 300:
                return PolicyDecision(
                    tool_name=tool_name,
                    risk_level="medium",
                    allowed=False,
                    reason="Gmail draft subjects are limited to 300 characters in the demo path.",
                )
            if len(body) > 10000:
                return PolicyDecision(
                    tool_name=tool_name,
                    risk_level="medium",
                    allowed=False,
                    reason="Gmail draft bodies are limited to 10000 characters in the demo path.",
                )
            return PolicyDecision(
                tool_name=tool_name,
                risk_level="medium",
                allowed=True,
                reason="Creating a Gmail draft changes mailbox state but does not send email.",
            )

        if tool_name == "vscode_paste_code":
            code = str(arguments.get("code", ""))
            if code and len(code) > 50000:
                return PolicyDecision(
                    tool_name=tool_name,
                    risk_level="medium",
                    allowed=False,
                    reason="VS Code paste is limited to 50000 characters in the demo path.",
                )
            return PolicyDecision(
                tool_name=tool_name,
                risk_level="medium",
                allowed=True,
                reason=(
                    "Opening VS Code and inserting generated code changes local desktop "
                    "state but does not save files or execute code."
                ),
            )

        if tool_name in {"mouse_click", "youtube_click_video"}:
            return PolicyDecision(
                tool_name=tool_name,
                risk_level="medium",
                allowed=True,
                reason="Mouse clicks change desktop/browser state and are limited to demo interactions.",
            )

        if tool_name == "browser_type":
            text = str(arguments.get("text", ""))
            if len(text) > 500:
                return PolicyDecision(
                    tool_name=tool_name,
                    risk_level="medium",
                    allowed=False,
                    reason="Managed browser typing is limited to 500 characters.",
                )
            return PolicyDecision(
                tool_name=tool_name,
                risk_level="medium",
                allowed=True,
                reason="Managed browser typing changes page state and is limited to demo text.",
            )

        if tool_name in {"browser_click", "browser_select_option", "browser_press"}:
            return PolicyDecision(
                tool_name=tool_name,
                risk_level="medium",
                allowed=True,
                reason="Managed browser mutations change page state and require approval.",
            )

        if tool_name in {"browser_open", "youtube_open", "canvas_open_course"}:
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
            elif tool_name == "canvas_open_course":
                reason = "Opening Canvas course pages is a low-risk navigation action."
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


def _recipient_values(recipients: Any) -> list[str]:
    if isinstance(recipients, str):
        raw_values = recipients.split(",")
    elif isinstance(recipients, list):
        raw_values = recipients
    else:
        raw_values = []
    return [str(value).strip() for value in raw_values if str(value).strip()]


def _is_valid_email_recipient(value: str) -> bool:
    _, address = parseaddr(value)
    return bool(address and EMAIL_ADDRESS_PATTERN.fullmatch(address))
