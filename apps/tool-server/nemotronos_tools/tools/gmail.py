from __future__ import annotations

import base64
from email.message import EmailMessage
from email.utils import parseaddr
from pathlib import Path
import re
from typing import Any


GMAIL_COMPOSE_SCOPE = "https://www.googleapis.com/auth/gmail.compose"
GMAIL_DRAFTS_URL = "https://mail.google.com/mail/u/0/#drafts"
EMAIL_ADDRESS_PATTERN = re.compile(r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$")


def email_create_draft(
    arguments: dict[str, Any],
    client_secrets_path: str,
    token_path: str,
) -> dict[str, Any]:
    message = build_gmail_draft_message(arguments)
    service = build_gmail_service(
        client_secrets_path=client_secrets_path,
        token_path=token_path,
    )
    return create_gmail_draft(
        service=service,
        message=message,
        arguments=arguments,
    )


def build_gmail_draft_message(arguments: dict[str, Any]) -> EmailMessage:
    recipients = _normalize_recipients(arguments.get("to") or arguments.get("recipients"))
    cc_recipients = _normalize_recipients(arguments.get("cc"))
    bcc_recipients = _normalize_recipients(arguments.get("bcc"))
    subject = _clean_header(str(arguments.get("subject") or "Draft from NemotronOS"))
    body = str(arguments.get("body") or "").strip()

    if not recipients:
        raise ValueError("email_create_draft requires at least one recipient in to.")
    if not body:
        raise ValueError("email_create_draft requires body text.")
    if len(body) > 10000:
        raise ValueError("Gmail draft bodies are limited to 10000 characters in this demo.")
    if len(subject) > 300:
        raise ValueError("Gmail draft subjects are limited to 300 characters in this demo.")

    message = EmailMessage()
    message["To"] = ", ".join(recipients)
    if cc_recipients:
        message["Cc"] = ", ".join(cc_recipients)
    if bcc_recipients:
        message["Bcc"] = ", ".join(bcc_recipients)
    message["Subject"] = subject
    message.set_content(body)
    return message


def build_gmail_service(client_secrets_path: str, token_path: str) -> Any:
    if not client_secrets_path:
        raise ValueError("Set GMAIL_CLIENT_SECRETS_PATH in .env before using Gmail drafts.")

    secrets_path = Path(client_secrets_path).expanduser()
    if not secrets_path.exists():
        raise ValueError(f"Gmail OAuth client secrets file does not exist: {secrets_path}")

    token_file = Path(token_path).expanduser()
    token_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as exc:  # pragma: no cover - depends on optional runtime install
        raise ValueError(
            "Gmail draft creation requires google-api-python-client and "
            "google-auth-oauthlib. Install the tool-server dependencies first."
        ) from exc

    credentials = None
    if token_file.exists():
        credentials = Credentials.from_authorized_user_file(
            str(token_file),
            [GMAIL_COMPOSE_SCOPE],
        )

    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())

    if not credentials or not credentials.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(secrets_path),
            [GMAIL_COMPOSE_SCOPE],
        )
        credentials = flow.run_local_server(
            port=0,
            authorization_prompt_message=(
                "NemotronOS needs Gmail draft access. Complete OAuth in the browser: {url}"
            ),
        )

    token_file.write_text(credentials.to_json(), encoding="utf-8")
    return build("gmail", "v1", credentials=credentials)


def create_gmail_draft(
    service: Any,
    message: EmailMessage,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    try:
        created = (
            service.users()
            .drafts()
            .create(userId="me", body={"message": {"raw": raw_message}})
            .execute()
        )
    except Exception as exc:  # noqa: BLE001 - googleapiclient is an optional dependency
        if exc.__class__.__name__ == "HttpError":
            status = getattr(getattr(exc, "resp", None), "status", "unknown")
            reason = str(getattr(exc, "reason", "") or exc).strip()
            raise ValueError(f"Gmail API rejected draft creation: {status} {reason}") from exc
        raise
    draft_id = str(created.get("id") or "")
    message_id = str((created.get("message") or {}).get("id") or "")
    recipients = _normalize_recipients(arguments.get("to") or arguments.get("recipients"))
    cc_recipients = _normalize_recipients(arguments.get("cc"))
    bcc_recipients = _normalize_recipients(arguments.get("bcc"))
    body = str(arguments.get("body") or "")

    return {
        "provider": "gmail",
        "created": True,
        "draft_id": draft_id,
        "message_id": message_id,
        "draft_url": GMAIL_DRAFTS_URL,
        "to": recipients,
        "cc_count": len(cc_recipients),
        "bcc_count": len(bcc_recipients),
        "recipient_count": len(recipients) + len(cc_recipients) + len(bcc_recipients),
        "subject": str(message.get("Subject") or ""),
        "body_characters": len(body),
        "sent": False,
    }


def _normalize_recipients(value: Any) -> list[str]:
    if value is None:
        return []
    raw_items = value if isinstance(value, list) else str(value).split(",")
    recipients: list[str] = []
    for raw_item in raw_items:
        recipient = _clean_header(str(raw_item))
        if not recipient:
            continue
        if not _is_valid_email_recipient(recipient):
            raise ValueError(
                "Gmail draft recipients must be email addresses, such as "
                "alex@example.com. Rejected recipient: "
                f"{recipient}"
            )
        recipients.append(recipient)
    if len(recipients) > 20:
        raise ValueError("Gmail draft recipients are limited to 20 in this demo.")
    return recipients


def _clean_header(value: str) -> str:
    return " ".join(value.replace("\r", " ").replace("\n", " ").split()).strip()


def _is_valid_email_recipient(value: str) -> bool:
    _, address = parseaddr(value)
    return bool(address and EMAIL_ADDRESS_PATTERN.fullmatch(address))
