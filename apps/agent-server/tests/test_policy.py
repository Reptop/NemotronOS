from __future__ import annotations

import unittest

from nemotronos_agent.policy import PolicyEngine


class PolicyEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = PolicyEngine()

    def test_browser_read_actions_are_low_risk(self) -> None:
        for tool_name in ("browser_session_ensure", "browser_navigate", "browser_snapshot"):
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
