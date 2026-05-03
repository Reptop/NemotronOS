from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import httpx

from nemotronos_voice_agent.tts import OpenAITTSSpeaker, build_speaker


class OpenAITTSTests(unittest.TestCase):
    def test_build_speaker_supports_openai_mode(self) -> None:
        speaker = build_speaker(
            tts_mode="openai",
            tts_voice="marin",
            api_key="test-key",
        )

        self.assertIsInstance(speaker, OpenAITTSSpeaker)

    def test_openai_tts_posts_speech_request_and_plays_wav(self) -> None:
        fallback = Mock()
        speaker = OpenAITTSSpeaker(
            api_key="test-key",
            base_url="https://api.openai.com/v1",
            model="gpt-4o-mini-tts",
            voice="marin",
            instructions="Speak warmly.",
            response_format="wav",
            speed=1.0,
            timeout_seconds=3,
            fallback=fallback,
        )

        response = Mock()
        response.content = b"RIFFfake-wave-data"
        response.headers = {"content-type": "audio/wav"}
        response.raise_for_status = Mock()
        client = Mock()
        client.post.return_value = response
        client.__enter__ = Mock(return_value=client)
        client.__exit__ = Mock(return_value=False)

        with (
            patch("nemotronos_voice_agent.tts.httpx.Client", return_value=client),
            patch.object(speaker, "_play_audio") as play_mock,
        ):
            speaker.speak("Hello there.")

        client.post.assert_called_once()
        _, kwargs = client.post.call_args
        self.assertEqual(kwargs["json"]["model"], "gpt-4o-mini-tts")
        self.assertEqual(kwargs["json"]["voice"], "marin")
        self.assertEqual(kwargs["json"]["response_format"], "wav")
        self.assertEqual(kwargs["json"]["instructions"], "Speak warmly.")
        play_mock.assert_called_once()
        audio_path = play_mock.call_args.args[0]
        self.assertIsInstance(audio_path, Path)
        self.assertFalse(audio_path.exists())
        fallback.speak.assert_not_called()

    def test_openai_tts_falls_back_without_api_key(self) -> None:
        fallback = Mock()
        speaker = OpenAITTSSpeaker(
            api_key="",
            base_url="https://api.openai.com/v1",
            model="gpt-4o-mini-tts",
            voice="marin",
            instructions="",
            response_format="wav",
            speed=1.0,
            timeout_seconds=3,
            fallback=fallback,
        )

        speaker.speak("Hello there.")

        fallback.speak.assert_called_once_with("Hello there.")

    def test_openai_tts_http_error_includes_response_body(self) -> None:
        fallback = Mock()
        speaker = OpenAITTSSpeaker(
            api_key="test-key",
            base_url="https://api.openai.com/v1",
            model="gpt-4o-mini-tts",
            voice="marin",
            instructions="",
            response_format="wav",
            speed=1.0,
            timeout_seconds=3,
            fallback=fallback,
        )

        request = httpx.Request("POST", "https://api.openai.com/v1/audio/speech")
        response = httpx.Response(
            status_code=400,
            request=request,
            text='{"error":{"message":"Unsupported voice"}}',
        )
        client = Mock()
        client.post.return_value = response
        client.__enter__ = Mock(return_value=client)
        client.__exit__ = Mock(return_value=False)

        with patch("nemotronos_voice_agent.tts.httpx.Client", return_value=client):
            with self.assertRaises(RuntimeError) as context:
                speaker._create_speech_file("Hello there.")

        self.assertIn("OpenAI TTS HTTP 400", str(context.exception))
        self.assertIn("Unsupported voice", str(context.exception))


if __name__ == "__main__":
    unittest.main()
