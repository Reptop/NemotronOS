from __future__ import annotations

import unittest
import wave
from io import BytesIO

import numpy as np

from nemotronos_voice_agent.audio import _normalize_device, _rms, pcm_to_wav_bytes


class AudioTests(unittest.TestCase):
    def test_converts_pcm_to_wav_bytes(self) -> None:
        samples = np.zeros((160,), dtype=np.int16)

        wav_bytes = pcm_to_wav_bytes(samples, sample_rate=16000, channels=1)

        with wave.open(BytesIO(wav_bytes), "rb") as wav_file:
            self.assertEqual(wav_file.getframerate(), 16000)
            self.assertEqual(wav_file.getnchannels(), 1)
            self.assertEqual(wav_file.getnframes(), 160)

    def test_normalizes_numeric_input_device(self) -> None:
        self.assertEqual(_normalize_device("6"), 6)
        self.assertEqual(_normalize_device("Microphone"), "Microphone")
        self.assertIsNone(_normalize_device(None))

    def test_rms_reflects_audio_level(self) -> None:
        quiet = np.zeros((160,), dtype=np.int16)
        loud = np.full((160,), 1000, dtype=np.int16)

        self.assertEqual(_rms(quiet), 0.0)
        self.assertGreater(_rms(loud), 900)


if __name__ == "__main__":
    unittest.main()
