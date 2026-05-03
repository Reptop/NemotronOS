from __future__ import annotations

import platform
import subprocess


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


def build_speaker(tts_mode: str, tts_voice: str = "") -> Speaker:
    if tts_mode == "windows_sapi":
        return WindowsSapiSpeaker(tts_voice)
    return NullSpeaker()
