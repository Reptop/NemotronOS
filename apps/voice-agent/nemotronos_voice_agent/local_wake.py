from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .audio import _normalize_device
from .config import VoiceAgentSettings


@dataclass(frozen=True, slots=True)
class WakeDetection:
    model_name: str
    score: float
    scores: dict[str, float]


class OpenWakeWordDetector:
    def __init__(self, settings: VoiceAgentSettings) -> None:
        if settings.sample_rate != 16000:
            raise RuntimeError("openWakeWord wake mode requires VOICE_AGENT_SAMPLE_RATE=16000.")
        if settings.channels != 1:
            raise RuntimeError("openWakeWord wake mode requires VOICE_AGENT_CHANNELS=1.")

        try:
            import sounddevice as sd
            from openwakeword.model import Model
        except ImportError as exc:
            raise RuntimeError(
                "openWakeWord wake mode requires extra local dependencies. "
                "Install them with: python -m pip install openwakeword onnxruntime"
            ) from exc

        model_kwargs: dict[str, Any] = {"inference_framework": "onnx"}
        if settings.openwakeword_model_paths:
            model_kwargs["wakeword_models"] = list(settings.openwakeword_model_paths)

        self.settings = settings
        self._sd = sd
        self._model = Model(**model_kwargs)
        self._block_frames = max(1, int(settings.sample_rate * settings.openwakeword_frame_ms / 1000))

    def wait_for_wake(self) -> WakeDetection:
        with self._sd.InputStream(
            samplerate=self.settings.sample_rate,
            channels=self.settings.channels,
            dtype="int16",
            device=_normalize_device(self.settings.input_device),
        ) as stream:
            while True:
                block, overflowed = stream.read(self._block_frames)
                del overflowed

                mono_audio = np.asarray(block, dtype=np.int16).reshape(-1)
                prediction = self._model.predict(mono_audio)
                scores = _normalize_scores(prediction)
                model_name, score = max(scores.items(), key=lambda item: item[1])
                if score >= self.settings.openwakeword_threshold:
                    return WakeDetection(
                        model_name=model_name,
                        score=score,
                        scores=scores,
                    )


def _normalize_scores(prediction: dict[str, Any]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for key, value in prediction.items():
        try:
            scores[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    if not scores:
        scores["unknown"] = 0.0
    return scores
