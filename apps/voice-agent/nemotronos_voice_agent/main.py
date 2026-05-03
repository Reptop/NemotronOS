from __future__ import annotations

import argparse
import asyncio

import httpx

from .audio import record_wav_until_silence
from .client import AgentClient
from .config import VoiceAgentSettings, get_settings
from .tts import build_speaker
from .wake import extract_wake_command, has_wake_word


async def run(settings: VoiceAgentSettings) -> None:
    client = AgentClient(settings)
    speaker = build_speaker(settings.tts_mode)

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

    raise RuntimeError(
        f"Unsupported VOICE_AGENT_WAKE_MODE={settings.wake_mode}. "
        "Use manual or whisper_poll for this MVP slice."
    )


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
        await submit_command(client, speaker, command, settings.acknowledgement, "voice_agent_manual")


async def run_whisper_poll_loop(
    settings: VoiceAgentSettings,
    client: AgentClient,
    speaker,
) -> None:
    print(
        "Listening for wake words "
        f"{', '.join(settings.wake_words)}. "
        f"Recording each utterance until {settings.silence_seconds:g}s of silence "
        f"or {settings.chunk_seconds:g}s max. "
        "Press Ctrl+C to stop."
    )
    while True:
        try:
            detection = await listen_once(settings, client)
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
                settings.acknowledgement,
                "voice_agent_wake",
            )
            continue

        if not has_wake_word(transcript, settings.wake_words):
            continue

        print("Wake word heard. Listening for command...")
        speaker.speak(settings.listening_acknowledgement)
        try:
            follow_up = await listen_once(settings, client)
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

        await submit_command(client, speaker, command, settings.acknowledgement, "voice_agent_wake")


async def listen_once(settings: VoiceAgentSettings, client: AgentClient) -> dict:
    audio_bytes = await asyncio.to_thread(
        record_wav_until_silence,
        settings.chunk_seconds,
        settings.silence_seconds,
        settings.min_record_seconds,
        settings.speech_threshold,
        settings.listen_block_ms,
        settings.sample_rate,
        settings.channels,
        settings.input_device,
    )
    return await client.detect_wake_word(audio_bytes)


async def submit_command(
    client: AgentClient,
    speaker,
    command: str,
    acknowledgement: str,
    source: str,
) -> None:
    print(f"Command: {command}")
    speaker.speak(acknowledgement)
    response = await client.submit_command(command, source=source)
    task = response["task"]
    print(f"Submitted task {task['id']} ({task['state']}): {task['goal']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the NemotronOS local voice agent.")
    parser.add_argument(
        "--mode",
        choices=["manual", "whisper_poll"],
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
            speech_threshold=settings.speech_threshold,
            listen_block_ms=settings.listen_block_ms,
            sample_rate=settings.sample_rate,
            channels=settings.channels,
            input_device=settings.input_device,
            request_timeout_seconds=settings.request_timeout_seconds,
            tts_mode=settings.tts_mode,
            acknowledgement=settings.acknowledgement,
            listening_acknowledgement=settings.listening_acknowledgement,
        )

    try:
        asyncio.run(run(settings))
    except KeyboardInterrupt:
        print("\nNemotronOS voice agent stopped.")


if __name__ == "__main__":
    main()
