from __future__ import annotations

import unittest

from nemotronos_voice_agent.wake import extract_wake_command, has_wake_word


class WakeTests(unittest.TestCase):
    def test_extracts_command_after_wake_word(self) -> None:
        self.assertEqual(
            extract_wake_command(
                "Computer, open YouTube and play a random video",
                ("jarvis", "computer"),
            ),
            "open YouTube and play a random video",
        )

    def test_ignores_partial_word(self) -> None:
        self.assertIsNone(
            extract_wake_command("mycomputer open YouTube", ("jarvis", "computer"))
        )
        self.assertFalse(has_wake_word("mycomputer open YouTube", ("jarvis", "computer")))

    def test_detects_wake_word_without_command(self) -> None:
        self.assertTrue(has_wake_word("Computer.", ("jarvis", "computer")))
        self.assertIsNone(extract_wake_command("Computer.", ("jarvis", "computer")))

    def test_finds_later_valid_wake_word(self) -> None:
        self.assertEqual(
            extract_wake_command("mycomputer is noisy. Computer, open Notepad", ("computer",)),
            "open Notepad",
        )


if __name__ == "__main__":
    unittest.main()
