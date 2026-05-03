from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class VoiceAgentSettings:
    agent_server_url: str
    wake_mode: str
    wake_words: tuple[str, ...]
    chunk_seconds: float
    silence_seconds: float
    min_record_seconds: float
    wake_chunk_seconds: float
    wake_silence_seconds: float
    wake_min_record_seconds: float
    command_chunk_seconds: float
    command_silence_seconds: float
    command_min_record_seconds: float
    openwakeword_model_paths: tuple[str, ...]
    openwakeword_threshold: float
    openwakeword_frame_ms: int
    speech_threshold: float
    listen_block_ms: int
    sample_rate: int
    channels: int
    input_device: str | None
    request_timeout_seconds: float
    tts_mode: str
    acknowledgement: str
    listening_acknowledgement: str


def get_settings() -> VoiceAgentSettings:
    env_file = Path(os.getenv("NEMOTRONOS_ENV_FILE", ".env"))
    _load_env_file(env_file)

    wake_words = tuple(
        word.strip().lower()
        for word in os.getenv("VOICE_AGENT_WAKE_WORDS", "jarvis,computer").split(",")
        if word.strip()
    )
    openwakeword_model_paths = tuple(
        path.strip()
        for path in os.getenv("VOICE_AGENT_OPENWAKEWORD_MODELS", "hey_jarvis").split(";")
        if path.strip()
    )

    chunk_seconds = float(os.getenv("VOICE_AGENT_CHUNK_SECONDS", "4"))
    silence_seconds = float(os.getenv("VOICE_AGENT_SILENCE_SECONDS", "1.0"))
    min_record_seconds = float(os.getenv("VOICE_AGENT_MIN_RECORD_SECONDS", "0.8"))

    return VoiceAgentSettings(
        agent_server_url=os.getenv("AGENT_SERVER_URL", "http://127.0.0.1:5051"),
        wake_mode=os.getenv("VOICE_AGENT_WAKE_MODE", "whisper_poll"),
        wake_words=wake_words or ("jarvis", "computer"),
        chunk_seconds=chunk_seconds,
        silence_seconds=silence_seconds,
        min_record_seconds=min_record_seconds,
        wake_chunk_seconds=float(os.getenv("VOICE_AGENT_WAKE_CHUNK_SECONDS", str(chunk_seconds))),
        wake_silence_seconds=float(
            os.getenv("VOICE_AGENT_WAKE_SILENCE_SECONDS", str(silence_seconds))
        ),
        wake_min_record_seconds=float(
            os.getenv("VOICE_AGENT_WAKE_MIN_RECORD_SECONDS", str(min_record_seconds))
        ),
        command_chunk_seconds=float(
            os.getenv("VOICE_AGENT_COMMAND_CHUNK_SECONDS", str(chunk_seconds))
        ),
        command_silence_seconds=float(
            os.getenv("VOICE_AGENT_COMMAND_SILENCE_SECONDS", str(silence_seconds))
        ),
        command_min_record_seconds=float(
            os.getenv("VOICE_AGENT_COMMAND_MIN_RECORD_SECONDS", str(min_record_seconds))
        ),
        openwakeword_model_paths=openwakeword_model_paths,
        openwakeword_threshold=float(os.getenv("VOICE_AGENT_OPENWAKEWORD_THRESHOLD", "0.5")),
        openwakeword_frame_ms=int(os.getenv("VOICE_AGENT_OPENWAKEWORD_FRAME_MS", "80")),
        speech_threshold=float(os.getenv("VOICE_AGENT_SPEECH_THRESHOLD", "350")),
        listen_block_ms=int(os.getenv("VOICE_AGENT_LISTEN_BLOCK_MS", "100")),
        sample_rate=int(os.getenv("VOICE_AGENT_SAMPLE_RATE", "16000")),
        channels=int(os.getenv("VOICE_AGENT_CHANNELS", "1")),
        input_device=os.getenv("VOICE_AGENT_INPUT_DEVICE") or None,
        request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "30")),
        tts_mode=os.getenv("VOICE_AGENT_TTS_MODE", "windows_sapi"),
        acknowledgement=os.getenv("VOICE_AGENT_ACK", "Of course, here you go."),
        listening_acknowledgement=os.getenv("VOICE_AGENT_LISTENING_ACK", "I'm listening."),
    )


def _load_env_file(env_file: Path) -> None:
    if not env_file.exists():
        return

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value
