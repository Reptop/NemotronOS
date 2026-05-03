from __future__ import annotations

import unittest
from pathlib import Path

from nemotronos_tools.config import ToolServerSettings
from nemotronos_tools.tools.browser_actions import (
    browser_click,
    browser_navigate,
    browser_press,
    browser_session_ensure,
    browser_snapshot,
    browser_type,
    gmail_compose_draft,
    gmail_open,
    gmail_search,
)
from nemotronos_tools.tools.browser_automation import (
    DisabledBrowserAutomationService,
    MockBrowserAutomationService,
    build_browser_automation_service,
)


class BrowserActionTests(unittest.TestCase):
    def test_mock_browser_flow_returns_structured_state(self) -> None:
        service = MockBrowserAutomationService()

        initial = browser_session_ensure({"start_url": "https://www.google.com"}, service)
        self.assertEqual(initial["title"], "Google")
        self.assertEqual(initial["targets"][0]["target_id"], "t1")

        typed = browser_type({"target_id": "t1", "text": "NemotronOS"}, service)
        self.assertIn("NemotronOS", typed["last_action"]["text"])

        searched = browser_press({"key": "Enter"}, service)
        self.assertIn("google.com/search", searched["url"])

    def test_browser_click_requires_target_id(self) -> None:
        with self.assertRaises(ValueError):
            browser_click({}, MockBrowserAutomationService())

    def test_disabled_service_raises_clear_error(self) -> None:
        with self.assertRaises(ValueError):
            browser_snapshot({}, DisabledBrowserAutomationService())

    def test_build_browser_service_uses_mock_outside_windows(self) -> None:
        settings = ToolServerSettings(
            app_env="test",
            tool_mode="mock_windows",
            fake_windows_root=Path("."),
            default_downloads_path=r"C:\Users\Raed\Downloads",
            browser_automation_enabled=True,
            browser_chrome_executable="",
            browser_user_data_dir="",
            browser_profile_dir="Default",
            browser_headless=False,
            browser_default_timeout_ms=10000,
            canvas_base_url="https://canvas.oregonstate.edu",
            canvas_api_token="",
            canvas_course_aliases={},
        )

        service = build_browser_automation_service(settings)

        self.assertIsInstance(service, MockBrowserAutomationService)

    def test_browser_navigate_normalizes_domain(self) -> None:
        result = browser_navigate({"url": "github.com"}, MockBrowserAutomationService())
        self.assertEqual(result["url"], "https://github.com")

    def test_mock_gmail_open_and_search_return_email_metadata(self) -> None:
        service = MockBrowserAutomationService()

        inbox = gmail_open({"view": "inbox"}, service)
        self.assertEqual(inbox["email"]["provider"], "gmail")
        self.assertEqual(inbox["email"]["view"], "inbox")

        search_result = gmail_search({"query": "from:alice"}, service)
        self.assertEqual(search_result["email"]["action"], "search")
        self.assertEqual(search_result["email"]["query"], "from:alice")
        self.assertIn("#search/from%3Aalice", search_result["url"])

    def test_mock_gmail_compose_draft_does_not_send(self) -> None:
        result = gmail_compose_draft(
            {
                "to": "alice@example.com",
                "subject": "Status",
                "body": "Running five minutes late.",
            },
            MockBrowserAutomationService(),
        )

        self.assertEqual(result["email"]["action"], "compose_draft")
        self.assertFalse(result["email"]["sent"])
        self.assertEqual(result["email"]["to"], "alice@example.com")


if __name__ == "__main__":
    unittest.main()
