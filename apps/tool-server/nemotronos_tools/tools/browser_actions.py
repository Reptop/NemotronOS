from __future__ import annotations

from typing import Any

from .browser_automation import (
    DEFAULT_SNAPSHOT_TARGETS,
    DEFAULT_SNAPSHOT_TEXT_CHARS,
    BrowserAutomationService,
)


def browser_session_ensure(
    arguments: dict[str, Any],
    browser_service: BrowserAutomationService,
) -> dict[str, Any]:
    start_url = str(arguments.get("start_url") or "").strip() or None
    return browser_service.ensure_session(start_url=start_url)


def browser_navigate(
    arguments: dict[str, Any],
    browser_service: BrowserAutomationService,
) -> dict[str, Any]:
    url = str(arguments.get("url") or "").strip()
    if not url:
        raise ValueError("browser_navigate requires url.")
    return browser_service.navigate(url)


def browser_snapshot(
    arguments: dict[str, Any],
    browser_service: BrowserAutomationService,
) -> dict[str, Any]:
    max_text_chars = int(arguments.get("max_text_chars", DEFAULT_SNAPSHOT_TEXT_CHARS))
    max_targets = int(arguments.get("max_targets", DEFAULT_SNAPSHOT_TARGETS))
    return browser_service.snapshot(max_text_chars=max_text_chars, max_targets=max_targets)


def browser_click(
    arguments: dict[str, Any],
    browser_service: BrowserAutomationService,
) -> dict[str, Any]:
    target_id = str(arguments.get("target_id") or "").strip()
    if not target_id:
        raise ValueError("browser_click requires target_id.")
    return browser_service.click(target_id)


def browser_type(
    arguments: dict[str, Any],
    browser_service: BrowserAutomationService,
) -> dict[str, Any]:
    target_id = str(arguments.get("target_id") or "").strip()
    text = str(arguments.get("text") or "")
    clear_first = bool(arguments.get("clear_first", False))
    if not target_id:
        raise ValueError("browser_type requires target_id.")
    if not text:
        raise ValueError("browser_type requires text.")
    return browser_service.type_text(target_id, text, clear_first=clear_first)


def browser_select_option(
    arguments: dict[str, Any],
    browser_service: BrowserAutomationService,
) -> dict[str, Any]:
    target_id = str(arguments.get("target_id") or "").strip()
    value_or_label = str(arguments.get("value_or_label") or "").strip()
    if not target_id:
        raise ValueError("browser_select_option requires target_id.")
    if not value_or_label:
        raise ValueError("browser_select_option requires value_or_label.")
    return browser_service.select_option(target_id, value_or_label)


def browser_press(
    arguments: dict[str, Any],
    browser_service: BrowserAutomationService,
) -> dict[str, Any]:
    key = str(arguments.get("key") or "").strip()
    if not key:
        raise ValueError("browser_press requires key.")
    return browser_service.press(key)


def gmail_open(
    arguments: dict[str, Any],
    browser_service: BrowserAutomationService,
) -> dict[str, Any]:
    view = str(arguments.get("view") or "inbox").strip() or "inbox"
    return browser_service.gmail_open(view=view)


def gmail_search(
    arguments: dict[str, Any],
    browser_service: BrowserAutomationService,
) -> dict[str, Any]:
    query = str(arguments.get("query") or "").strip()
    if not query:
        raise ValueError("gmail_search requires query.")
    return browser_service.gmail_search(query=query)


def gmail_compose_draft(
    arguments: dict[str, Any],
    browser_service: BrowserAutomationService,
) -> dict[str, Any]:
    to = str(arguments.get("to") or "").strip()
    subject = str(arguments.get("subject") or "").strip()
    body = str(arguments.get("body") or "").strip()
    if not to:
        raise ValueError("gmail_compose_draft requires to.")
    if not body:
        raise ValueError("gmail_compose_draft requires body.")
    return browser_service.gmail_compose_draft(to=to, subject=subject, body=body)

def gmail_send_current_draft(
    arguments: dict[str, Any],
    browser_service: BrowserAutomationService,
) -> dict[str, Any]:
    del arguments
    return browser_service.gmail_send_current_draft()