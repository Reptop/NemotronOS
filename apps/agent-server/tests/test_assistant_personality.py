from __future__ import annotations

import unittest

from nemotronos_agent.assistant_personality import (
    ASSISTANT_PERSONALITY_PROMPT,
    with_assistant_personality,
)


class AssistantPersonalityTests(unittest.TestCase):
    def test_personality_balances_care_with_non_intrusive_support(self) -> None:
        self.assertIn("caring and capable", ASSISTANT_PERSONALITY_PROMPT)
        self.assertIn("work and everyday life", ASSISTANT_PERSONALITY_PROMPT)
        self.assertIn("check whether they are okay", ASSISTANT_PERSONALITY_PROMPT)
        self.assertIn(
            "Do not add a wellness check to routine requests",
            ASSISTANT_PERSONALITY_PROMPT,
        )
        self.assertIn("respectful of the user's autonomy", ASSISTANT_PERSONALITY_PROMPT)

    def test_personality_is_a_stable_instruction_prefix(self) -> None:
        prompt = with_assistant_personality("Choose exactly one tool.")

        self.assertTrue(prompt.startswith(ASSISTANT_PERSONALITY_PROMPT))
        self.assertTrue(prompt.endswith("Choose exactly one tool."))


if __name__ == "__main__":
    unittest.main()
