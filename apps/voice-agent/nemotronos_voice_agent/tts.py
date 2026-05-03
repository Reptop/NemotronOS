from __future__ import annotations

import os
import platform
import subprocess
import tempfile
from pathlib import Path

import httpx


class Speaker:
    def speak(self, text: str) -> None:
        raise NotImplementedError


class NullSpeaker(Speaker):
    def speak(self, text: str) -> None:
        print(f"NemotronOS: {text}")


class WindowsSapiSpeaker(Speaker):
    def __init__(self, voice_name: str = "") -> None:
        self.voice_name = voice_name.strip()

    def speak(self, text: str) -> None:
        if platform.system() != "Windows":
            print(f"NemotronOS: {text}")
            return

        escaped = text.replace("'", "''")
        escaped_voice = self.voice_name.replace("'", "''")
        select_voice_command = ""
        if escaped_voice:
            select_voice_command = (
                "$voice = $speaker.GetInstalledVoices() | "
                f"Where-Object {{ $_.VoiceInfo.Name -eq '{escaped_voice}' }} | "
                "Select-Object -First 1; "
                "if ($voice) { $speaker.SelectVoice($voice.VoiceInfo.Name) }; "
            )
        command = (
            "Add-Type -AssemblyName System.Speech; "
            "$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"{select_voice_command}"
            f"$speaker.Speak('{escaped}')"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            check=False,
            capture_output=True,
            text=True,
        )


class OpenAITTSSpeaker(Speaker):
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        voice: str,
        instructions: str,
        response_format: str,
        speed: float,
        timeout_seconds: float,
        fallback: Speaker,
    ) -> None:
        self.api_key = api_key.strip()
        self.base_url = base_url.strip().rstrip("/") or "https://api.openai.com/v1"
        self.model = model.strip() or "gpt-4o-mini-tts"
        self.voice = voice.strip() or "marin"
        self.instructions = instructions.strip()
        self.response_format = response_format.strip().lower() or "mp3"
        self.speed = max(0.25, min(float(speed), 4.0))
        self.timeout_seconds = timeout_seconds
        self.fallback = fallback

    def speak(self, text: str) -> None:
        cleaned_text = text.strip()
        if not cleaned_text:
            return
        if not self.api_key:
            self.fallback.speak(cleaned_text)
            return

        try:
            audio_path = self._create_speech_file(cleaned_text)
            try:
                self._play_audio(audio_path)
            finally:
                audio_path.unlink(missing_ok=True)
        except Exception as exc:  # noqa: BLE001 - speech should not crash the voice loop
            print(f"OpenAI TTS failed; falling back to Windows voice: {exc}")
            self.fallback.speak(cleaned_text)

    def _create_speech_file(self, text: str) -> Path:
        payload: dict[str, object] = {
            "model": self.model,
            "voice": self.voice,
            "input": text[:4096],
            "response_format": self.response_format,
        }
        if self.instructions and self.model.startswith("gpt-4o-mini-tts"):
            payload["instructions"] = self.instructions
        if self.speed != 1.0:
            payload["speed"] = self.speed

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(
                f"{self.base_url}/audio/speech",
                headers=headers,
                json=payload,
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = exc.response.text.strip()
                if len(detail) > 500:
                    detail = f"{detail[:497]}..."
                message = f"OpenAI TTS HTTP {exc.response.status_code}"
                if detail:
                    message = f"{message}: {detail}"
                raise RuntimeError(message) from exc

        if not response.content:
            raise RuntimeError("OpenAI TTS returned empty audio.")

        suffix = _audio_suffix(response, self.response_format)
        audio_dir = Path(tempfile.gettempdir()) / "NemotronOS" / "tts"
        audio_dir.mkdir(parents=True, exist_ok=True)
        fd, raw_path = tempfile.mkstemp(prefix="speech-", suffix=suffix, dir=audio_dir)
        os.close(fd)
        audio_path = Path(raw_path)
        audio_path.write_bytes(response.content)
        return audio_path

    def _play_audio(self, audio_path: Path) -> None:
        if platform.system() != "Windows":
            print(f"NemotronOS TTS audio saved to {audio_path}")
            return

        if audio_path.suffix.lower() == ".pcm":
            raise RuntimeError(
                "OpenAI TTS playback cannot play raw PCM directly; use mp3 or wav."
            )

        escaped_uri = audio_path.resolve().as_uri().replace("'", "''")
        command = (
            "$ErrorActionPreference = 'Stop'; "
            "Add-Type -AssemblyName PresentationCore; "
            "$player = New-Object System.Windows.Media.MediaPlayer; "
            f"$player.Open([Uri]::new('{escaped_uri}')); "
            "$player.Play(); "
            "$deadline = (Get-Date).AddSeconds(30); "
            "while (-not $player.NaturalDuration.HasTimeSpan -and (Get-Date) -lt $deadline) { "
            "Start-Sleep -Milliseconds 50 }; "
            "$durationMs = 3000; "
            "if ($player.NaturalDuration.HasTimeSpan) { "
            "$durationMs = [Math]::Min([int]$player.NaturalDuration.TimeSpan.TotalMilliseconds + 250, 30000) "
            "}; "
            "Start-Sleep -Milliseconds $durationMs; "
            "$player.Stop(); "
            "$player.Close()"
        )
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Sta", "-Command", command],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise RuntimeError(f"Windows audio playback failed: {detail}")


def build_speaker(
    tts_mode: str,
    tts_voice: str = "",
    api_key: str = "",
    base_url: str = "https://api.openai.com/v1",
    model: str = "gpt-4o-mini-tts",
    instructions: str = "",
    response_format: str = "mp3",
    speed: float = 1.0,
    timeout_seconds: float = 30.0,
) -> Speaker:
    normalized_mode = tts_mode.strip().lower()
    fallback = WindowsSapiSpeaker("") if platform.system() == "Windows" else NullSpeaker()
    if normalized_mode in {"openai", "openai_tts"}:
        return OpenAITTSSpeaker(
            api_key=api_key,
            base_url=base_url,
            model=model,
            voice=tts_voice,
            instructions=instructions,
            response_format=response_format,
            speed=speed,
            timeout_seconds=timeout_seconds,
            fallback=fallback,
        )
    if normalized_mode == "windows_sapi":
        return WindowsSapiSpeaker(tts_voice)
    return NullSpeaker()


def _audio_suffix(response: httpx.Response, requested_format: str) -> str:
    content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
    suffix_by_content_type = {
        "audio/aac": ".aac",
        "audio/flac": ".flac",
        "audio/mpeg": ".mp3",
        "audio/mp3": ".mp3",
        "audio/ogg": ".opus",
        "audio/opus": ".opus",
        "audio/pcm": ".pcm",
        "audio/wav": ".wav",
        "audio/wave": ".wav",
        "audio/x-wav": ".wav",
    }
    suffix = suffix_by_content_type.get(content_type)
    if suffix:
        return suffix
    cleaned_format = requested_format.strip().lower().lstrip(".") or "mp3"
    return f".{cleaned_format}"
