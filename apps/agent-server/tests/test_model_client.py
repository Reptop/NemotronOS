from __future__ import annotations

import asyncio
import unittest
from dataclasses import replace

from nemotronos_agent.config import AgentServerSettings
from nemotronos_agent.model_client import (
    OpenAICompatibleModelClient,
    OpenAIResponsesModelClient,
    PlannedToolCall,
    build_model_client,
    _extract_accessibility_describe_arguments,
    _extract_browser_target,
    _extract_canvas_assignment_arguments,
    _extract_canvas_arguments,
    _extract_code_request_arguments,
    _extract_discord_message_arguments,
    _extract_email_draft_arguments,
    _extract_gmail_action,
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


class RecordingResponsesModelClient(OpenAIResponsesModelClient):
    def __init__(self, settings: AgentServerSettings, response_data: dict) -> None:
        super().__init__(settings)
        self.response_data = response_data
        self.payloads: list[dict] = []

    async def _post_response(self, payload: dict) -> dict:
        self.payloads.append(payload)
        return self.response_data


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

    def test_responses_api_converts_and_parses_function_call(self) -> None:
        settings = replace(
            self.settings,
            model_provider="openai",
            model_base_url="https://api.openai.com/v1",
            model_name="gpt-5.6-luna",
            model_api="responses",
        )
        client = RecordingResponsesModelClient(
            settings,
            {
                "output": [
                    {
                        "type": "function_call",
                        "name": "notify_user",
                        "arguments": '{"message":"Ready."}',
                    }
                ]
            },
        )
        tool_definitions = [
            {
                "name": "notify_user",
                "description": "Tell the user something.",
                "parameters": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                },
            }
        ]

        planned_call = asyncio.run(
            client.plan_first_action("Tell me you are ready.", tool_definitions)
        )

        self.assertEqual(planned_call.name, "notify_user")
        self.assertEqual(planned_call.arguments, {"message": "Ready."})
        payload = client.payloads[0]
        self.assertEqual(payload["model"], "gpt-5.6-luna")
        self.assertEqual(payload["tool_choice"], "required")
        self.assertFalse(payload["parallel_tool_calls"])
        self.assertEqual(payload["reasoning"], {"effort": "low"})
        self.assertEqual(payload["text"], {"verbosity": "low"})
        self.assertFalse(payload["store"])
        self.assertEqual(payload["tools"][0]["type"], "function")
        self.assertFalse(payload["tools"][0]["strict"])
        self.assertNotIn("messages", payload)

    def test_responses_api_extracts_nested_output_text(self) -> None:
        client = OpenAIResponsesModelClient(
            replace(self.settings, model_api="responses")
        )
        data = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": "You are focused on Notepad."}
                    ],
                }
            ]
        }

        self.assertEqual(
            client._extract_response_text(data),
            "You are focused on Notepad.",
        )
        self.assertEqual(
            client._responses_url(),
            "http://127.0.0.1:8000/v1/responses",
        )

    def test_build_model_client_selects_responses_transport(self) -> None:
        client = build_model_client(replace(self.settings, model_api="responses"))

        self.assertIsInstance(client, OpenAIResponsesModelClient)

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

    def test_canvas_assignment_due_dates_route_to_assignment_tool(self) -> None:
        client = RecordingModelClient(
            self.settings,
            PlannedToolCall(
                name="canvas_list_assignments_due_soon",
                arguments={"days_ahead": 7},
            ),
        )

        planned_call = asyncio.run(
            client.plan_first_action(
                "Open Canvas, find assignments due within the next week, and make a todo note.",
                [],
            )
        )

        self.assertEqual(planned_call.name, "canvas_list_assignments_due_soon")
        self.assertEqual(
            planned_call.arguments,
            {"days_ahead": 7, "include_completed": False},
        )

    def test_accessibility_request_overrides_unsupported_model_reply(self) -> None:
        client = RecordingModelClient(
            self.settings,
            PlannedToolCall(
                name="notify_user",
                arguments={"message": "I do not know how to do that yet."},
            ),
        )

        planned_call = asyncio.run(
            client.plan_first_action(
                "Describe my active window.",
                [],
            )
        )

        self.assertEqual(planned_call.name, "accessibility_describe_screen")
        self.assertEqual(
            planned_call.arguments,
            {"include_screenshot": True, "max_windows": 12},
        )

    def test_accessibility_request_falls_back_when_model_planning_fails(self) -> None:
        client = RecordingModelClient(
            self.settings,
            error=RuntimeError("model did not return a tool call"),
            json_error=RuntimeError("json planner did not return a tool call"),
        )

        planned_call = asyncio.run(
            client.plan_first_action(
                "Can you give me visual context for the foreground app?",
                [],
            )
        )

        self.assertEqual(planned_call.name, "accessibility_describe_screen")
        self.assertEqual(
            planned_call.arguments,
            {"include_screenshot": True, "max_windows": 12},
        )

    def test_open_recent_screenshot_overrides_new_capture_tool_call(self) -> None:
        client = RecordingModelClient(
            self.settings,
            PlannedToolCall(name="screen_capture", arguments={}),
        )

        planned_call = asyncio.run(
            client.plan_first_action(
                "Can you open that screenshot that you just took?",
                [],
            )
        )

        self.assertEqual(planned_call.name, "screenshot_open")
        self.assertEqual(planned_call.arguments, {})

    def test_canvas_assignment_request_overrides_premature_sticky_tool(self) -> None:
        client = RecordingModelClient(
            self.settings,
            PlannedToolCall(
                name="sticky_note_create",
                arguments={"text": "todo"},
            ),
        )

        planned_call = asyncio.run(
            client.plan_first_action(
                "Open Canvas, find assignments due within the next week, and make a sticky note.",
                [],
            )
        )

        self.assertEqual(planned_call.name, "canvas_list_assignments_due_soon")
        self.assertEqual(
            planned_call.arguments,
            {"days_ahead": 7, "include_completed": False},
        )

    def test_synonym_variants_override_unsupported_model_reply(self) -> None:
        cases = (
            (
                "Please pull up cnn.com.",
                "browser_open",
                {"url": "cnn.com"},
            ),
            (
                "Pull up my intro to AI class in Canvas.",
                "canvas_open_course",
                {"course_query": "intro to AI"},
            ),
            (
                "Show me Canvas homework coming 5 days.",
                "canvas_list_assignments_due_soon",
                {"days_ahead": 5, "include_completed": False},
            ),
            (
                "Put on Zajef77 on YouTube.",
                "youtube_open",
                {
                    "action": "search",
                    "query": "Zajef77",
                    "prefer_video_results": True,
                },
            ),
            (
                "Write Discord saying running late.",
                "discord_send_message",
                {"text": "running late", "open_if_needed": True},
            ),
            (
                "Prepare an email to alex@example.com with subject Demo saying hello.",
                "email_create_draft",
                {"to": "alex@example.com", "subject": "Demo", "body": "hello."},
            ),
            (
                "Could you make me a small HTML game?",
                "vscode_paste_code",
                {
                    "request": "Could you make me a small HTML game",
                    "language": "html",
                    "open_new_window": True,
                },
            ),
            (
                "Write in Notepad hello there.",
                "app_launch",
                {"app_name": "notepad"},
            ),
            (
                "Help me see the current page.",
                "accessibility_describe_screen",
                {"include_screenshot": True, "max_windows": 12},
            ),
        )

        for goal, expected_name, expected_arguments in cases:
            with self.subTest(goal=goal):
                client = RecordingModelClient(
                    self.settings,
                    PlannedToolCall(
                        name="notify_user",
                        arguments={"message": "I do not know how to do that yet."},
                    ),
                )

                planned_call = asyncio.run(client.plan_first_action(goal, []))

                self.assertEqual(planned_call.name, expected_name)
                self.assertEqual(planned_call.arguments, expected_arguments)

    def test_extracts_canvas_assignment_window(self) -> None:
        self.assertEqual(
            _extract_canvas_assignment_arguments(
                "Open Canvas and find assignments due within the next week."
            ),
            {"days_ahead": 7, "include_completed": False},
        )
        self.assertEqual(
            _extract_canvas_assignment_arguments(
                "Check Canvas homework due within 3 days for my intro to AI course."
            ),
            {
                "days_ahead": 3,
                "include_completed": False,
                "course_query": "intro to AI",
            },
        )
        self.assertEqual(
            _extract_canvas_assignment_arguments(
                "Show me Canvas projects coming 5 days."
            ),
            {"days_ahead": 5, "include_completed": False},
        )
        self.assertIsNone(_extract_canvas_assignment_arguments("Open Canvas."))

    def test_extracts_canvas_course_query(self) -> None:
        self.assertEqual(
            _extract_canvas_arguments("Open Canvas and navigate to my intro to AI course."),
            {"course_query": "intro to AI"},
        )
        self.assertEqual(
            _extract_canvas_arguments("Take me to my data structures class on Canvas."),
            {"course_query": "data structures"},
        )
        self.assertEqual(
            _extract_canvas_arguments("Pull up my intro to AI class in Canvas."),
            {"course_query": "intro to AI"},
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
        self.assertEqual(_extract_browser_target("Please pull up cnn.com."), "cnn.com")
        self.assertEqual(_extract_browser_target("Take me to canvas."), "canvas")
        self.assertEqual(_extract_browser_target("Visit oregonstate.edu."), "oregonstate.edu")
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
        self.assertEqual(
            _extract_youtube_arguments("Put on Zajef77 on YouTube."),
            {
                "action": "search",
                "query": "Zajef77",
                "prefer_video_results": True,
            },
        )
        self.assertEqual(
            _extract_youtube_arguments("Open YouTube and play something recommended."),
            {"action": "random"},
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

    def test_code_request_routes_to_vscode_tool(self) -> None:
        client = RecordingModelClient(
            self.settings,
            PlannedToolCall(
                name="vscode_paste_code",
                arguments={"request": "Code me a Python snake game.", "language": "python"},
            ),
        )

        planned_call = asyncio.run(
            client.plan_first_action("Code me a Python snake game.", [])
        )

        self.assertEqual(planned_call.name, "vscode_paste_code")
        self.assertEqual(
            planned_call.arguments,
            {
                "request": "Code me a Python snake game.",
                "language": "python",
                "open_new_window": True,
            },
        )

    def test_code_request_overrides_notify_misroute(self) -> None:
        client = RecordingModelClient(
            self.settings,
            PlannedToolCall(
                name="notify_user",
                arguments={"message": "I do not know how to do that yet."},
            ),
        )

        planned_call = asyncio.run(
            client.plan_first_action(
                "Code me a tic-tac-toe game written in Swift.",
                [],
            )
        )

        self.assertEqual(planned_call.name, "vscode_paste_code")
        self.assertEqual(
            planned_call.arguments,
            {
                "request": "Code me a tic-tac-toe game written in Swift",
                "language": "swift",
                "open_new_window": True,
            },
        )

    def test_email_compose_request_routes_to_gmail_draft_tool(self) -> None:
        client = RecordingModelClient(
            self.settings,
            PlannedToolCall(
                name="email_create_draft",
                arguments={
                    "to": "alex@example.com",
                    "subject": "Hackathon update",
                    "body": "I finished the demo slice.",
                },
            ),
        )

        planned_call = asyncio.run(
            client.plan_first_action(
                "Compose an email to alex@example.com with subject Hackathon update "
                "saying I finished the demo slice.",
                [],
            )
        )

        self.assertEqual(planned_call.name, "email_create_draft")
        self.assertEqual(
            planned_call.arguments,
            {
                "to": "alex@example.com",
                "subject": "Hackathon update",
                "body": "I finished the demo slice.",
            },
        )

    def test_email_compose_overrides_browser_misroute(self) -> None:
        client = RecordingModelClient(
            self.settings,
            PlannedToolCall(
                name="browser_open",
                arguments={"url": "gmail"},
            ),
        )

        planned_call = asyncio.run(
            client.plan_first_action(
                "Compose an email to alex@example.com saying I finished the demo slice.",
                [],
            )
        )

        self.assertEqual(planned_call.name, "email_create_draft")
        self.assertEqual(
            planned_call.arguments,
            {
                "to": "alex@example.com",
                "body": "I finished the demo slice.",
            },
        )

    def test_extracts_code_request_arguments(self) -> None:
        self.assertEqual(
            _extract_code_request_arguments(
                "Computer, code me a Python script that prints hello in VS Code."
            ),
            {
                "request": "code me a Python script that prints hello",
                "language": "python",
                "open_new_window": True,
            },
        )
        self.assertEqual(
            _extract_code_request_arguments(
                "Code me a tic-tac-toe game written in Swift."
            ),
            {
                "request": "Code me a tic-tac-toe game written in Swift",
                "language": "swift",
                "open_new_window": True,
            },
        )
        self.assertEqual(
            _extract_code_request_arguments("Make a tic tac toe app in Swift."),
            {
                "request": "Make a tic tac toe app in Swift",
                "language": "swift",
                "open_new_window": True,
            },
        )
        self.assertEqual(
            _extract_code_request_arguments("Could you make me a small HTML game?"),
            {
                "request": "Could you make me a small HTML game",
                "language": "html",
                "open_new_window": True,
            },
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
        self.assertIn("vscode_paste_code", system_prompt)
        self.assertIn("email_create_draft", system_prompt)
        self.assertIn("canvas_list_assignments_due_soon", system_prompt)
        self.assertIn("accessibility_describe_screen", system_prompt)
        self.assertIn("gmail_compose_draft", system_prompt)
        self.assertIn("simple arithmetic", system_prompt)
        self.assertIn("Do not launch an app, browser, or Calculator", system_prompt)
        self.assertIn("explicitly asks to open, launch, or start", system_prompt)
        self.assertIn("AI assistant for both work and everyday life", system_prompt)
        self.assertIn("Do not add a wellness check to routine requests", system_prompt)
        self.assertIn("Never claim to have feelings", system_prompt)

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
        self.assertEqual(
            _extract_discord_message_arguments("Write Discord saying running late."),
            {"text": "running late", "open_if_needed": True},
        )

    def test_extracts_email_draft_arguments(self) -> None:
        self.assertEqual(
            _extract_email_draft_arguments(
                "Compose an email to alex@example.com with subject Hackathon update "
                "saying I finished the demo slice."
            ),
            {
                "to": "alex@example.com",
                "subject": "Hackathon update",
                "body": "I finished the demo slice.",
            },
        )
        self.assertEqual(
            _extract_email_draft_arguments(
                "Compose an email to example.com with the subject Nemotron OS "
                "saying this is a draft created by Nemotron OS."
            ),
            {
                "to": "example.com",
                "subject": "Nemotron OS",
                "body": "this is a draft created by Nemotron OS.",
            },
        )
        self.assertEqual(
            _extract_email_draft_arguments("send a message to raed@example.com saying hello"),
            {"to": "raed@example.com", "body": "hello"},
        )
        self.assertEqual(
            _extract_email_draft_arguments(
                "Prepare an email to alex@example.com with subject line Demo saying hello."
            ),
            {"to": "alex@example.com", "subject": "Demo", "body": "hello."},
        )
        self.assertIsNone(_extract_email_draft_arguments("send a message saying hello team"))

    def test_extracts_accessibility_describe_arguments(self) -> None:
        self.assertEqual(
            _extract_accessibility_describe_arguments("Describe my active window."),
            {"include_screenshot": True, "max_windows": 12},
        )
        self.assertEqual(
            _extract_accessibility_describe_arguments(
                "Can you give me visual context for the foreground app?"
            ),
            {"include_screenshot": True, "max_windows": 12},
        )
        self.assertEqual(
            _extract_accessibility_describe_arguments("What am I looking at?"),
            {"include_screenshot": True, "max_windows": 12},
        )
        self.assertEqual(
            _extract_accessibility_describe_arguments("Help me see the current page."),
            {"include_screenshot": True, "max_windows": 12},
        )
        self.assertIsNone(
            _extract_accessibility_describe_arguments("Open Notepad and type hello.")
        )

    def test_gmail_open_search_and_compose_fallbacks(self) -> None:
        open_call = _extract_gmail_action("Open Gmail.")
        self.assertIsNotNone(open_call)
        assert open_call is not None
        self.assertEqual(open_call.name, "gmail_open")
        self.assertEqual(open_call.arguments, {"view": "inbox"})

        search_call = _extract_gmail_action("Search my Gmail for from Alice invoices.")
        self.assertIsNotNone(search_call)
        assert search_call is not None
        self.assertEqual(search_call.name, "gmail_search")
        self.assertEqual(search_call.arguments, {"query": "from Alice invoices"})

        compose_call = _extract_gmail_action(
            'Send an email to alice@example.com subject Status saying "Running five minutes late."'
        )
        self.assertIsNotNone(compose_call)
        assert compose_call is not None
        self.assertEqual(compose_call.name, "gmail_compose_draft")
        self.assertEqual(
            compose_call.arguments,
            {
                "to": "alice@example.com",
                "subject": "Status",
                "body": "Running five minutes late.",
            },
        )


if __name__ == "__main__":
    unittest.main()
