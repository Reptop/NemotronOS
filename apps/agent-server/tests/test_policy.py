from __future__ import annotations

import unittest

from nemotronos_agent.policy import PolicyEngine


class PolicyEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = PolicyEngine()

    def test_browser_read_actions_are_low_risk(self) -> None:
        for tool_name in (
            "browser_session_ensure",
            "browser_navigate",
            "browser_snapshot",
            "canvas_list_assignments_due_soon",
            "accessibility_describe_screen",
            "gmail_open",
            "gmail_search",
        ):
            decision = self.policy.classify(tool_name, {})
            self.assertEqual(decision.risk_level, "low")
            self.assertTrue(decision.allowed)

    def test_browser_mutation_actions_are_medium_risk(self) -> None:
        decision = self.policy.classify("browser_click", {"target_id": "t1"})
        self.assertEqual(decision.risk_level, "medium")
        self.assertTrue(decision.allowed)

    def test_browser_type_enforces_length_limit(self) -> None:
        decision = self.policy.classify("browser_type", {"text": "x" * 501})
        self.assertFalse(decision.allowed)

    def test_sticky_note_enforces_length_limit(self) -> None:
        allowed = self.policy.classify("sticky_note_create", {"text": "todo"})
        blocked = self.policy.classify("sticky_note_create", {"text": "x" * 4001})

        self.assertEqual(allowed.risk_level, "medium")
        self.assertTrue(allowed.allowed)
        self.assertFalse(blocked.allowed)

    def test_email_create_draft_is_medium_risk_and_limited(self) -> None:
        allowed = self.policy.classify(
            "email_create_draft",
            {
                "to": "alex@example.com",
                "subject": "Hello",
                "body": "Draft body",
            },
        )
        missing_recipient = self.policy.classify(
            "email_create_draft",
            {"subject": "Hello", "body": "Draft body"},
        )
        long_body = self.policy.classify(
            "email_create_draft",
            {"to": "alex@example.com", "body": "x" * 10001},
        )
        invalid_recipient = self.policy.classify(
            "email_create_draft",
            {"to": "example.com", "subject": "Hello", "body": "Draft body"},
        )

        self.assertEqual(allowed.risk_level, "medium")
        self.assertTrue(allowed.allowed)
        self.assertFalse(missing_recipient.allowed)
        self.assertFalse(long_body.allowed)
        self.assertFalse(invalid_recipient.allowed)
        self.assertIn("alex@example.com", invalid_recipient.reason)

    def test_gmail_read_actions_are_low_risk_and_drafts_are_medium_risk(self) -> None:
        for tool_name in ("gmail_open", "gmail_search"):
            decision = self.policy.classify(tool_name, {"query": "from:alice"})
            self.assertEqual(decision.risk_level, "low")
            self.assertTrue(decision.allowed)

        draft_decision = self.policy.classify(
            "gmail_compose_draft",
            {
                "to": "alice@example.com",
                "subject": "Status",
                "body": "Running five minutes late.",
            },
        )
        self.assertEqual(draft_decision.risk_level, "medium")
        self.assertTrue(draft_decision.allowed)


if __name__ == "__main__":
    unittest.main()
