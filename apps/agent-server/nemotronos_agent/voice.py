from __future__ import annotations

import base64
import binascii
from typing import Any

import httpx

from .config import AgentServerSettings


MAX_AUDIO_BYTES = 25 * 1024 * 1024


class TranscriptionError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


def decode_audio_base64(audio_base64: str) -> bytes:
    if not audio_base64:
        raise ValueError("audio_base64 is required.")

    _, _, payload = audio_base64.partition(",")
    encoded_audio = payload or audio_base64
    try:
        audio_bytes = base64.b64decode(encoded_audio, validate=True)
    except binascii.Error as exc:
        raise ValueError("audio_base64 must be valid base64 audio data.") from exc

    if not audio_bytes:
        raise ValueError("audio_base64 decoded to an empty audio file.")
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise ValueError("Audio uploads are limited to 25 MB.")

    return audio_bytes


class VoiceTranscriber:
    def __init__(self, settings: AgentServerSettings) -> None:
        self.settings = settings

    async def transcribe(
        self,
        audio_base64: str,
        mime_type: str,
        filename: str,
    ) -> dict[str, Any]:
        audio_bytes = decode_audio_base64(audio_base64)
        safe_mime_type = mime_type or "audio/webm"
        safe_filename = filename or "voice-command.webm"
        provider = self.settings.transcription_provider.strip().lower()

        if provider == "elevenlabs":
            return await self._transcribe_elevenlabs(
                audio_bytes,
                safe_mime_type,
                safe_filename,
            )
        if provider in {"openai", "openai_transcription"}:
            return await self._transcribe_openai(
                audio_bytes,
                safe_mime_type,
                safe_filename,
            )
        raise RuntimeError(
            "TRANSCRIPTION_PROVIDER must be either 'openai' or 'elevenlabs'."
        )

    async def _transcribe_openai(
        self,
        audio_bytes: bytes,
        mime_type: str,
        filename: str,
    ) -> dict[str, Any]:
        if not self.settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAI transcription.")

        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            response = await client.post(
                f"{self.settings.openai_base_url.rstrip('/')}/audio/transcriptions",
                headers={"Authorization": f"Bearer {self.settings.openai_api_key}"},
                data={"model": self.settings.transcription_model},
                files={"file": (filename, audio_bytes, mime_type)},
            )
            if response.status_code >= 400:
                raise TranscriptionError(
                    _format_transcription_error(response),
                    status_code=response.status_code,
                )

        payload = response.json()
        text = str(payload.get("text", "")).strip()
        if not text:
            raise RuntimeError("Transcription returned empty text.")

        return {
            "text": text,
            "model": self.settings.transcription_model,
            "provider": "openai",
            "audio_bytes": len(audio_bytes),
        }

    async def _transcribe_elevenlabs(
        self,
        audio_bytes: bytes,
        mime_type: str,
        filename: str,
    ) -> dict[str, Any]:
        if not self.settings.elevenlabs_api_key:
            raise RuntimeError(
                "ELEVENLABS_API_KEY is required for ElevenLabs transcription."
            )

        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            response = await client.post(
                f"{self.settings.elevenlabs_base_url.rstrip('/')}/speech-to-text",
                headers={"xi-api-key": self.settings.elevenlabs_api_key},
                data={"model_id": self.settings.elevenlabs_stt_model},
                files={"file": (filename, audio_bytes, mime_type)},
            )
            if response.status_code >= 400:
                raise TranscriptionError(
                    _format_transcription_error(response, provider="ElevenLabs"),
                    status_code=response.status_code,
                )

        payload = response.json()
        text = str(payload.get("text", "")).strip()
        if not text:
            raise RuntimeError("Transcription returned empty text.")

        return {
            "text": text,
            "model": self.settings.elevenlabs_stt_model,
            "provider": "elevenlabs",
            "audio_bytes": len(audio_bytes),
        }


def _format_transcription_error(
    response: httpx.Response,
    provider: str = "OpenAI",
) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = {}

    message = ""
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = str(error.get("message") or "")
        elif isinstance(error, str):
            message = error
        elif isinstance(payload.get("detail"), str):
            message = str(payload["detail"])

    if not message:
        message = response.text.strip()
    if not message:
        message = response.reason_phrase

    return f"{provider} transcription failed ({response.status_code}): {message}"
