from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
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
            from pyopen_wakeword import Model, OpenWakeWord, OpenWakeWordFeatures
        except ImportError as exc:
            raise RuntimeError(
                "openWakeWord wake mode requires extra local dependencies. "
                "Install them with: python -m pip install -e "
                "'apps/voice-agent[openwakeword]'"
            ) from exc

        self.settings = settings
        self._sd = sd
        self._features = OpenWakeWordFeatures.from_builtin()
        self._models = _load_models(
            settings.openwakeword_model_paths,
            Model,
            OpenWakeWord,
        )
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
                scores = _score_audio(
                    self._features,
                    self._models,
                    mono_audio.tobytes(),
                )
                if not scores:
                    continue
                model_name, score = max(scores.items(), key=lambda item: item[1])
                if score >= self.settings.openwakeword_threshold:
                    self._reset()
                    return WakeDetection(
                        model_name=model_name,
                        score=score,
                        scores=scores,
                    )


    def _reset(self) -> None:
        self._features.reset()
        for model in self._models:
            model.reset()


def _load_models(
    model_specs: tuple[str, ...],
    model_enum: Any,
    openwakeword_class: Any,
) -> list[Any]:
    specs = model_specs or ("hey_jarvis",)
    models: list[Any] = []
    available_models = ", ".join(item.value for item in model_enum)
    for raw_spec in specs:
        spec = raw_spec.strip()
        model_path = Path(spec).expanduser()
        if model_path.is_file():
            models.append(openwakeword_class.from_model(model_path))
            continue
        try:
            built_in_model = model_enum(spec.lower())
        except ValueError as exc:
            raise RuntimeError(
                f"Unknown local wake model '{spec}'. Use one of: {available_models}; "
                "or provide a path to a custom .tflite model."
            ) from exc
        models.append(openwakeword_class.from_builtin(built_in_model))
    return models


def _score_audio(features: Any, models: list[Any], audio_bytes: bytes) -> dict[str, float]:
    scores: dict[str, float] = {}
    for embeddings in features.process_streaming(audio_bytes):
        for model in models:
            for value in model.process_streaming(embeddings):
                score = float(value)
                model_name = str(model.id)
                scores[model_name] = max(scores.get(model_name, 0.0), score)
    return scores
