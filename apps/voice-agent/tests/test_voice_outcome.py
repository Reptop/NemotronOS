from __future__ import annotations

import asyncio
from types import SimpleNamespace
import unittest

from nemotronos_voice_agent.main import (
    command_acknowledgement,
    is_spoken_result_command,
    speak_for_final_task_outcome,
    spoken_outcome_message,
)


class _FakeAgentClient:
    def __init__(self, snapshots: list[dict]) -> None:
        self.snapshots = snapshots

    async def get_task(self, task_id: str) -> dict:
        del task_id
        if self.snapshots:
            return self.snapshots.pop(0)
        return {"id": "task-1", "state": "planning"}


class _CapturingSpeaker:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def speak(self, text: str) -> None:
        self.messages.append(text)


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

    def test_completed_accessibility_task_speaks_voice_response(self) -> None:
        task = {
            "state": "completed",
            "memory": {
                "voice_response_text": "You are on the Canvas assignments page.",
            },
            "tool_calls": [
                {
                    "name": "accessibility_describe_screen",
                    "result": {"foreground_window": {"title": "Canvas"}},
                }
            ],
        }

        self.assertEqual(
            spoken_outcome_message(task, "Of course, here you go."),
            "You are on the Canvas assignments page.",
        )

    def test_approval_task_gets_approval_message(self) -> None:
        self.assertEqual(
            spoken_outcome_message({"state": "waiting_for_approval"}, "Done."),
            "I need your approval before I do that.",
        )

    def test_background_final_outcome_speaks_delayed_voice_response(self) -> None:
        client = _FakeAgentClient(
            [
                {"id": "task-1", "state": "planning"},
                {
                    "id": "task-1",
                    "state": "completed",
                    "memory": {"voice_response_text": "You are focused on Codex."},
                },
            ]
        )
        speaker = _CapturingSpeaker()
        settings = SimpleNamespace(
            final_outcome_wait_seconds=2.0,
            acknowledgement="Done.",
        )

        asyncio.run(
            speak_for_final_task_outcome(
                client,
                speaker,
                {"id": "task-1", "state": "planning"},
                settings,
            )
        )

        self.assertEqual(speaker.messages, ["You are focused on Codex."])

    def test_accessibility_commands_get_accessibility_acknowledgement(self) -> None:
        settings = SimpleNamespace(
            submitted_acknowledgement="Got it.",
            accessibility_acknowledgement="Let me take a look.",
        )

        self.assertTrue(is_spoken_result_command("explain the active window"))
        self.assertTrue(is_spoken_result_command("what did the AI just do"))
        self.assertEqual(
            command_acknowledgement("explain the active window", settings),
            "Let me take a look.",
        )
        self.assertEqual(
            command_acknowledgement("open youtube", settings),
            "Got it.",
        )


if __name__ == "__main__":
    unittest.main()
