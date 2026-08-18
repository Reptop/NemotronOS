from __future__ import annotations

import tempfile
import unittest
from enum import Enum
from pathlib import Path
from unittest.mock import Mock

from nemotronos_voice_agent.local_wake import _load_models, _score_audio


class _FakeModel(str, Enum):
    HEY_JARVIS = "hey_jarvis"


class LocalWakeTests(unittest.TestCase):
    def test_loads_builtin_pyopenwakeword_model(self) -> None:
        wakeword_class = Mock()
        wakeword_class.from_builtin.return_value = Mock(id="hey_jarvis")

        models = _load_models(("hey_jarvis",), _FakeModel, wakeword_class)

        wakeword_class.from_builtin.assert_called_once_with(_FakeModel.HEY_JARVIS)
        self.assertEqual(models[0].id, "hey_jarvis")

    def test_loads_custom_tflite_model_path(self) -> None:
        wakeword_class = Mock()
        wakeword_class.from_model.return_value = Mock(id="hey_nova")
        with tempfile.TemporaryDirectory() as temp_dir:
            model_path = Path(temp_dir) / "hey_nova.tflite"
            model_path.touch()

            models = _load_models((str(model_path),), _FakeModel, wakeword_class)

        wakeword_class.from_model.assert_called_once_with(model_path)
        self.assertEqual(models[0].id, "hey_nova")

    def test_rejects_unknown_builtin_model_with_choices(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "hey_jarvis"):
            _load_models(("hey_nova",), _FakeModel, Mock())

    def test_scores_streaming_embeddings_for_each_model(self) -> None:
        features = Mock()
        features.process_streaming.return_value = ["embedding-1", "embedding-2"]
        model = Mock(id="hey_jarvis")
        model.process_streaming.side_effect = [[0.25], [0.75]]

        scores = _score_audio(features, [model], b"audio")

        self.assertEqual(scores, {"hey_jarvis": 0.75})


if __name__ == "__main__":
    unittest.main()
