from __future__ import annotations

import unittest

from nemotronos_agent.coordinator import extract_notepad_text


class NotepadFollowUpTests(unittest.TestCase):
    def test_extracts_quoted_notepad_text(self) -> None:
        self.assertEqual(
            extract_notepad_text('Open a new notepad and type "It works, yuppie :)" in it.'),
            "It works, yuppie :)",
        )

    def test_extracts_unquoted_notepad_text(self) -> None:
        self.assertEqual(
            extract_notepad_text("Open notepad and type in hello from windows."),
            "hello from windows.",
        )
        self.assertEqual(
            extract_notepad_text("Open notepad and write in hello from windows."),
            "hello from windows.",
        )
        self.assertEqual(
            extract_notepad_text("Put this in Notepad hello from windows."),
            "hello from windows.",
        )

    def test_returns_none_when_no_literal_text_is_present(self) -> None:
        self.assertIsNone(extract_notepad_text("Open notepad and type."))


if __name__ == "__main__":
    unittest.main()
