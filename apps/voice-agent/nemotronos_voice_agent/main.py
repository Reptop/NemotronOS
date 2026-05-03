from __future__ import annotations

import argparse
import asyncio

import httpx

from .audio import record_command_wav, record_wav_until_silence
from .client import AgentClient
from .config import VoiceAgentSettings, get_settings
from .local_wake import OpenWakeWordDetector
from .tts import build_speaker
from .wake import extract_wake_command, has_wake_word


async def run(settings: VoiceAgentSettings) -> None:
    client = AgentClient(settings)
    speaker = build_speaker(settings.tts_mode, settings.tts_voice)

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
    speak_background(settings.submitted_acknowledgement, speaker)
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
    speak_background(settings.submitted_acknowledgement, speaker)
    print(f"Submitted task {task['id']} ({task['state']}): {task['goal']}")
    await speak_for_task_outcome(client, speaker, task, settings)


async def speak_for_task_outcome(
    client: AgentClient,
    speaker,
    task: dict,
    settings: VoiceAgentSettings,
) -> None:
    final_task = await wait_for_task_outcome(
        client,
        task,
        timeout_seconds=settings.outcome_wait_seconds,
    )
    message = spoken_outcome_message(final_task, settings.acknowledgement)
    speak_background(message, speaker)


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
        return ""
    if state == "waiting_for_approval":
        return "I need your approval before I do that."
    if state in {"failed", "cancelled", "blocked"}:
        return "I couldn't do that."
    return "I'm working on it."


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the NemotronOS local voice agent.")
    parser.add_argument(
        "--mode",
        choices=["manual", "whisper_poll", "openwakeword"],
        help="Override VOICE_AGENT_WAKE_MODE for this run.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = get_settings()
    if args.mode:
        settings = VoiceAgentSettings(
            agent_server_url=settings.agent_server_url,
            wake_mode=args.mode,
            wake_words=settings.wake_words,
            chunk_seconds=settings.chunk_seconds,
            silence_seconds=settings.silence_seconds,
            min_record_seconds=settings.min_record_seconds,
            wake_chunk_seconds=settings.wake_chunk_seconds,
            wake_silence_seconds=settings.wake_silence_seconds,
            wake_min_record_seconds=settings.wake_min_record_seconds,
            command_chunk_seconds=settings.command_chunk_seconds,
            command_silence_seconds=settings.command_silence_seconds,
            command_min_record_seconds=settings.command_min_record_seconds,
            openwakeword_model_paths=settings.openwakeword_model_paths,
            openwakeword_threshold=settings.openwakeword_threshold,
            openwakeword_frame_ms=settings.openwakeword_frame_ms,
            speech_threshold=settings.speech_threshold,
            listen_block_ms=settings.listen_block_ms,
            preroll_seconds=settings.preroll_seconds,
            sample_rate=settings.sample_rate,
            channels=settings.channels,
            input_device=settings.input_device,
            request_timeout_seconds=settings.request_timeout_seconds,
            tts_mode=settings.tts_mode,
            tts_voice=settings.tts_voice,
            acknowledgement=settings.acknowledgement,
            submitted_acknowledgement=settings.submitted_acknowledgement,
            listening_acknowledgement=settings.listening_acknowledgement,
            outcome_wait_seconds=settings.outcome_wait_seconds,
        )

    try:
        asyncio.run(run(settings))
    except KeyboardInterrupt:
        print("\nNemotronOS voice agent stopped.")


if __name__ == "__main__":
    main()
