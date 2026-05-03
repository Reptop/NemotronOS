from __future__ import annotations

import base64
import unittest

import httpx

from nemotronos_agent.voice import decode_audio_base64
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
            "Transcription failed (429): Rate limit reached.",
        )


if __name__ == "__main__":
    unittest.main()
