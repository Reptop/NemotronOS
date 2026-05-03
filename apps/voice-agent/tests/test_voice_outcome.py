from __future__ import annotations

import unittest

from nemotronos_voice_agent.main import spoken_outcome_message


class VoiceOutcomeTests(unittest.TestCase):
    def test_unknown_notify_task_gets_uncertainty_message(self) -> None:
        task = {
            "state": "completed",
            "tool_calls": [
                {
                    "name": "notify_user",
                    "result": {
                        "message": "Mock mode does not have a richer plan for: make me soup",
                    },
                }
            ],
        }

        self.assertEqual(
            spoken_outcome_message(task, "Of course, here you go."),
            "I don't know how to do that yet.",
        )

    def test_completed_real_task_gets_success_message(self) -> None:
        task = {
            "state": "completed",
            "tool_calls": [
                {
                    "name": "youtube_open",
                    "result": {"opened": True},
                }
            ],
        }

        self.assertEqual(
            spoken_outcome_message(task, "Of course, here you go."),
            "",
        )

    def test_approval_task_gets_approval_message(self) -> None:
        self.assertEqual(
            spoken_outcome_message({"state": "waiting_for_approval"}, "Done."),
            "I need your approval before I do that.",
        )


if __name__ == "__main__":
    unittest.main()
