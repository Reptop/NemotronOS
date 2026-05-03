from __future__ import annotations

import asyncio
import unittest

from nemotronos_agent.config import AgentServerSettings
from nemotronos_agent.model_client import (
    OpenAICompatibleModelClient,
    PlannedToolCall,
    _extract_browser_target,
    _extract_canvas_arguments,
    _extract_discord_message_arguments,
    _extract_youtube_arguments,
)


class RecordingModelClient(OpenAICompatibleModelClient):
    def __init__(
        self,
        settings: AgentServerSettings,
        planned_call: PlannedToolCall | None = None,
        error: Exception | None = None,
        json_planned_call: PlannedToolCall | None = None,
        json_error: Exception | None = None,
    ) -> None:
        super().__init__(settings)
        self.planned_call = planned_call
        self.error = error
        self.json_planned_call = json_planned_call
        self.json_error = json_error
        self.payloads: list[dict] = []

    async def _request_tool_call(
        self,
        payload: dict,
        tool_definitions: list[dict],
    ) -> PlannedToolCall:
        del tool_definitions
        self.payloads.append(payload)
        if self.error:
            raise self.error
        if self.planned_call is None:
            raise RuntimeError("test client has no planned call")
        return self.planned_call

    async def _request_json_tool_call(
        self,
        goal: str,
        tool_definitions: list[dict],
        force_downloads_plan: bool,
    ) -> PlannedToolCall:
        del goal, tool_definitions, force_downloads_plan
        if self.json_error:
            raise self.json_error
        if self.json_planned_call is None:
            raise RuntimeError("test client has no JSON planned call")
        return self.json_planned_call


class OpenAICompatibleModelClientTests(unittest.TestCase):
    def setUp(self) -> None:
        settings = AgentServerSettings(
            app_env="test",
            model_mode="openai_compatible",
            model_provider="nim",
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
        self.settings = settings

    def test_ollama_provider_uses_openai_compat_chat_route(self) -> None:
        ollama_settings = AgentServerSettings(
            app_env="test",
            model_mode="openai_compatible",
            model_provider="ollama",
            model_base_url="http://localhost:11434",
            model_name="nemotron-3-nano:4b",
            model_api_key="ollama",
            openai_api_key="test-openai-key",
            transcription_model="whisper-1",
            openai_base_url="https://api.openai.com/v1",
            default_downloads_path=r"C:\Users\Raed\Downloads",
            tool_server_url="http://127.0.0.1:5050",
            agent_server_url="http://127.0.0.1:5051",
            request_timeout_seconds=1,
        )

        client = OpenAICompatibleModelClient(ollama_settings)

        self.assertEqual(
            client._chat_completions_url(),
            "http://localhost:11434/v1/chat/completions",
        )

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
        client = RecordingModelClient(
            self.settings,
            PlannedToolCall(name="app_launch", arguments={"app_name": "notepad"}),
        )

        planned_call = asyncio.run(
            client.plan_first_action(
                'Open Notepad and type "Hello from NemotronOS."',
                [],
            )
        )

        self.assertEqual(planned_call.name, "app_launch")
        self.assertEqual(planned_call.arguments, {"app_name": "notepad"})

    def test_browser_navigation_demo_opens_browser(self) -> None:
        client = RecordingModelClient(
            self.settings,
            PlannedToolCall(name="browser_open", arguments={"url": "Canvas"}),
        )

        planned_call = asyncio.run(
            client.plan_first_action(
                "Open my web browser and navigate to Canvas.",
                [],
            )
        )

        self.assertEqual(planned_call.name, "browser_open")
        self.assertEqual(planned_call.arguments, {"url": "Canvas"})

    def test_canvas_course_navigation_routes_to_canvas_tool(self) -> None:
        client = RecordingModelClient(
            self.settings,
            PlannedToolCall(
                name="canvas_open_course",
                arguments={"course_query": "intro to AI"},
            ),
        )

        planned_call = asyncio.run(
            client.plan_first_action(
                "Computer, open Canvas and navigate to my intro to AI course.",
                [],
            )
        )

        self.assertEqual(planned_call.name, "canvas_open_course")
        self.assertEqual(planned_call.arguments, {"course_query": "intro to AI"})

    def test_extracts_canvas_course_query(self) -> None:
        self.assertEqual(
            _extract_canvas_arguments("Open Canvas and navigate to my intro to AI course."),
            {"course_query": "intro to AI"},
        )
        self.assertEqual(
            _extract_canvas_arguments("Take me to my data structures class on Canvas."),
            {"course_query": "data structures"},
        )
        self.assertIsNone(_extract_canvas_arguments("Open Canvas."))

    def test_extracts_common_browser_targets(self) -> None:
        self.assertEqual(
            _extract_browser_target("Computer, open my web browser and go to youtube."),
            "youtube",
        )
        self.assertEqual(
            _extract_browser_target("Navigate to github.com"),
            "github.com",
        )
        self.assertEqual(_extract_browser_target("to cnn.com"), "cnn.com")
        self.assertEqual(_extract_browser_target("cnn.com"), "cnn.com")
        self.assertEqual(
            _extract_browser_target("Computer, go to https://cnn.com/world"),
            "https://cnn.com/world",
        )
        self.assertEqual(_extract_browser_target("to canvas"), "canvas")
        self.assertEqual(_extract_browser_target("canvas url"), "canvas")
        self.assertEqual(_extract_browser_target("Computer, go canvas"), "canvas")
        self.assertIsNone(_extract_browser_target("Open Notepad and type hello."))

    def test_youtube_random_video_routes_to_youtube_tool(self) -> None:
        client = RecordingModelClient(
            self.settings,
            PlannedToolCall(name="youtube_open", arguments={"action": "random"}),
        )

        planned_call = asyncio.run(
            client.plan_first_action(
                "Open YouTube and play a random recommended video.",
                [],
            )
        )

        self.assertEqual(planned_call.name, "youtube_open")
        self.assertEqual(planned_call.arguments, {"action": "random"})

    def test_youtube_specific_video_search_routes_to_youtube_tool(self) -> None:
        client = RecordingModelClient(
            self.settings,
            PlannedToolCall(
                name="youtube_open",
                arguments={"action": "search", "query": "lofi hip hop"},
            ),
        )

        planned_call = asyncio.run(
            client.plan_first_action(
                "Play lofi hip hop on YouTube.",
                [],
            )
        )

        self.assertEqual(planned_call.name, "youtube_open")
        self.assertEqual(
            planned_call.arguments,
            {
                "action": "search",
                "query": "lofi hip hop",
                "prefer_video_results": True,
            },
        )

    def test_youtube_clipped_play_command_routes_to_search(self) -> None:
        client = RecordingModelClient(
            self.settings,
            PlannedToolCall(
                name="youtube_open",
                arguments={"action": "search", "query": "Zajef77"},
            ),
        )

        planned_call = asyncio.run(
            client.plan_first_action(
                "Zajef77 on YouTube.",
                [],
            )
        )

        self.assertEqual(planned_call.name, "youtube_open")
        self.assertEqual(
            planned_call.arguments,
            {
                "action": "search",
                "query": "Zajef77",
                "prefer_video_results": True,
            },
        )

    def test_extracts_youtube_url_as_exact_video(self) -> None:
        self.assertEqual(
            _extract_youtube_arguments("Watch https://www.youtube.com/watch?v=abc123"),
            {"action": "video", "video_url": "https://www.youtube.com/watch?v=abc123"},
        )

    def test_discord_message_routes_to_discord_tool(self) -> None:
        client = RecordingModelClient(
            self.settings,
            PlannedToolCall(
                name="discord_send_message",
                arguments={"text": "hello hackathon team"},
            ),
        )

        planned_call = asyncio.run(
            client.plan_first_action(
                "Open Discord and send a message saying hello hackathon team.",
                [],
            )
        )

        self.assertEqual(planned_call.name, "discord_send_message")
        self.assertEqual(
            planned_call.arguments,
            {"text": "hello hackathon team", "open_if_needed": True},
        )

    def test_noisy_discord_message_routes_to_discord_tool(self) -> None:
        client = RecordingModelClient(
            self.settings,
            error=RuntimeError("model unavailable"),
            json_error=RuntimeError("json planner unavailable"),
        )

        planned_call = asyncio.run(
            client.plan_first_action(
                "chord, and send a message saying, I like polar bears.",
                [],
            )
        )

        self.assertEqual(planned_call.name, "discord_send_message")
        self.assertEqual(
            planned_call.arguments,
            {"text": "I like polar bears", "open_if_needed": True},
        )

    def test_model_payload_instructs_general_voice_routing(self) -> None:
        client = RecordingModelClient(
            self.settings,
            PlannedToolCall(name="notify_user", arguments={"message": "ok"}),
        )

        asyncio.run(client.plan_first_action("Do something vague.", []))

        system_prompt = client.payloads[0]["messages"][0]["content"]
        self.assertIn("noisy voice transcripts", system_prompt)
        self.assertIn("youtube_open", system_prompt)
        self.assertIn("discord_send_message", system_prompt)

    def test_falls_back_when_model_planning_fails(self) -> None:
        client = RecordingModelClient(
            self.settings,
            error=RuntimeError("model did not return a tool call"),
            json_error=RuntimeError("json planner did not return a tool call"),
        )

        planned_call = asyncio.run(
            client.plan_first_action(
                "Play lofi hip hop on YouTube.",
                [],
            )
        )

        self.assertEqual(planned_call.name, "youtube_open")
        self.assertEqual(
            planned_call.arguments,
            {
                "action": "search",
                "query": "lofi hip hop",
                "prefer_video_results": True,
            },
        )

    def test_uses_json_router_when_native_tool_call_is_missing(self) -> None:
        client = RecordingModelClient(
            self.settings,
            error=RuntimeError("native tool call missing"),
            json_planned_call=PlannedToolCall(
                name="youtube_open",
                arguments={"action": "search", "query": "lofi hip hop"},
                rationale="JSON router selected YouTube search.",
            ),
        )

        planned_call = asyncio.run(
            client.plan_first_action(
                "Play lofi hip hop on YouTube.",
                [],
            )
        )

        self.assertEqual(planned_call.name, "youtube_open")
        self.assertEqual(
            planned_call.arguments,
            {
                "action": "search",
                "query": "lofi hip hop",
                "prefer_video_results": True,
            },
        )

    def test_parses_json_tool_content_after_thinking_text(self) -> None:
        content = '<think>hidden</think> {"name":"browser_open","arguments":{"url":"cnn.com"}}'

        parsed = self.client._parse_json_tool_content(content)

        self.assertEqual(parsed["name"], "browser_open")
        self.assertEqual(parsed["arguments"], {"url": "cnn.com"})

    def test_extracts_discord_message_variants(self) -> None:
        self.assertEqual(
            _extract_discord_message_arguments("Send Discord a message saying be there soon."),
            {"text": "be there soon", "open_if_needed": True},
        )
        self.assertEqual(
            _extract_discord_message_arguments("Post to Discord: running five minutes late"),
            {"text": "running five minutes late", "open_if_needed": True},
        )
        self.assertEqual(
            _extract_discord_message_arguments(
                "open discord, and send a message saying I like cats."
            ),
            {"text": "I like cats", "open_if_needed": True},
        )
        self.assertEqual(
            _extract_discord_message_arguments(
                "Open a Discord and send a message saying, I like cats."
            ),
            {"text": "I like cats", "open_if_needed": True},
        )
        self.assertEqual(
            _extract_discord_message_arguments("Discord I like cats."),
            {"text": "I like cats", "open_if_needed": True},
        )
        self.assertEqual(
            _extract_discord_message_arguments(
                "chord, and send a message saying, I like polar bears."
            ),
            {"text": "I like polar bears", "open_if_needed": True},
        )
        self.assertEqual(
            _extract_discord_message_arguments("send a message saying hello team"),
            {"text": "hello team", "open_if_needed": True},
        )


if __name__ == "__main__":
    unittest.main()
