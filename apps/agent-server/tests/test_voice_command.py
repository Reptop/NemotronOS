from __future__ import annotations

import unittest

from nemotronos_agent.main import extract_voice_dictation_text, extract_wake_command


class VoiceCommandTests(unittest.TestCase):
    def test_extracts_text_after_word_for_word_marker(self) -> None:
        transcript = (
            "Put up a notepad and type in this word for word. "
            "Today I woke up at 6am because I could not sleep."
        )

        self.assertEqual(
            extract_voice_dictation_text(transcript),
            "Today I woke up at 6am because I could not sleep.",
        )

    def test_extracts_plain_notepad_dictation_text(self) -> None:
        transcript = "Open notepad and type in I like cats and dogs."

        self.assertEqual(
            extract_voice_dictation_text(transcript),
            "I like cats and dogs.",
        )

    def test_extracts_lifecam_dictation_text(self) -> None:
        transcript = "open Notepad and type in hello from a LifeCam."

        self.assertEqual(
            extract_voice_dictation_text(transcript),
            "hello from a LifeCam.",
        )

    def test_extracts_command_after_jarvis_wake_word(self) -> None:
        self.assertEqual(
            extract_wake_command("Jarvis, open notepad and type in hello."),
            "open notepad and type in hello.",
        )

    def test_extracts_command_after_computer_wake_word(self) -> None:
        self.assertEqual(
            extract_wake_command("hey Computer open notepad"),
            "open notepad",
        )

    def test_ignores_punctuation_only_after_wake_word(self) -> None:
        self.assertIsNone(extract_wake_command("Computer?"))
        self.assertIsNone(extract_wake_command("Jarvis?!"))

    def test_skips_punctuation_before_wake_command(self) -> None:
        self.assertEqual(
            extract_wake_command("Computer? open notepad"),
            "open notepad",
        )

    def test_ignores_partial_wake_word(self) -> None:
        self.assertIsNone(extract_wake_command("mycomputer open notepad"))


if __name__ == "__main__":
    unittest.main()
