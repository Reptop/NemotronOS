from __future__ import annotations

import base64
from typing import Any

import httpx

from .config import VoiceAgentSettings


class AgentClient:
    def __init__(self, settings: VoiceAgentSettings) -> None:
        self.settings = settings
        self._client = httpx.AsyncClient(timeout=self.settings.request_timeout_seconds)

    async def health(self) -> dict[str, Any]:
        response = await self._client.get(f"{self._base_url}/health")
        response.raise_for_status()
        return response.json()

    async def detect_wake_word(self, audio_bytes: bytes) -> dict[str, Any]:
        payload = {
            "audio_base64": base64.b64encode(audio_bytes).decode("ascii"),
            "mime_type": "audio/wav",
            "filename": "wake-word.wav",
        }
        response = await self._client.post(f"{self._base_url}/voice/wake-detect", json=payload)
        response.raise_for_status()
        return response.json()

    async def submit_audio_command(self, audio_bytes: bytes) -> dict[str, Any]:
        payload = {
            "audio_base64": base64.b64encode(audio_bytes).decode("ascii"),
            "mime_type": "audio/wav",
            "filename": "voice-command.wav",
        }
        response = await self._client.post(f"{self._base_url}/voice/tasks", json=payload)
        response.raise_for_status()
        return response.json()

    async def submit_command(self, command: str, source: str) -> dict[str, Any]:
        payload = {
            "transcript": command,
            "source": source,
        }
        response = await self._client.post(f"{self._base_url}/voice/text-tasks", json=payload)
        response.raise_for_status()
        return response.json()

    async def get_task(self, task_id: str) -> dict[str, Any]:
        response = await self._client.get(f"{self._base_url}/tasks/{task_id}")
        response.raise_for_status()
        return response.json()

    async def close(self) -> None:
        await self._client.aclose()

    @property
    def _base_url(self) -> str:
        return self.settings.agent_server_url.rstrip("/")
