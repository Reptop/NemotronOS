from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AgentServerSettings:
    app_env: str
    model_mode: str
    model_base_url: str
    model_name: str
    model_api_key: str
    tool_server_url: str
    agent_server_url: str
    request_timeout_seconds: float


def get_settings() -> AgentServerSettings:
    return AgentServerSettings(
        app_env=os.getenv("APP_ENV", "mac_dev"),
        model_mode=os.getenv("MODEL_MODE", "mock"),
        model_base_url=os.getenv("MODEL_BASE_URL", "http://localhost:8000/v1"),
        model_name=os.getenv("MODEL_NAME", "mock"),
        model_api_key=os.getenv("MODEL_API_KEY", "local-dev-key"),
        tool_server_url=os.getenv("TOOL_SERVER_URL", "http://localhost:5050"),
        agent_server_url=os.getenv("AGENT_SERVER_URL", "http://localhost:5051"),
        request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "15")),
    )
