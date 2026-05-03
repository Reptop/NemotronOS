from __future__ import annotations

import asyncio
import unittest

from nemotronos_agent.config import AgentServerSettings
from nemotronos_agent.model_client import OpenAICompatibleModelClient, _extract_browser_target


class OpenAICompatibleModelClientTests(unittest.TestCase):
    def setUp(self) -> None:
        settings = AgentServerSettings(
            app_env="test",
            model_mode="openai_compatible",
            model_base_url="http://127.0.0.1:8000/v1",
            model_name="test-model",
            model_api_key="test-key",
            openai_api_key="test-openai-key",
            transcription_model="whisper-1",
            openai_base_url="https://api.openai.com/v1",
            default_downloads_path=r"C:\Users\Raed\Downloads",
            tool_server_url="http://127.0.0.1:5050",
            agent_server_url="http://127.0.0.1:5051",
            request_timeout_seconds=1,
        )
        self.client = OpenAICompatibleModelClient(settings)

    def test_extracts_legacy_function_call(self) -> None:
        message = {
            "function_call": {
                "name": "fs_plan_changes",
                "arguments": '{"root_path": "/my/downloads"}',
            }
        }

        tool_call = self.client._extract_tool_call(message)

        self.assertEqual(tool_call["function"]["name"], "fs_plan_changes")

    def test_parses_tool_arguments_as_object(self) -> None:
        arguments = self.client._parse_arguments(
            '{"root_path": "C:/Users/Raed/Downloads", "allowed_operations": ["move"]}'
        )

        self.assertEqual(arguments["root_path"], "C:/Users/Raed/Downloads")
        self.assertEqual(arguments["allowed_operations"], ["move"])

    def test_normalizes_downloads_demo_arguments(self) -> None:
        normalized = self.client._normalize_downloads_plan_arguments(
            "Organize my Downloads folder into folders by file type, but show me the plan first.",
            {
                "root_path": "/my/downloads",
                "goal": "reorganize_files",
                "allowed_operations": ["move"],
            },
        )

        self.assertEqual(normalized["root_path"], r"C:\Users\Raed\Downloads")
        self.assertEqual(
            normalized["goal"],
            "Organize my Downloads folder into folders by file type, but show me the plan first.",
        )
        self.assertEqual(normalized["allowed_operations"], ["mkdir", "move"])

    def test_notepad_typing_demo_starts_with_app_launch(self) -> None:
        planned_call = asyncio.run(
            self.client.plan_first_action(
                'Open Notepad and type "Hello from NemotronOS."',
                [],
            )
        )

        self.assertEqual(planned_call.name, "app_launch")
        self.assertEqual(planned_call.arguments, {"app_name": "notepad"})

    def test_browser_navigation_demo_opens_browser(self) -> None:
        planned_call = asyncio.run(
            self.client.plan_first_action(
                "Open my web browser and navigate to Canvas.",
                [],
            )
        )

        self.assertEqual(planned_call.name, "browser_open")
        self.assertEqual(planned_call.arguments, {"url": "Canvas"})

    def test_extracts_common_browser_targets(self) -> None:
        self.assertEqual(
            _extract_browser_target("Computer, open my web browser and go to youtube."),
            "youtube",
        )
        self.assertEqual(
            _extract_browser_target("Navigate to github.com"),
            "github.com",
        )
        self.assertIsNone(_extract_browser_target("Open Notepad and type hello."))


if __name__ == "__main__":
    unittest.main()
