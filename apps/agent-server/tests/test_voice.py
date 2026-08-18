from __future__ import annotations

import base64
import unittest
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import httpx

from nemotronos_agent.config import AgentServerSettings
from nemotronos_agent.voice import VoiceTranscriber, decode_audio_base64
from nemotronos_agent.voice import _format_transcription_error


class VoiceTests(unittest.TestCase):
    def test_decodes_plain_base64_audio(self) -> None:
        audio = b"fake-webm"

        self.assertEqual(decode_audio_base64(base64.b64encode(audio).decode()), audio)

    def test_decodes_data_url_audio(self) -> None:
        audio = b"fake-webm"
        payload = base64.b64encode(audio).decode()

        self.assertEqual(decode_audio_base64(f"data:audio/webm;base64,{payload}"), audio)

    def test_rejects_invalid_base64_audio(self) -> None:
        with self.assertRaises(ValueError):
            decode_audio_base64("not-base64!")

    def test_formats_openai_error_message(self) -> None:
        response = httpx.Response(
            429,
            json={"error": {"message": "Rate limit reached."}},
        )

        self.assertEqual(
            _format_transcription_error(response),
            "OpenAI transcription failed (429): Rate limit reached.",
        )


class VoiceTranscriberTests(unittest.IsolatedAsyncioTestCase):
    async def test_elevenlabs_transcription_uses_scribe_endpoint(self) -> None:
        settings = AgentServerSettings(
            app_env="test",
            model_mode="mock",
            model_provider="nim",
            model_base_url="http://localhost:8000/v1",
            model_name="mock",
            model_api_key="local-dev-key",
            openai_api_key="",
            transcription_model="whisper-1",
            openai_base_url="https://api.openai.com/v1",
            default_downloads_path=r"C:\Users\Raed\Downloads",
            tool_server_url="http://localhost:5050",
            agent_server_url="http://localhost:5051",
            request_timeout_seconds=3,
            transcription_provider="elevenlabs",
            elevenlabs_api_key="test-elevenlabs-key",
            elevenlabs_base_url="https://api.elevenlabs.io/v1",
            elevenlabs_stt_model="scribe_v2",
        )
        response = Mock(status_code=200)
        response.json.return_value = {"text": "Computer, open Notepad."}
        client = MagicMock()
        client.post = AsyncMock(return_value=response)
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "nemotronos_agent.voice.httpx.AsyncClient",
            return_value=client,
        ):
            result = await VoiceTranscriber(settings).transcribe(
                base64.b64encode(b"fake-webm").decode(),
                "audio/webm",
                "voice-command.webm",
            )

        self.assertEqual(result["text"], "Computer, open Notepad.")
        self.assertEqual(result["provider"], "elevenlabs")
        self.assertEqual(result["model"], "scribe_v2")
        request_url = client.post.call_args.args[0]
        request = client.post.call_args.kwargs
        self.assertEqual(request_url, "https://api.elevenlabs.io/v1/speech-to-text")
        self.assertEqual(request["headers"]["xi-api-key"], "test-elevenlabs-key")
        self.assertEqual(request["data"], {"model_id": "scribe_v2"})
        self.assertEqual(request["files"]["file"][0], "voice-command.webm")

    async def test_elevenlabs_transcription_requires_api_key(self) -> None:
        settings = AgentServerSettings(
            app_env="test",
            model_mode="mock",
            model_provider="nim",
            model_base_url="http://localhost:8000/v1",
            model_name="mock",
            model_api_key="local-dev-key",
            openai_api_key="",
            transcription_model="whisper-1",
            openai_base_url="https://api.openai.com/v1",
            default_downloads_path=r"C:\Users\Raed\Downloads",
            tool_server_url="http://localhost:5050",
            agent_server_url="http://localhost:5051",
            request_timeout_seconds=3,
            transcription_provider="elevenlabs",
        )

        with self.assertRaisesRegex(RuntimeError, "ELEVENLABS_API_KEY"):
            await VoiceTranscriber(settings).transcribe(
                base64.b64encode(b"fake-webm").decode(),
                "audio/webm",
                "voice-command.webm",
            )


if __name__ == "__main__":
    unittest.main()
