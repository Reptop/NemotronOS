from __future__ import annotations

import unittest

from nemotronos_agent.config import AgentServerSettings
from nemotronos_agent.event_log import EventLog
from nemotronos_agent.task_store import TaskStore
from nemotronos_agent.worker import AgentWorker


class AgentWorkerTests(unittest.TestCase):
    def test_redacts_text_ref_arguments(self) -> None:
        worker = AgentWorker(
            settings=AgentServerSettings(
                app_env="test",
                model_mode="mock",
                model_provider="nim",
                model_base_url="http://127.0.0.1:8000/v1",
                model_name="mock",
                model_api_key="local-dev-key",
                openai_api_key="",
                transcription_model="whisper-1",
                openai_base_url="https://api.openai.com/v1",
                default_downloads_path=r"C:\Users\Raed\Downloads",
                tool_server_url="http://127.0.0.1:5050",
                agent_server_url="http://127.0.0.1:5051",
                request_timeout_seconds=1,
            ),
            task_store=TaskStore(),
            event_log=EventLog(),
        )

        redacted = worker._redact_tool_arguments(
            {
                "text": "Today I woke up at 6am.",
                "text_ref": "task.memory.voice_transcript",
            }
        )

        self.assertEqual(redacted["text"], "<23 chars from task.memory.voice_transcript>")

    def test_redacts_code_ref_arguments(self) -> None:
        worker = AgentWorker(
            settings=AgentServerSettings(
                app_env="test",
                model_mode="mock",
                model_base_url="http://127.0.0.1:8000/v1",
                model_name="mock",
                model_api_key="local-dev-key",
                openai_api_key="",
                transcription_model="whisper-1",
                openai_base_url="https://api.openai.com/v1",
                default_downloads_path=r"C:\Users\Raed\Downloads",
                tool_server_url="http://127.0.0.1:5050",
                agent_server_url="http://127.0.0.1:5051",
                request_timeout_seconds=1,
            ),
            task_store=TaskStore(),
            event_log=EventLog(),
        )

        redacted = worker._redact_tool_arguments(
            {
                "code": "print('hello')",
                "code_ref": "task.memory.generated_code",
            }
        )

        self.assertEqual(redacted["code"], "<14 chars from task.memory.generated_code>")


if __name__ == "__main__":
    unittest.main()
