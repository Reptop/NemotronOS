from __future__ import annotations

import io
import math
import wave
from collections import deque

import numpy as np


def record_wav_chunk(
    seconds: float,
    sample_rate: int,
    channels: int,
    input_device: str | None = None,
) -> bytes:
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise RuntimeError(
            "sounddevice is required for microphone wake mode. "
            "Install apps/voice-agent dependencies first."
        ) from exc

    frames = int(seconds * sample_rate)
    recording = sd.rec(
        frames,
        samplerate=sample_rate,
        channels=channels,
        dtype="int16",
        blocking=True,
        device=_normalize_device(input_device),
    )
    return pcm_to_wav_bytes(recording, sample_rate, channels)


def record_wav_until_silence(
    max_seconds: float,
    silence_seconds: float,
    min_record_seconds: float,
    speech_threshold: float,
    listen_block_ms: int,
    sample_rate: int,
    channels: int,
    input_device: str | None = None,
    preroll_seconds: float = 0.35,
) -> bytes:
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise RuntimeError(
            "sounddevice is required for microphone wake mode. "
            "Install apps/voice-agent dependencies first."
        ) from exc

    block_frames = max(1, int(sample_rate * listen_block_ms / 1000))
    max_blocks = max(1, math.ceil(max_seconds * sample_rate / block_frames))
    min_blocks = max(1, math.ceil(min_record_seconds * sample_rate / block_frames))
    silence_blocks = max(1, math.ceil(silence_seconds * sample_rate / block_frames))
    preroll_blocks = max(0, math.ceil(preroll_seconds * sample_rate / block_frames))
    chunks: list[np.ndarray] = []
    preroll: deque[np.ndarray] = deque(maxlen=preroll_blocks)
    quiet_blocks = 0
    heard_voice = False

    with sd.InputStream(
        samplerate=sample_rate,
        channels=channels,
        dtype="int16",
        device=_normalize_device(input_device),
    ) as stream:
        while True:
            block, overflowed = stream.read(block_frames)
            del overflowed

            is_speech = _rms(block) >= speech_threshold
            if is_speech:
                if not heard_voice:
                    chunks.extend(item.copy() for item in preroll)
                heard_voice = True
                quiet_blocks = 0
            elif heard_voice:
                quiet_blocks += 1

            if not heard_voice:
                if preroll_blocks:
                    preroll.append(block.copy())
                continue

            chunks.append(block.copy())
            if len(chunks) >= max_blocks:
                break
            if len(chunks) >= min_blocks and quiet_blocks >= silence_blocks:
                break

    samples = np.concatenate(chunks, axis=0)
    return pcm_to_wav_bytes(samples, sample_rate, channels)


def record_command_wav(settings) -> bytes:
    return record_wav_until_silence(
        settings.command_chunk_seconds,
        settings.command_silence_seconds,
        settings.command_min_record_seconds,
        settings.speech_threshold,
        settings.listen_block_ms,
        settings.sample_rate,
        settings.channels,
        settings.input_device,
        settings.preroll_seconds,
    )


def _normalize_device(input_device: str | None) -> int | str | None:
    if input_device is None:
        return None
    if input_device.isdigit():
        return int(input_device)
    return input_device


def _rms(samples: np.ndarray) -> float:
    if samples.size == 0:
        return 0.0
    float_samples = samples.astype(np.float32)
    return float(np.sqrt(np.mean(float_samples * float_samples)))


def pcm_to_wav_bytes(samples: np.ndarray, sample_rate: int, channels: int) -> bytes:
    if samples.dtype != np.int16:
        samples = samples.astype(np.int16)

    with io.BytesIO() as buffer:
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(channels)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(samples.tobytes())
        return buffer.getvalue()
