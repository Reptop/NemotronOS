from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AgentServerSettings:
    app_env: str
    model_mode: str
    model_provider: str
    model_base_url: str
    model_name: str
    model_api_key: str
    openai_api_key: str
    transcription_model: str
    openai_base_url: str
    default_downloads_path: str
    tool_server_url: str
    agent_server_url: str
    request_timeout_seconds: float


def get_settings() -> AgentServerSettings:
    env_file = Path(os.getenv("NEMOTRONOS_ENV_FILE", ".env"))
    _load_env_file(env_file)
    model_provider = os.getenv("MODEL_PROVIDER", "nim").strip().lower() or "nim"

    return AgentServerSettings(
        app_env=os.getenv("APP_ENV", "mac_dev"),
        model_mode=os.getenv("MODEL_MODE", "mock"),
        model_provider=model_provider,
        model_base_url=os.getenv("MODEL_BASE_URL", _default_model_base_url(model_provider)),
        model_name=os.getenv("MODEL_NAME", _default_model_name(model_provider)),
        model_api_key=os.getenv("MODEL_API_KEY", _default_model_api_key(model_provider)),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        transcription_model=os.getenv("TRANSCRIPTION_MODEL", "whisper-1"),
        openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        default_downloads_path=os.getenv(
            "DEFAULT_DOWNLOADS_PATH",
            r"C:\Users\Raed\Downloads",
        ),
        tool_server_url=os.getenv("TOOL_SERVER_URL", "http://localhost:5050"),
        agent_server_url=os.getenv("AGENT_SERVER_URL", "http://localhost:5051"),
        request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "15")),
    )


def _default_model_base_url(model_provider: str) -> str:
    if model_provider == "ollama":
        return "http://localhost:11434"
    return "http://localhost:8000/v1"


def _default_model_name(model_provider: str) -> str:
    if model_provider == "ollama":
        return "nemotron-3-nano:4b"
    return "mock"


def _default_model_api_key(model_provider: str) -> str:
    if model_provider == "ollama":
        return "ollama"
    return "local-dev-key"


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
