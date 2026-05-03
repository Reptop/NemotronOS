from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from nemotronos_agent.config import _load_env_file, get_settings


class ConfigTests(unittest.TestCase):
    def test_env_file_overrides_existing_environment_value(self) -> None:
        previous = os.environ.get("NEMOTRONOS_TEST_KEY")
        os.environ["NEMOTRONOS_TEST_KEY"] = "old"

        with tempfile.TemporaryDirectory() as temp_dir:
            env_file = Path(temp_dir) / ".env"
            env_file.write_text('NEMOTRONOS_TEST_KEY="new"\n', encoding="utf-8")

            _load_env_file(env_file)

        self.assertEqual(os.environ["NEMOTRONOS_TEST_KEY"], "new")
        if previous is None:
            os.environ.pop("NEMOTRONOS_TEST_KEY", None)
        else:
            os.environ["NEMOTRONOS_TEST_KEY"] = previous

    def test_ollama_provider_sets_local_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env_file = Path(temp_dir) / ".missing.env"
            with mock.patch.dict(
                os.environ,
                {
                    "NEMOTRONOS_ENV_FILE": str(env_file),
                    "MODEL_PROVIDER": "ollama",
                },
                clear=True,
            ):
                settings = get_settings()

        self.assertEqual(settings.model_provider, "ollama")
        self.assertEqual(settings.model_base_url, "http://localhost:11434")
        self.assertEqual(settings.model_name, "nemotron-3-nano:4b")
        self.assertEqual(settings.model_api_key, "ollama")


if __name__ == "__main__":
    unittest.main()
