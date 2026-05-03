from __future__ import annotations

import webbrowser
from abc import ABC, abstractmethod
from dataclasses import dataclass
from threading import Lock
from typing import Any
from urllib.parse import quote, urlparse

from ..config import ToolServerSettings
from .desktop_actions import normalize_browser_target

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import Page, Playwright, sync_playwright
except ImportError:  # pragma: no cover - exercised in environments without Playwright
    Page = Any  # type: ignore[assignment]
    Playwright = Any  # type: ignore[assignment]
    PlaywrightError = RuntimeError  # type: ignore[assignment]
    sync_playwright = None  # type: ignore[assignment]


DEFAULT_SNAPSHOT_TEXT_CHARS = 1200
DEFAULT_SNAPSHOT_TARGETS = 25
DEFAULT_START_URL = "https://www.google.com"

BROWSER_AGENT_TOOLS = {
    "browser_session_ensure",
    "browser_navigate",
    "browser_snapshot",
    "browser_click",
    "browser_type",
    "browser_select_option",
    "browser_press",
}

GMAIL_BASE_URL = "https://mail.google.com/mail/u/0"
GMAIL_VIEWS = {
    "inbox": f"{GMAIL_BASE_URL}/#inbox",
    "starred": f"{GMAIL_BASE_URL}/#starred",
    "sent": f"{GMAIL_BASE_URL}/#sent",
    "drafts": f"{GMAIL_BASE_URL}/#drafts",
    "all": f"{GMAIL_BASE_URL}/#all",
}


@dataclass(frozen=True, slots=True)
class BrowserTarget:
    target_id: str
    tag: str
    role: str
    name: str
    text: str
    input_type: str
    href: str
    value_preview: str
    actionable: list[str]
    disabled: bool
    checked: bool | None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "target_id": self.target_id,
            "tag": self.tag,
            "role": self.role,
            "name": self.name,
            "text": self.text,
            "type": self.input_type,
            "actionable": self.actionable,
            "disabled": self.disabled,
        }
        if self.href:
            payload["href"] = self.href
        if self.value_preview:
            payload["value_preview"] = self.value_preview
        if self.checked is not None:
            payload["checked"] = self.checked
        return payload


class BrowserAutomationService(ABC):
    @abstractmethod
    def ensure_session(self, start_url: str | None = None) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def navigate(self, url: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def snapshot(
        self,
        max_text_chars: int = DEFAULT_SNAPSHOT_TEXT_CHARS,
        max_targets: int = DEFAULT_SNAPSHOT_TARGETS,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def click(self, target_id: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def type_text(self, target_id: str, text: str, clear_first: bool = False) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def select_option(self, target_id: str, value_or_label: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def press(self, key: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def gmail_open(self, view: str = "inbox") -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def gmail_search(self, query: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def gmail_compose_draft(
        self,
        to: str,
        subject: str,
        body: str,
    ) -> dict[str, Any]:
        raise NotImplementedError
    
    @abstractmethod
    def gmail_send_current_draft(self) -> dict[str, Any]:
        raise NotImplementedError

class SimpleBrowserOpenService(BrowserAutomationService):
    """
    Uses the OS default browser instead of Playwright. This avoids the
    Playwright Sync API vs asyncio issue in the FastAPI tool server.
    """

    def ensure_session(self, start_url: str | None = None) -> dict[str, Any]:
        url = normalize_browser_target(start_url or DEFAULT_START_URL)
        webbrowser.open(url)
        return {
            "mode": "simple_browser_open",
            "browser": "default",
            "automation_enabled": True,
            "url": url,
            "title": "Browser opened",
            "load_state": "opened",
            "visible_text_excerpt": f"Opened {url} in the default browser.",
            "targets": [],
        }

    def navigate(self, url: str) -> dict[str, Any]:
        normalized_url = normalize_browser_target(url)
        webbrowser.open(normalized_url)
        return {
            "mode": "simple_browser_open",
            "browser": "default",
            "automation_enabled": True,
            "url": normalized_url,
            "title": "Browser opened",
            "load_state": "opened",
            "visible_text_excerpt": f"Opened {normalized_url} in the default browser.",
            "targets": [],
        }

    def snapshot(
        self,
        max_text_chars: int = DEFAULT_SNAPSHOT_TEXT_CHARS,
        max_targets: int = DEFAULT_SNAPSHOT_TARGETS,
    ) -> dict[str, Any]:
        del max_text_chars, max_targets
        return {
            "mode": "simple_browser_open",
            "browser": "default",
            "automation_enabled": True,
            "url": "",
            "title": "Snapshot unavailable",
            "load_state": "not_supported",
            "visible_text_excerpt": "Simple browser mode can open URLs but does not inspect page contents.",
            "targets": [],
        }

    def click(self, target_id: str) -> dict[str, Any]:
        del target_id
        raise ValueError("Simple browser mode does not support browser_click.")

    def type_text(self, target_id: str, text: str, clear_first: bool = False) -> dict[str, Any]:
        del target_id, text, clear_first
        raise ValueError("Simple browser mode does not support browser_type.")

    def select_option(self, target_id: str, value_or_label: str) -> dict[str, Any]:
        del target_id, value_or_label
        raise ValueError("Simple browser mode does not support browser_select_option.")

    def press(self, key: str) -> dict[str, Any]:
        del key
        raise ValueError("Simple browser mode does not support browser_press.")

    def gmail_open(self, view: str = "inbox") -> dict[str, Any]:
        normalized_view = _normalize_gmail_view(view)
        url = GMAIL_VIEWS[normalized_view]
        webbrowser.open(url)
        return {
            "mode": "simple_browser_open",
            "browser": "default",
            "automation_enabled": True,
            "url": url,
            "title": f"Gmail {normalized_view.title()}",
            "load_state": "opened",
            "visible_text_excerpt": f"Opened Gmail {normalized_view} in the default browser.",
            "targets": [],
            "email": {
                "provider": "gmail",
                "action": "open",
                "view": normalized_view,
                "authenticated": None,
            },
        }

    def gmail_search(self, query: str) -> dict[str, Any]:
        cleaned_query = query.strip()
        if not cleaned_query:
            raise ValueError("gmail_search requires query.")
        url = f"{GMAIL_BASE_URL}/#search/{quote(cleaned_query, safe='')}"
        webbrowser.open(url)
        return {
            "mode": "simple_browser_open",
            "browser": "default",
            "automation_enabled": True,
            "url": url,
            "title": "Gmail Search",
            "load_state": "opened",
            "visible_text_excerpt": f"Opened Gmail search for {cleaned_query}.",
            "targets": [],
            "email": {
                "provider": "gmail",
                "action": "search",
                "query": cleaned_query,
                "authenticated": None,
            },
        }

    def gmail_compose_draft(
        self,
        to: str,
        subject: str,
        body: str,
    ) -> dict[str, Any]:
        cleaned_to = to.strip()
        cleaned_subject = subject.strip()
        cleaned_body = body.strip()

        if not cleaned_to:
            raise ValueError("gmail_compose_draft requires to.")
        if not cleaned_body:
            raise ValueError("gmail_compose_draft requires body.")

        # This opens Gmail compose. It may not fully prefill all fields reliably,
        # but it is enough as a safe fallback for the hackathon demo.
        url = (
            f"{GMAIL_BASE_URL}/?view=cm&fs=1"
            f"&to={quote(cleaned_to)}"
            f"&su={quote(cleaned_subject)}"
            f"&body={quote(cleaned_body)}"
        )
        webbrowser.open(url)

        return {
            "mode": "simple_browser_open",
            "browser": "default",
            "automation_enabled": True,
            "url": url,
            "title": "Gmail Compose",
            "load_state": "opened",
            "visible_text_excerpt": f"Opened Gmail compose draft to {cleaned_to}.",
            "targets": [],
            "email": {
                "provider": "gmail",
                "action": "compose_draft",
                "to": cleaned_to,
                "subject": cleaned_subject,
                "body_preview": cleaned_body[:160],
                "authenticated": None,
                "sent": False,
            },
        }
        
    def gmail_send_current_draft(self) -> dict[str, Any]:
        import pyautogui
        import time

        # Give Gmail/browser focus a moment.
        time.sleep(0.5)
        
        # Gmail commonly supports Ctrl+Enter to send from compose.
        pyautogui.hotkey("ctrl", "enter")

        return {
            "mode": "simple_browser_open",
            "browser": "default",
            "automation_enabled": True,
            "title": "Gmail Send",
            "load_state": "sent_shortcut_attempted",
            "visible_text_excerpt": "Attempted to send the current Gmail draft using Ctrl+Enter.",
            "targets": [],
            "email": {
                "provider": "gmail",
                "action": "send_current_draft",
                "sent": "attempted",
                "confirmation_required": True,
            },
        }
                
        
class DisabledBrowserAutomationService(BrowserAutomationService):
    def ensure_session(self, start_url: str | None = None) -> dict[str, Any]:
        del start_url
        raise ValueError(
            "Browser automation is disabled. Set BROWSER_AUTOMATION_ENABLED=true on the Windows tool server."
        )

    def navigate(self, url: str) -> dict[str, Any]:
        del url
        raise ValueError(
            "Browser automation is disabled. Set BROWSER_AUTOMATION_ENABLED=true on the Windows tool server."
        )

    def snapshot(
        self,
        max_text_chars: int = DEFAULT_SNAPSHOT_TEXT_CHARS,
        max_targets: int = DEFAULT_SNAPSHOT_TARGETS,
    ) -> dict[str, Any]:
        del max_text_chars, max_targets
        raise ValueError(
            "Browser automation is disabled. Set BROWSER_AUTOMATION_ENABLED=true on the Windows tool server."
        )

    def click(self, target_id: str) -> dict[str, Any]:
        del target_id
        raise ValueError(
            "Browser automation is disabled. Set BROWSER_AUTOMATION_ENABLED=true on the Windows tool server."
        )

    def type_text(self, target_id: str, text: str, clear_first: bool = False) -> dict[str, Any]:
        del target_id, text, clear_first
        raise ValueError(
            "Browser automation is disabled. Set BROWSER_AUTOMATION_ENABLED=true on the Windows tool server."
        )

    def select_option(self, target_id: str, value_or_label: str) -> dict[str, Any]:
        del target_id, value_or_label
        raise ValueError(
            "Browser automation is disabled. Set BROWSER_AUTOMATION_ENABLED=true on the Windows tool server."
        )

    def press(self, key: str) -> dict[str, Any]:
        del key
        raise ValueError(
            "Browser automation is disabled. Set BROWSER_AUTOMATION_ENABLED=true on the Windows tool server."
        )

    def gmail_open(self, view: str = "inbox") -> dict[str, Any]:
        del view
        raise ValueError(
            "Browser automation is disabled. Set BROWSER_AUTOMATION_ENABLED=true on the Windows tool server."
        )

    def gmail_search(self, query: str) -> dict[str, Any]:
        del query
        raise ValueError(
            "Browser automation is disabled. Set BROWSER_AUTOMATION_ENABLED=true on the Windows tool server."
        )

    def gmail_compose_draft(
        self,
        to: str,
        subject: str,
        body: str,
    ) -> dict[str, Any]:
        del to, subject, body
        raise ValueError(
            "Browser automation is disabled. Set BROWSER_AUTOMATION_ENABLED=true on the Windows tool server."
        )
    
    def gmail_send_current_draft(self) -> dict[str, Any]:
        raise ValueError(
            "Browser automation is disabled. Set BROWSER_AUTOMATION_ENABLED=true on the Windows tool server."
    )


class MockBrowserAutomationService(BrowserAutomationService):
    def __init__(self) -> None:
        self._state = self._state_for_url(DEFAULT_START_URL)

    def ensure_session(self, start_url: str | None = None) -> dict[str, Any]:
        if start_url:
            self._state = self._state_for_url(normalize_browser_target(start_url))
        return self._snapshot()

    def navigate(self, url: str) -> dict[str, Any]:
        self._state = self._state_for_url(normalize_browser_target(url))
        return self._snapshot()

    def snapshot(
        self,
        max_text_chars: int = DEFAULT_SNAPSHOT_TEXT_CHARS,
        max_targets: int = DEFAULT_SNAPSHOT_TARGETS,
    ) -> dict[str, Any]:
        return self._snapshot(max_text_chars=max_text_chars, max_targets=max_targets)

    def click(self, target_id: str) -> dict[str, Any]:
        target = self._require_target(target_id, "click")
        if target_id == "t2" and "google" in self._state["url"]:
            query = self._state.get("typed_text") or "NemotronOS"
            self._state = self._state_for_url(
                f"https://www.google.com/search?q={query.replace(' ', '+')}"
            )
        self._state["last_action"] = {"tool": "browser_click", "target_id": target_id}
        self._state["last_target"] = target["name"] or target["text"]
        return self._snapshot()

    def type_text(self, target_id: str, text: str, clear_first: bool = False) -> dict[str, Any]:
        self._require_target(target_id, "type")
        del clear_first
        self._state["typed_text"] = text
        self._state["last_action"] = {
            "tool": "browser_type",
            "target_id": target_id,
            "text": text,
        }
        return self._snapshot()

    def select_option(self, target_id: str, value_or_label: str) -> dict[str, Any]:
        self._require_target(target_id, "select")
        self._state["selected_value"] = value_or_label
        self._state["last_action"] = {
            "tool": "browser_select_option",
            "target_id": target_id,
            "value_or_label": value_or_label,
        }
        return self._snapshot()

    def press(self, key: str) -> dict[str, Any]:
        if key.lower() == "enter" and "google" in self._state["url"] and self._state.get("typed_text"):
            query = self._state["typed_text"]
            self._state = self._state_for_url(
                f"https://www.google.com/search?q={query.replace(' ', '+')}"
            )
        self._state["last_action"] = {"tool": "browser_press", "key": key}
        return self._snapshot()

    def gmail_open(self, view: str = "inbox") -> dict[str, Any]:
        normalized_view = _normalize_gmail_view(view)
        self._state = self._gmail_state(
            GMAIL_VIEWS[normalized_view],
            f"Gmail {normalized_view.title()}",
            f"Gmail. {normalized_view.title()}. Primary inbox. Compose. Search mail.",
        )
        snapshot = self._snapshot()
        snapshot["email"] = {
            "provider": "gmail",
            "action": "open",
            "view": normalized_view,
            "authenticated": True,
        }
        return snapshot

    def gmail_search(self, query: str) -> dict[str, Any]:
        if not query.strip():
            raise ValueError("gmail_search requires query.")
        encoded_query = quote(query.strip(), safe="")
        self._state = self._gmail_state(
            f"{GMAIL_BASE_URL}/#search/{encoded_query}",
            "Gmail Search",
            f"Gmail search results for {query.strip()}. Compose. Search mail.",
        )
        snapshot = self._snapshot(max_text_chars=2000, max_targets=40)
        snapshot["email"] = {
            "provider": "gmail",
            "action": "search",
            "query": query.strip(),
            "authenticated": True,
        }
        return snapshot

    def gmail_compose_draft(
        self,
        to: str,
        subject: str,
        body: str,
    ) -> dict[str, Any]:
        if not to.strip():
            raise ValueError("gmail_compose_draft requires to.")
        if not body.strip():
            raise ValueError("gmail_compose_draft requires body.")
        self._state = self._gmail_state(
            f"{GMAIL_BASE_URL}/#drafts",
            "Gmail Draft",
            f"New Message draft. To {to.strip()}. Subject {subject.strip()}. {body.strip()}",
        )
        self._state["last_action"] = {
            "tool": "gmail_compose_draft",
            "to": to.strip(),
            "subject": subject.strip(),
            "body_preview": body.strip()[:160],
        }
        snapshot = self._snapshot(max_text_chars=2000, max_targets=40)
        snapshot["email"] = {
            "provider": "gmail",
            "action": "compose_draft",
            "to": to.strip(),
            "subject": subject.strip(),
            "body_preview": body.strip()[:160],
            "sent": False,
        }
        return snapshot

    def _snapshot(
        self,
        max_text_chars: int = DEFAULT_SNAPSHOT_TEXT_CHARS,
        max_targets: int = DEFAULT_SNAPSHOT_TARGETS,
    ) -> dict[str, Any]:
        targets = [target.copy() for target in self._state["targets"][: max(1, max_targets)]]
        return {
            "mode": "mock_browser_automation",
            "browser": "chrome",
            "automation_enabled": True,
            "url": self._state["url"],
            "title": self._state["title"],
            "load_state": "complete",
            "visible_text_excerpt": self._state["visible_text"][: max(1, max_text_chars)],
            "targets": targets,
            **({"last_action": self._state["last_action"]} if self._state.get("last_action") else {}),
        }

    def _require_target(self, target_id: str, required_action: str) -> dict[str, Any]:
        for target in self._state["targets"]:
            if target["target_id"] != target_id:
                continue
            if required_action not in target["actionable"]:
                raise ValueError(f"Target {target_id} does not support {required_action}.")
            return target
        raise ValueError(f"Unknown browser target_id: {target_id}. Take a fresh browser_snapshot.")

    def _state_for_url(self, url: str) -> dict[str, Any]:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if "google.com" in host:
            return {
                "url": url,
                "title": "Google",
                "visible_text": "Google Search. Search the web.",
                "targets": [
                    {
                        "target_id": "t1",
                        "tag": "input",
                        "role": "searchbox",
                        "name": "Search",
                        "text": "",
                        "type": "search",
                        "actionable": ["type"],
                        "disabled": False,
                    },
                    {
                        "target_id": "t2",
                        "tag": "button",
                        "role": "button",
                        "name": "Google Search",
                        "text": "Google Search",
                        "type": "",
                        "actionable": ["click"],
                        "disabled": False,
                    },
                ],
            }
        if "github.com" in host:
            return {
                "url": url,
                "title": "GitHub",
                "visible_text": "GitHub. Search or jump to.",
                "targets": [
                    {
                        "target_id": "t1",
                        "tag": "input",
                        "role": "searchbox",
                        "name": "Search GitHub",
                        "text": "",
                        "type": "search",
                        "actionable": ["type"],
                        "disabled": False,
                    }
                ],
            }
        if "mail.google.com" in host:
            return self._gmail_state(
                url,
                "Gmail",
                "Gmail. Primary inbox. Compose. Search mail.",
            )
        return {
            "url": url,
            "title": parsed.netloc or "Managed Browser",
            "visible_text": f"Managed browser page for {url}",
            "targets": [
                {
                    "target_id": "t1",
                    "tag": "a",
                    "role": "link",
                    "name": "Primary Link",
                    "text": "Primary Link",
                    "type": "",
                    "href": url,
                    "actionable": ["click"],
                    "disabled": False,
                }
            ],
        }

    def _gmail_state(self, url: str, title: str, visible_text: str) -> dict[str, Any]:
        return {
            "url": url,
            "title": title,
            "visible_text": visible_text,
            "targets": [
                {
                    "target_id": "t1",
                    "tag": "button",
                    "role": "button",
                    "name": "Compose",
                    "text": "Compose",
                    "type": "",
                    "actionable": ["click"],
                    "disabled": False,
                },
                {
                    "target_id": "t2",
                    "tag": "input",
                    "role": "searchbox",
                    "name": "Search mail",
                    "text": "",
                    "type": "search",
                    "actionable": ["type"],
                    "disabled": False,
                },
            ],
        }
    def gmail_send_current_draft(self) -> dict[str, Any]:
        snapshot = self._snapshot(max_text_chars=2000, max_targets=40)
        snapshot["email"] = {
            "provider": "gmail",
            "action": "send_current_draft",
            "sent": True,
            "mock": True,
        }
        return snapshot


class PlaywrightBrowserAutomationService(BrowserAutomationService):
    def __init__(self, settings: ToolServerSettings) -> None:
        self.settings = settings
        self._lock = Lock()
        self._playwright_manager: Any | None = None
        self._playwright: Playwright | None = None
        self._context: Any | None = None
        self._page: Page | None = None

    def ensure_session(self, start_url: str | None = None) -> dict[str, Any]:
        with self._lock:
            page = self._ensure_page()
            if start_url:
                page.goto(normalize_browser_target(start_url), wait_until="domcontentloaded")
                self._wait_for_page_settle(page)
            return self._snapshot_page(page)

    def navigate(self, url: str) -> dict[str, Any]:
        normalized_url = normalize_browser_target(url)
        with self._lock:
            page = self._ensure_page()
            page.goto(normalized_url, wait_until="domcontentloaded")
            self._wait_for_page_settle(page)
            return self._snapshot_page(page)

    def snapshot(
        self,
        max_text_chars: int = DEFAULT_SNAPSHOT_TEXT_CHARS,
        max_targets: int = DEFAULT_SNAPSHOT_TARGETS,
    ) -> dict[str, Any]:
        with self._lock:
            page = self._ensure_page()
            return self._snapshot_page(
                page,
                max_text_chars=max_text_chars,
                max_targets=max_targets,
            )

    def click(self, target_id: str) -> dict[str, Any]:
        with self._lock:
            page = self._ensure_page()
            locator = self._require_target_locator(page, target_id)
            locator.click(timeout=self.settings.browser_default_timeout_ms)
            self._wait_for_page_settle(page)
            return self._snapshot_page(page)

    def type_text(self, target_id: str, text: str, clear_first: bool = False) -> dict[str, Any]:
        with self._lock:
            page = self._ensure_page()
            locator = self._require_target_locator(page, target_id)
            locator.click(timeout=self.settings.browser_default_timeout_ms)
            if clear_first:
                page.keyboard.press("Control+A")
                page.keyboard.press("Backspace")
            page.keyboard.type(text, delay=20)
            return self._snapshot_page(page)

    def select_option(self, target_id: str, value_or_label: str) -> dict[str, Any]:
        with self._lock:
            page = self._ensure_page()
            locator = self._require_target_locator(page, target_id)
            try:
                locator.select_option(label=value_or_label, timeout=self.settings.browser_default_timeout_ms)
            except Exception:
                locator.select_option(value=value_or_label, timeout=self.settings.browser_default_timeout_ms)
            self._wait_for_page_settle(page)
            return self._snapshot_page(page)

    def press(self, key: str) -> dict[str, Any]:
        with self._lock:
            page = self._ensure_page()
            page.keyboard.press(key)
            self._wait_for_page_settle(page)
            return self._snapshot_page(page)

    def gmail_open(self, view: str = "inbox") -> dict[str, Any]:
        normalized_view = _normalize_gmail_view(view)
        with self._lock:
            page = self._ensure_page()
            page.goto(GMAIL_VIEWS[normalized_view], wait_until="domcontentloaded")
            self._wait_for_page_settle(page)
            snapshot = self._snapshot_page(page, max_text_chars=2000, max_targets=40)
            snapshot["email"] = {
                "provider": "gmail",
                "action": "open",
                "view": normalized_view,
                "authenticated": self._is_gmail_authenticated(page),
            }
            return snapshot

    def gmail_search(self, query: str) -> dict[str, Any]:
        cleaned_query = query.strip()
        if not cleaned_query:
            raise ValueError("gmail_search requires query.")
        with self._lock:
            page = self._ensure_page()
            page.goto(
                f"{GMAIL_BASE_URL}/#search/{quote(cleaned_query, safe='')}",
                wait_until="domcontentloaded",
            )
            self._wait_for_page_settle(page)
            snapshot = self._snapshot_page(page, max_text_chars=2400, max_targets=50)
            snapshot["email"] = {
                "provider": "gmail",
                "action": "search",
                "query": cleaned_query,
                "authenticated": self._is_gmail_authenticated(page),
            }
            return snapshot

    def gmail_compose_draft(
        self,
        to: str,
        subject: str,
        body: str,
    ) -> dict[str, Any]:
        cleaned_to = to.strip()
        cleaned_subject = subject.strip()
        cleaned_body = body.strip()
        if not cleaned_to:
            raise ValueError("gmail_compose_draft requires to.")
        if not cleaned_body:
            raise ValueError("gmail_compose_draft requires body.")

        with self._lock:
            page = self._ensure_page()
            if "mail.google.com" not in urlparse(page.url).netloc.lower():
                page.goto(GMAIL_VIEWS["inbox"], wait_until="domcontentloaded")
                self._wait_for_page_settle(page)

            if not self._is_gmail_authenticated(page):
                snapshot = self._snapshot_page(page, max_text_chars=2000, max_targets=40)
                snapshot["email"] = {
                    "provider": "gmail",
                    "action": "compose_draft",
                    "authenticated": False,
                    "sent": False,
                    "blocked_reason": "Gmail is not signed in on the managed browser profile.",
                }
                return snapshot

            compose_button = self._first_visible_locator(
                page,
                [
                    "div[role='button'][gh='cm']",
                    "div[role='button'][aria-label*='Compose']",
                    "div[role='button']:has-text('Compose')",
                ],
            )
            compose_button.click(timeout=self.settings.browser_default_timeout_ms)

            to_field = self._first_visible_locator(
                page,
                [
                    "textarea[name='to']",
                    "input[aria-label*='To']",
                    "textarea[aria-label*='To']",
                ],
            )
            to_field.fill(cleaned_to, timeout=self.settings.browser_default_timeout_ms)
            page.keyboard.press("Enter")

            if cleaned_subject:
                subject_field = self._first_visible_locator(
                    page,
                    [
                        "input[name='subjectbox']",
                        "input[aria-label='Subject']",
                        "input[placeholder='Subject']",
                    ],
                )
                subject_field.fill(cleaned_subject, timeout=self.settings.browser_default_timeout_ms)

            body_field = self._first_visible_locator(
                page,
                [
                    "div[aria-label='Message Body'][role='textbox']",
                    "div[role='textbox'][aria-label*='Message Body']",
                    "div[contenteditable='true'][role='textbox']",
                ],
            )
            try:
                body_field.fill(cleaned_body, timeout=self.settings.browser_default_timeout_ms)
            except PlaywrightError:
                body_field.click(timeout=self.settings.browser_default_timeout_ms)
                page.keyboard.type(cleaned_body, delay=10)

            snapshot = self._snapshot_page(page, max_text_chars=2400, max_targets=50)
            snapshot["email"] = {
                "provider": "gmail",
                "action": "compose_draft",
                "to": cleaned_to,
                "subject": cleaned_subject,
                "body_preview": cleaned_body[:160],
                "authenticated": True,
                "sent": False,
            }
            return snapshot

    def _ensure_page(self) -> Page:
        if self.settings.tool_mode != "windows":
            raise ValueError("Browser automation is only supported in TOOL_MODE=windows.")
        if sync_playwright is None:
            raise OSError(
                "Browser automation requires Playwright. Install the tool-server dependencies first."
            )
        if not self.settings.browser_user_data_dir:
            raise ValueError(
                "BROWSER_USER_DATA_DIR is required for browser automation with a persistent Chrome profile."
            )
        if self._page is not None and not self._page.is_closed():
            return self._page

        if self._context is None:
            self._playwright_manager = sync_playwright()
            self._playwright = self._playwright_manager.start()
            launch_kwargs: dict[str, Any] = {
                "user_data_dir": self.settings.browser_user_data_dir,
                "headless": self.settings.browser_headless,
                "args": [f"--profile-directory={self.settings.browser_profile_dir}"],
            }
            if self.settings.browser_chrome_executable:
                launch_kwargs["executable_path"] = self.settings.browser_chrome_executable
            else:
                launch_kwargs["channel"] = "chrome"
            try:
                self._context = self._playwright.chromium.launch_persistent_context(**launch_kwargs)
            except Exception as exc:  # noqa: BLE001
                raise OSError(
                    "Failed to launch the managed Chrome profile. Make sure the configured profile exists "
                    "and is not locked by another Chrome instance."
                ) from exc
            self._context.set_default_timeout(self.settings.browser_default_timeout_ms)

        pages = [page for page in self._context.pages if not page.is_closed()]
        self._page = pages[0] if pages else self._context.new_page()
        if self._page.url in {"", "about:blank"}:
            self._page.goto(DEFAULT_START_URL, wait_until="domcontentloaded")
        self._wait_for_page_settle(self._page)
        return self._page

    def _wait_for_page_settle(self, page: Page) -> None:
        try:
            page.wait_for_load_state("domcontentloaded", timeout=self.settings.browser_default_timeout_ms)
        except Exception:
            return

    def _first_visible_locator(self, page: Page, selectors: list[str]) -> Any:
        last_error: Exception | None = None
        per_selector_timeout = max(1000, self.settings.browser_default_timeout_ms // max(1, len(selectors)))
        for selector in selectors:
            locator = page.locator(selector).last
            try:
                locator.wait_for(state="visible", timeout=per_selector_timeout)
                return locator
            except Exception as exc:  # noqa: BLE001
                last_error = exc
        raise ValueError(f"Could not find a visible Gmail element for selectors: {selectors}") from last_error

    def _is_gmail_authenticated(self, page: Page) -> bool:
        parsed = urlparse(page.url)
        if parsed.netloc.lower().endswith("accounts.google.com"):
            return False
        if "mail.google.com" not in parsed.netloc.lower():
            return False
        try:
            return page.locator("div[role='main'], div[gh='tl'], textarea[name='to']").count() > 0
        except Exception:
            return True

    def _snapshot_page(
        self,
        page: Page,
        max_text_chars: int = DEFAULT_SNAPSHOT_TEXT_CHARS,
        max_targets: int = DEFAULT_SNAPSHOT_TARGETS,
    ) -> dict[str, Any]:
        snapshot = page.evaluate(
            """
            ({ maxTextChars, maxTargets }) => {
              const isVisible = (element) => {
                if (!element || !(element instanceof HTMLElement)) return false;
                const style = window.getComputedStyle(element);
                const rect = element.getBoundingClientRect();
                return style.visibility !== "hidden" && style.display !== "none" &&
                  rect.width > 0 && rect.height > 0 && element.getClientRects().length > 0;
              };

              const textOf = (element) => (element.innerText || element.textContent || "").replace(/\\s+/g, " ").trim();
              const bodyText = textOf(document.body || document.documentElement).slice(0, maxTextChars);
              document.querySelectorAll("[data-nemotron-target-id]").forEach((element) => {
                element.removeAttribute("data-nemotron-target-id");
              });

              const candidates = Array.from(
                document.querySelectorAll("a, button, input, textarea, select, [role], [contenteditable='true']")
              );

              const targets = [];
              let counter = 1;
              for (const element of candidates) {
                if (!isVisible(element)) continue;

                const tag = element.tagName.toLowerCase();
                const role = (element.getAttribute("role") || "").toLowerCase();
                const type = (element.getAttribute("type") || "").toLowerCase();
                const actionable = [];
                if (tag === "input" || tag === "textarea" || element.isContentEditable) actionable.push("type");
                if (tag === "select") actionable.push("select");
                if (tag === "a" || tag === "button" || role === "button" || role === "link" || tag === "summary") actionable.push("click");
                if (actionable.length === 0) continue;

                const targetId = `t${counter++}`;
                element.setAttribute("data-nemotron-target-id", targetId);
                const name = (
                  element.getAttribute("aria-label") ||
                  element.getAttribute("title") ||
                  element.getAttribute("placeholder") ||
                  textOf(element)
                ).slice(0, 200);
                const text = textOf(element).slice(0, 200);
                const valuePreview =
                  type === "password"
                    ? ""
                    : String((element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement) ? element.value || "" : "")
                        .replace(/\\s+/g, " ")
                        .slice(0, 120);
                targets.push({
                  target_id: targetId,
                  tag,
                  role,
                  name,
                  text,
                  type,
                  href: tag === "a" ? (element.getAttribute("href") || "") : "",
                  value_preview: valuePreview,
                  actionable,
                  disabled: Boolean(element.disabled || element.getAttribute("aria-disabled") === "true"),
                  checked:
                    tag === "input" && ["checkbox", "radio"].includes(type)
                      ? Boolean(element.checked)
                      : null,
                });
                if (targets.length >= maxTargets) break;
              }

              return {
                url: window.location.href,
                title: document.title,
                load_state: document.readyState,
                visible_text_excerpt: bodyText,
                targets,
              };
            }
            """,
            {"maxTextChars": max(1, max_text_chars), "maxTargets": max(1, max_targets)},
        )
        return {
            "mode": "browser_automation",
            "browser": "chrome",
            "automation_enabled": True,
            "url": str(snapshot.get("url") or page.url),
            "title": str(snapshot.get("title") or ""),
            "load_state": str(snapshot.get("load_state") or "unknown"),
            "visible_text_excerpt": str(snapshot.get("visible_text_excerpt") or ""),
            "targets": [self._normalize_target(target).to_dict() for target in snapshot.get("targets", [])],
        }

    def _require_target_locator(self, page: Page, target_id: str) -> Any:
        if not target_id.strip():
            raise ValueError("browser action requires target_id.")
        locator = page.locator(f'[data-nemotron-target-id="{target_id}"]').first
        if locator.count() == 0:
            raise ValueError(
                f"Unknown browser target_id: {target_id}. Take a fresh browser_snapshot before acting."
            )
        return locator

    def _normalize_target(self, raw_target: dict[str, Any]) -> BrowserTarget:
        return BrowserTarget(
            target_id=str(raw_target.get("target_id") or ""),
            tag=str(raw_target.get("tag") or ""),
            role=str(raw_target.get("role") or ""),
            name=str(raw_target.get("name") or ""),
            text=str(raw_target.get("text") or ""),
            input_type=str(raw_target.get("type") or ""),
            href=str(raw_target.get("href") or ""),
            value_preview=str(raw_target.get("value_preview") or ""),
            actionable=[str(item) for item in raw_target.get("actionable") or []],
            disabled=bool(raw_target.get("disabled", False)),
            checked=raw_target.get("checked") if isinstance(raw_target.get("checked"), bool) else None,
        )


def build_browser_automation_service(settings: ToolServerSettings) -> BrowserAutomationService:
    if settings.tool_mode != "windows":
        return MockBrowserAutomationService()
    if not settings.browser_automation_enabled:
        return DisabledBrowserAutomationService()

    # Avoid Playwright Sync API inside FastAPI's asyncio loop.
    return SimpleBrowserOpenService()


def _normalize_gmail_view(view: str) -> str:
    normalized = view.strip().lower()
    if normalized in {"mail", "email", "gmail", ""}:
        return "inbox"
    if normalized not in GMAIL_VIEWS:
        return "inbox"
    return normalized
