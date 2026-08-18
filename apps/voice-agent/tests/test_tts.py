from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import httpx

from nemotronos_voice_agent.tts import (
    ElevenLabsTTSSpeaker,
    OpenAITTSSpeaker,
    _play_windows_audio,
    _windows_audio_reference,
    build_speaker,
)


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


class ElevenLabsTTSTests(unittest.TestCase):
    def test_build_speaker_supports_elevenlabs_mode(self) -> None:
        speaker = build_speaker(
            tts_mode="elevenlabs",
            elevenlabs_api_key="test-key",
            elevenlabs_voice_id="test-voice",
        )

        self.assertIsInstance(speaker, ElevenLabsTTSSpeaker)

    def test_elevenlabs_tts_posts_speech_request_and_plays_mp3(self) -> None:
        fallback = Mock()
        speaker = ElevenLabsTTSSpeaker(
            api_key="test-key",
            base_url="https://api.elevenlabs.io/v1",
            voice_id="test voice/id",
            model="eleven_flash_v2_5",
            output_format="mp3_44100_128",
            timeout_seconds=3,
            fallback=fallback,
        )

        response = Mock()
        response.content = b"fake-mp3-data"
        response.headers = {"content-type": "audio/mpeg"}
        response.raise_for_status = Mock()
        client = Mock()
        client.post.return_value = response
        client.__enter__ = Mock(return_value=client)
        client.__exit__ = Mock(return_value=False)

        with (
            patch("nemotronos_voice_agent.tts.httpx.Client", return_value=client),
            patch.object(speaker, "_play_audio") as play_mock,
        ):
            speaker.speak("The task is ready for review.")

        client.post.assert_called_once()
        request_url = client.post.call_args.args[0]
        request = client.post.call_args.kwargs
        self.assertEqual(
            request_url,
            "https://api.elevenlabs.io/v1/text-to-speech/test%20voice%2Fid",
        )
        self.assertEqual(request["headers"]["xi-api-key"], "test-key")
        self.assertEqual(request["params"]["output_format"], "mp3_44100_128")
        self.assertEqual(request["json"]["model_id"], "eleven_flash_v2_5")
        self.assertEqual(request["json"]["text"], "The task is ready for review.")
        audio_path = play_mock.call_args.args[0]
        self.assertEqual(audio_path.suffix, ".mp3")
        self.assertFalse(audio_path.exists())
        fallback.speak.assert_not_called()

    def test_elevenlabs_tts_falls_back_without_voice_id(self) -> None:
        fallback = Mock()
        speaker = ElevenLabsTTSSpeaker(
            api_key="test-key",
            base_url="https://api.elevenlabs.io/v1",
            voice_id="",
            model="eleven_flash_v2_5",
            output_format="mp3_44100_128",
            timeout_seconds=3,
            fallback=fallback,
        )

        speaker.speak("Hello there.")

        fallback.speak.assert_called_once_with("Hello there.")


class WindowsAudioPlaybackTests(unittest.TestCase):
    def test_wsl_audio_uses_windows_powershell_bridge(self) -> None:
        completed = Mock(returncode=0, stdout="", stderr="")
        with (
            patch(
                "nemotronos_voice_agent.tts._powershell_executable",
                return_value="/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe",
            ),
            patch(
                "nemotronos_voice_agent.tts._windows_audio_reference",
                return_value=r"\\wsl.localhost\Ubuntu\tmp\NemotronOS\tts\speech.mp3",
            ),
            patch("nemotronos_voice_agent.tts.subprocess.run", return_value=completed) as run,
        ):
            _play_windows_audio(Path("/tmp/NemotronOS/tts/speech.mp3"))

        command = run.call_args.args[0]
        self.assertTrue(command[0].endswith("powershell.exe"))
        self.assertIn("-Sta", command)
        self.assertIn(r"\\wsl.localhost\Ubuntu\tmp\NemotronOS\tts\speech.mp3", command[-1])

    def test_wsl_audio_path_is_translated_for_windows(self) -> None:
        completed = Mock(
            returncode=0,
            stdout=r"\\wsl.localhost\Ubuntu\tmp\speech.mp3" + "\n",
            stderr="",
        )
        with (
            patch("nemotronos_voice_agent.tts.platform.system", return_value="Linux"),
            patch("nemotronos_voice_agent.tts._is_wsl", return_value=True),
            patch("nemotronos_voice_agent.tts.shutil.which", return_value="/usr/bin/wslpath"),
            patch("nemotronos_voice_agent.tts.subprocess.run", return_value=completed) as run,
        ):
            translated = _windows_audio_reference(Path("/tmp/speech.mp3"))

        self.assertEqual(translated, r"\\wsl.localhost\Ubuntu\tmp\speech.mp3")
        self.assertEqual(run.call_args.args[0][1], "-w")


if __name__ == "__main__":
    unittest.main()
