from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from nemotronos_voice_agent.config import get_settings
from nemotronos_voice_agent.main import apply_cli_overrides, parse_args


class VoiceAgentCliTests(unittest.TestCase):
    def test_tts_mode_cli_override_wins_for_current_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env_file = Path(temp_dir) / ".env"
            env_file.write_text("VOICE_AGENT_TTS_MODE=openai\n", encoding="utf-8")
            with mock.patch.dict(
                os.environ,
                {"NEMOTRONOS_ENV_FILE": str(env_file)},
                clear=True,
            ):
                settings = get_settings()

        args = parse_args(["--tts-mode", "elevenlabs", "--test-tts", "Hello"])
        updated = apply_cli_overrides(settings, args)

        self.assertEqual(settings.tts_mode, "openai")
        self.assertEqual(updated.tts_mode, "elevenlabs")
        self.assertEqual(args.test_tts, "Hello")


if __name__ == "__main__":
    unittest.main()
