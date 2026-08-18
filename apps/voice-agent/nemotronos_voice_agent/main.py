from __future__ import annotations

import argparse
import asyncio
import re
from dataclasses import replace
from threading import Lock

import httpx

from .audio import record_command_wav, record_wav_until_silence
from .client import AgentClient
from .config import VoiceAgentSettings, get_settings
from .local_wake import OpenWakeWordDetector
from .tts import build_speaker
from .wake import extract_wake_command, has_wake_word


async def run(settings: VoiceAgentSettings) -> None:
    client = AgentClient(settings)
    speaker = SerializedSpeaker(build_configured_speaker(settings))

    try:
        health = await client.health()
        print(
            "NemotronOS voice agent online "
            f"(wake_mode={settings.wake_mode}, agent={settings.agent_server_url}, "
            f"model={health.get('model_name')})."
        )

        if settings.wake_mode == "manual":
            await run_manual_loop(settings, client, speaker)
            return
        if settings.wake_mode == "whisper_poll":
            await run_whisper_poll_loop(settings, client, speaker)
            return
        if settings.wake_mode == "openwakeword":
            await run_openwakeword_loop(settings, client, speaker)
            return

        raise RuntimeError(
            f"Unsupported VOICE_AGENT_WAKE_MODE={settings.wake_mode}. "
            "Use manual, whisper_poll, or openwakeword."
        )
    finally:
        await client.close()


async def run_manual_loop(settings: VoiceAgentSettings, client: AgentClient, speaker) -> None:
    print("Manual mode. Type a command with or without a wake word, then press Enter.")
    while True:
        try:
            raw_text = await asyncio.to_thread(input, "NemotronOS> ")
        except EOFError:
            print("Manual input closed.")
            return
        command = extract_wake_command(raw_text, settings.wake_words) or raw_text.strip()
        if not command:
            continue
        await submit_command(client, speaker, command, settings, "voice_agent_manual")


async def run_whisper_poll_loop(
    settings: VoiceAgentSettings,
    client: AgentClient,
    speaker,
) -> None:
    print(
        "Listening for wake words "
        f"{', '.join(settings.wake_words)}. "
        f"Wake capture: {settings.wake_silence_seconds:g}s silence/"
        f"{settings.wake_chunk_seconds:g}s max. "
        f"Command capture: {settings.command_silence_seconds:g}s silence/"
        f"{settings.command_chunk_seconds:g}s max. "
        f"Input device: {settings.input_device or 'default'} at {settings.sample_rate}Hz. "
        "Press Ctrl+C to stop."
    )
    while True:
        try:
            detection = await listen_once(settings, client, profile="wake")
        except httpx.HTTPStatusError as exc:
            print(f"Wake detection failed: {exc.response.text}")
            await asyncio.sleep(1.0)
            continue

        transcript = detection.get("transcription", {}).get("text", "")
        command = detection.get("command", "") or extract_wake_command(
            transcript,
            settings.wake_words,
        )
        if transcript:
            print(f"Heard: {transcript}")
        if command:
            await submit_command(
                client,
                speaker,
                command,
                settings,
                "voice_agent_wake",
            )
            continue

        if not has_wake_word(transcript, settings.wake_words):
            continue

        print("Wake word heard. Listening for command...")
        await speak_async(settings.listening_acknowledgement, speaker)
        try:
            follow_up = await listen_once(settings, client, profile="command")
        except httpx.HTTPStatusError as exc:
            print(f"Command transcription failed: {exc.response.text}")
            await asyncio.sleep(1.0)
            continue

        follow_up_transcript = follow_up.get("transcription", {}).get("text", "").strip()
        follow_up_command = follow_up.get("command", "") or extract_wake_command(
            follow_up_transcript,
            settings.wake_words,
        )
        command = (follow_up_command or follow_up_transcript).strip()
        if follow_up_transcript:
            print(f"Heard command: {follow_up_transcript}")
        if not command:
            print("No command heard after wake word.")
            continue

        await submit_command(client, speaker, command, settings, "voice_agent_wake")


async def run_openwakeword_loop(
    settings: VoiceAgentSettings,
    client: AgentClient,
    speaker,
) -> None:
    detector = OpenWakeWordDetector(settings)
    print(
        "Listening locally for wake words with openWakeWord. "
        f"Threshold={settings.openwakeword_threshold:g}, "
        f"frame={settings.openwakeword_frame_ms}ms. "
        "Press Ctrl+C to stop."
    )

    while True:
        detection = await asyncio.to_thread(detector.wait_for_wake)
        print(
            "Wake detected locally: "
            f"{detection.model_name} ({detection.score:.2f}). Listening for command..."
        )
        await speak_async(settings.listening_acknowledgement, speaker)
        command_audio = await asyncio.to_thread(record_command_wav, settings)
        await submit_audio_command(
            client,
            speaker,
            command_audio,
            settings,
        )


async def listen_once(
    settings: VoiceAgentSettings,
    client: AgentClient,
    profile: str = "wake",
) -> dict:
    if profile == "command":
        max_seconds = settings.command_chunk_seconds
        silence_seconds = settings.command_silence_seconds
        min_record_seconds = settings.command_min_record_seconds
    else:
        max_seconds = settings.wake_chunk_seconds
        silence_seconds = settings.wake_silence_seconds
        min_record_seconds = settings.wake_min_record_seconds

    audio_bytes = await asyncio.to_thread(
        record_wav_until_silence,
        max_seconds,
        silence_seconds,
        min_record_seconds,
        settings.speech_threshold,
        settings.listen_block_ms,
        settings.sample_rate,
        settings.channels,
        settings.input_device,
        settings.preroll_seconds,
    )
    return await client.detect_wake_word(audio_bytes)


async def submit_command(
    client: AgentClient,
    speaker,
    command: str,
    settings: VoiceAgentSettings,
    source: str,
) -> None:
    print(f"Command: {command}")
    speak_background(command_acknowledgement(command, settings), speaker)
    response = await client.submit_command(command, source=source)
    task = response["task"]
    print(f"Submitted task {task['id']} ({task['state']}): {task['goal']}")
    await speak_for_task_outcome(client, speaker, task, settings)


async def submit_audio_command(
    client: AgentClient,
    speaker,
    audio_bytes: bytes,
    settings: VoiceAgentSettings,
) -> None:
    print("Command audio captured. Transcribing...")
    response = await client.submit_audio_command(audio_bytes)
    transcription = response["transcription"]
    task = response["task"]
    print(f"Heard command: {transcription['text']}")
    speak_background(command_acknowledgement(str(transcription["text"]), settings), speaker)
    print(f"Submitted task {task['id']} ({task['state']}): {task['goal']}")
    await speak_for_task_outcome(client, speaker, task, settings)


def command_acknowledgement(command: str, settings: VoiceAgentSettings) -> str:
    if is_spoken_result_command(command):
        return settings.accessibility_acknowledgement
    return settings.submitted_acknowledgement


def is_spoken_result_command(command: str) -> bool:
    lowered = command.lower()
    return bool(
        re.search(
            r"\b(?:what(?:'s| is)?\s+(?:on\s+)?(?:my\s+)?screen|"
            r"what\s+am\s+i\s+looking\s+at|what\s+do\s+you\s+see|"
            r"(?:describe|explain|read)\s+(?:(?:my|this|the|current|active)\s+)*"
            r"(?:screen|window|page)|"
            r"what\s+(?:window|app|application)\s+am\s+i\s+(?:on|in|using)|"
            r"what(?:'s| is)?\s+(?:this|the|my|active)\s+window|"
            r"what\s+did\s+(?:you|the\s+ai|ai|the\s+agent|the\s+assistant|"
            r"nemotron|nemotron\s*os)\s+(?:just\s+)?do|"
            r"explain\s+what\s+(?:you|the\s+ai|ai|the\s+agent|the\s+assistant|"
            r"nemotron|nemotron\s*os)\s+(?:just\s+)?did|"
            r"describe\s+what\s+(?:you|the\s+ai|ai|the\s+agent|the\s+assistant|"
            r"nemotron|nemotron\s*os)\s+(?:just\s+)?did)\b",
            lowered,
        )
    )


async def speak_for_task_outcome(
    client: AgentClient,
    speaker,
    task: dict,
    settings: VoiceAgentSettings,
) -> None:
    latest_task = await wait_for_task_outcome(
        client,
        task,
        timeout_seconds=settings.outcome_wait_seconds,
    )
    if _is_terminal_task(latest_task):
        message = spoken_outcome_message(latest_task, settings.acknowledgement)
        speak_background(message, speaker)
        return

    task_id = str(latest_task.get("id") or task.get("id") or "")
    state = str(latest_task.get("state") or task.get("state") or "unknown")
    if task_id:
        print(
            f"Task {task_id} is still {state}; waiting in the background for final voice output."
        )
    monitor_task = asyncio.create_task(
        speak_for_final_task_outcome(client, speaker, latest_task, settings)
    )
    monitor_task.add_done_callback(_consume_task_exception)


async def speak_for_final_task_outcome(
    client: AgentClient,
    speaker,
    task: dict,
    settings: VoiceAgentSettings,
) -> None:
    final_task = await wait_for_task_outcome(
        client,
        task,
        timeout_seconds=settings.final_outcome_wait_seconds,
    )
    if not _is_terminal_task(final_task):
        task_id = str(final_task.get("id") or task.get("id") or "")
        if task_id:
            print(f"Task {task_id} did not finish before the final voice wait expired.")
        return

    message = spoken_outcome_message(final_task, settings.acknowledgement)
    await speak_async(message, speaker)


def _is_terminal_task(task: dict) -> bool:
    return str(task.get("state", "")) in {
        "completed",
        "failed",
        "cancelled",
        "waiting_for_approval",
        "blocked",
    }


async def wait_for_task_outcome(
    client: AgentClient,
    task: dict,
    timeout_seconds: float = 8.0,
) -> dict:
    task_id = str(task.get("id", ""))
    if not task_id:
        return task

    deadline = asyncio.get_running_loop().time() + timeout_seconds
    latest_task = task
    while asyncio.get_running_loop().time() < deadline:
        state = str(latest_task.get("state", ""))
        if state in {"completed", "failed", "cancelled", "waiting_for_approval", "blocked"}:
            return latest_task
        await asyncio.sleep(0.35)
        latest_task = await client.get_task(task_id)
    return latest_task


def spoken_outcome_message(task: dict, success_acknowledgement: str) -> str:
    state = str(task.get("state", ""))
    if state == "completed":
        if _is_unsupported_notify_task(task):
            return "I don't know how to do that yet."
        voice_response = _voice_response_text(task)
        if voice_response:
            return voice_response
        return ""
    if state == "waiting_for_approval":
        return "I need your approval before I do that."
    if state in {"failed", "cancelled", "blocked"}:
        return "I couldn't do that."
    return "I'm working on it."


def _voice_response_text(task: dict) -> str:
    memory = task.get("memory")
    if isinstance(memory, dict):
        message = str(memory.get("voice_response_text") or "").strip()
        if message:
            return _fit_spoken_message(message)

    result = task.get("result")
    if isinstance(result, dict):
        message = str(result.get("voice_response_text") or "").strip()
        if message:
            return _fit_spoken_message(message)
        notify_result = result.get("notify_user")
        if isinstance(notify_result, dict):
            message = str(notify_result.get("message") or "").strip()
            if message and "i do not know how to do that yet" not in message.lower():
                return _fit_spoken_message(message)

    notify_message = _completed_notify_user_message(task)
    if notify_message:
        return _fit_spoken_message(notify_message)
    return ""


def _completed_notify_user_message(task: dict) -> str:
    tool_calls = task.get("tool_calls")
    if not isinstance(tool_calls, list) or len(tool_calls) != 1:
        return ""
    tool_call = tool_calls[0]
    if not isinstance(tool_call, dict) or tool_call.get("name") != "notify_user":
        return ""

    task_result = task.get("result")
    if isinstance(task_result, dict):
        message = str(task_result.get("message") or "").strip()
        if message:
            return message
    tool_result = tool_call.get("result")
    if isinstance(tool_result, dict):
        message = str(tool_result.get("message") or "").strip()
        if message:
            return message
    arguments = tool_call.get("arguments")
    if isinstance(arguments, dict):
        return str(arguments.get("message") or "").strip()
    return ""


def _fit_spoken_message(message: str, max_characters: int = 900) -> str:
    if len(message) <= max_characters:
        return message
    return f"{message[: max_characters - 22].rstrip()}... I can continue if you want."


def _is_unsupported_notify_task(task: dict) -> bool:
    tool_calls = task.get("tool_calls")
    if not isinstance(tool_calls, list) or len(tool_calls) != 1:
        return False

    tool_call = tool_calls[0]
    if not isinstance(tool_call, dict) or tool_call.get("name") != "notify_user":
        return False

    result = tool_call.get("result")
    message = ""
    if isinstance(result, dict):
        message = str(result.get("message", ""))
    arguments = tool_call.get("arguments")
    if not message and isinstance(arguments, dict):
        message = str(arguments.get("message", ""))

    lowered_message = message.lower()
    return any(
        marker in lowered_message
        for marker in (
            "does not have a richer plan",
            "no richer plan",
            "unsupported",
            "no follow-up action",
        )
    )


def speak(text: str, speaker) -> None:
    if text.strip():
        speaker.speak(text)


def speak_background(text: str, speaker) -> None:
    if not text.strip():
        return
    speak_task = asyncio.create_task(speak_async(text, speaker))
    speak_task.add_done_callback(_consume_task_exception)


async def speak_async(text: str, speaker) -> None:
    if text.strip():
        await asyncio.to_thread(speaker.speak, text)


def _consume_task_exception(task: asyncio.Task) -> None:
    try:
        task.result()
    except Exception as exc:  # noqa: BLE001
        print(f"Voice acknowledgement failed: {exc}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the NemotronOS local voice agent.")
    parser.add_argument(
        "--mode",
        choices=["manual", "whisper_poll", "openwakeword"],
        help="Override VOICE_AGENT_WAKE_MODE for this run.",
    )
    parser.add_argument(
        "--tts-mode",
        choices=["windows_sapi", "openai", "elevenlabs"],
        help="Override VOICE_AGENT_TTS_MODE for this run.",
    )
    parser.add_argument(
        "--test-tts",
        nargs="?",
        const="NemotronOS voice test. If you can hear this, text to speech is working.",
        metavar="TEXT",
        help="Speak a sample through the configured TTS backend, then exit.",
    )
    return parser.parse_args(argv)


def build_configured_speaker(settings: VoiceAgentSettings):
    return build_speaker(
        tts_mode=settings.tts_mode,
        tts_voice=settings.tts_voice,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.tts_model,
        instructions=settings.tts_instructions,
        response_format=settings.tts_response_format,
        speed=settings.tts_speed,
        timeout_seconds=settings.request_timeout_seconds,
        elevenlabs_api_key=settings.elevenlabs_api_key,
        elevenlabs_base_url=settings.elevenlabs_base_url,
        elevenlabs_voice_id=settings.elevenlabs_voice_id,
        elevenlabs_model=settings.elevenlabs_tts_model,
        elevenlabs_output_format=settings.elevenlabs_output_format,
    )


def apply_cli_overrides(
    settings: VoiceAgentSettings,
    args: argparse.Namespace,
) -> VoiceAgentSettings:
    if args.mode:
        settings = replace(settings, wake_mode=args.mode)
    if args.tts_mode:
        settings = replace(settings, tts_mode=args.tts_mode)
    return settings


class SerializedSpeaker:
    def __init__(self, speaker) -> None:
        self._speaker = speaker
        self._lock = Lock()

    def speak(self, text: str) -> None:
        with self._lock:
            self._speaker.speak(text)


def main() -> None:
    args = parse_args()
    settings = apply_cli_overrides(get_settings(), args)

    if args.test_tts is not None:
        speaker = build_configured_speaker(settings)
        speaker.speak(args.test_tts)
        return

    try:
        asyncio.run(run(settings))
    except KeyboardInterrupt:
        print("\nNemotronOS voice agent stopped.")


if __name__ == "__main__":
    main()
