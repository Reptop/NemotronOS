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
    def speak(self, text: str) -> None:
        if platform.system() != "Windows":
            print(f"NemotronOS: {text}")
            return

        escaped = text.replace("'", "''")
        command = (
            "Add-Type -AssemblyName System.Speech; "
            "$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$speaker.Speak('{escaped}')"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            check=False,
            capture_output=True,
            text=True,
        )


def build_speaker(tts_mode: str) -> Speaker:
    if tts_mode == "windows_sapi":
        return WindowsSapiSpeaker()
    return NullSpeaker()
