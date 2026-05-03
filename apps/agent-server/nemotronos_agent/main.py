from __future__ import annotations

import re
from typing import Any

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import AgentServerSettings, get_settings
from .coordinator import AgentCoordinator
from .event_log import EventLog
from .model_client import build_model_client
from .policy import PolicyEngine
from .task_store import TaskStore
from .tool_registry import ToolRegistry
from .voice import TranscriptionError, VoiceTranscriber
from .worker import AgentWorker


WAKE_WORDS = ("jarvis", "computer")
WAKE_COMMAND_SEPARATOR_CHARS = " \t\n\r,.:;-?!\"'()[]{}"


class CreateTaskRequest(BaseModel):
    goal: str


class ApproveTaskRequest(BaseModel):
    approved: bool


class VoiceCommandRequest(BaseModel):
    audio_base64: str
    mime_type: str = "audio/webm"
    filename: str = "voice-command.webm"


class VoiceTextCommandRequest(BaseModel):
    transcript: str
    source: str = "browser_speech"


def extract_voice_dictation_text(transcript: str) -> str | None:
    lowered = transcript.lower()
    markers = (
        "word for word",
        "verbatim",
        "exactly",
    )
    for marker in markers:
        marker_index = lowered.find(marker)
        if marker_index >= 0:
            text = transcript[marker_index + len(marker) :].lstrip(" .,:;-")
            if text:
                return text

    command_match = re.search(
        r"\b(?:type|write|enter|paste)\b(?:\s+(?:in|out|down|up|this|that|the|text|note))*"
        r"\s*[:,-]?\s+(.+)$",
        transcript,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if command_match:
        text = command_match.group(1).strip(" \t\n\r\"'")
        if text:
            return text
    return None


def extract_wake_command(transcript: str) -> str | None:
    normalized_transcript = transcript.strip()
    lowered_transcript = normalized_transcript.lower()
    for wake_word in WAKE_WORDS:
        index = lowered_transcript.find(wake_word)
        if index < 0:
            continue

        before = lowered_transcript[index - 1] if index > 0 else " "
        after_index = index + len(wake_word)
        after = lowered_transcript[after_index] if after_index < len(lowered_transcript) else " "
        if before.isalnum() or after.isalnum():
            continue

        command = normalized_transcript[after_index:].lstrip(WAKE_COMMAND_SEPARATOR_CHARS)
        if command.strip(WAKE_COMMAND_SEPARATOR_CHARS):
            return command
    return None


def get_coordinator(request: Request) -> AgentCoordinator:
    return request.app.state.coordinator


def get_task_store(request: Request) -> TaskStore:
    return request.app.state.task_store


def get_event_log(request: Request) -> EventLog:
    return request.app.state.event_log


def create_app() -> FastAPI:
    settings = get_settings()
    task_store = TaskStore()
    event_log = EventLog()
    tool_registry = ToolRegistry()
    policy_engine = PolicyEngine()
    model_client = build_model_client(settings)
    voice_transcriber = VoiceTranscriber(settings)
    worker = AgentWorker(settings=settings, task_store=task_store, event_log=event_log)
    coordinator = AgentCoordinator(
        task_store=task_store,
        event_log=event_log,
        tool_registry=tool_registry,
        policy_engine=policy_engine,
        model_client=model_client,
        worker=worker,
    )

    app = FastAPI(title="NemotronOS Agent Server", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.settings = settings
    app.state.task_store = task_store
    app.state.event_log = event_log
    app.state.coordinator = coordinator
    app.state.worker = worker
    app.state.voice_transcriber = voice_transcriber

    @app.get("/health")
    async def health(request: Request) -> dict[str, Any]:
        current_settings: AgentServerSettings = request.app.state.settings
        current_worker: AgentWorker = request.app.state.worker
        tool_health = await current_worker.fetch_tool_server_health()
        return {
            "status": "ok",
            "app_env": current_settings.app_env,
            "model_mode": current_settings.model_mode,
            "model_name": current_settings.model_name,
            "transcription_model": current_settings.transcription_model,
            "voice_enabled": bool(current_settings.openai_api_key),
            "tool_server_url": current_settings.tool_server_url,
            "tool_server": tool_health,
        }

    @app.post("/tasks")
    async def create_task(
        payload: CreateTaskRequest,
        background_tasks: BackgroundTasks,
        request: Request,
    ) -> dict[str, Any]:
        if not payload.goal.strip():
            raise HTTPException(status_code=400, detail="Goal is required.")

        current_task_store = get_task_store(request)
        current_event_log = get_event_log(request)
        current_coordinator = get_coordinator(request)

        task = current_task_store.create_task(goal=payload.goal.strip())
        current_event_log.add_event("task_created", task_id=task.id, goal=task.goal)
        background_tasks.add_task(current_coordinator.process_task, task.id)
        return task.model_dump()

    @app.post("/voice/tasks")
    async def create_voice_task(
        payload: VoiceCommandRequest,
        background_tasks: BackgroundTasks,
        request: Request,
    ) -> dict[str, Any]:
        current_task_store = get_task_store(request)
        current_event_log = get_event_log(request)
        current_coordinator = get_coordinator(request)
        current_transcriber: VoiceTranscriber = request.app.state.voice_transcriber

        try:
            transcription = await current_transcriber.transcribe(
                payload.audio_base64,
                payload.mime_type,
                payload.filename,
            )
        except ValueError as exc:
            current_event_log.add_event("voice_transcription_failed", error=str(exc))
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except TranscriptionError as exc:
            current_event_log.add_event(
                "voice_transcription_failed",
                error=str(exc),
                status_code=exc.status_code,
            )
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        except httpx.HTTPError as exc:
            detail = f"Transcription request failed before OpenAI returned a response: {exc}"
            current_event_log.add_event("voice_transcription_failed", error=detail)
            raise HTTPException(status_code=502, detail=detail) from exc
        except RuntimeError as exc:
            current_event_log.add_event("voice_transcription_failed", error=str(exc))
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        task = current_task_store.create_task(goal=transcription["text"])
        dictation_text = extract_voice_dictation_text(transcription["text"])
        current_task_store.update_task(
            task.id,
            memory={
                "voice_transcript": transcription["text"],
                "voice_transcription_model": transcription["model"],
                **(
                    {"voice_dictation_text": dictation_text}
                    if dictation_text is not None
                    else {}
                ),
            },
        )
        task = current_task_store.get_task(task.id) or task
        current_event_log.add_event(
            "voice_transcribed",
            task_id=task.id,
            text=transcription["text"],
            model=transcription["model"],
            audio_bytes=transcription["audio_bytes"],
        )
        current_event_log.add_event("task_created", task_id=task.id, goal=task.goal)
        background_tasks.add_task(current_coordinator.process_task, task.id)
        return {
            "task": task.model_dump(),
            "transcription": transcription,
        }

    @app.post("/voice/text-tasks")
    async def create_voice_text_task(
        payload: VoiceTextCommandRequest,
        background_tasks: BackgroundTasks,
        request: Request,
    ) -> dict[str, Any]:
        transcript = payload.transcript.strip()
        if not transcript:
            raise HTTPException(status_code=400, detail="Transcript is required.")

        current_task_store = get_task_store(request)
        current_event_log = get_event_log(request)
        current_coordinator = get_coordinator(request)

        task = current_task_store.create_task(goal=transcript)
        dictation_text = extract_voice_dictation_text(transcript)
        current_task_store.update_task(
            task.id,
            memory={
                "voice_transcript": transcript,
                "voice_transcription_model": payload.source,
                **(
                    {"voice_dictation_text": dictation_text}
                    if dictation_text is not None
                    else {}
                ),
            },
        )
        task = current_task_store.get_task(task.id) or task
        current_event_log.add_event(
            "voice_transcribed",
            task_id=task.id,
            text=transcript,
            model=payload.source,
            audio_bytes=0,
        )
        current_event_log.add_event("task_created", task_id=task.id, goal=task.goal)
        background_tasks.add_task(current_coordinator.process_task, task.id)
        return {
            "task": task.model_dump(),
            "transcription": {
                "text": transcript,
                "model": payload.source,
                "audio_bytes": 0,
            },
        }

    @app.post("/voice/wake-detect")
    async def detect_wake_word(
        payload: VoiceCommandRequest,
        request: Request,
    ) -> dict[str, Any]:
        current_event_log = get_event_log(request)
        current_transcriber: VoiceTranscriber = request.app.state.voice_transcriber

        try:
            transcription = await current_transcriber.transcribe(
                payload.audio_base64,
                payload.mime_type,
                payload.filename,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except TranscriptionError as exc:
            current_event_log.add_event(
                "wake_word_detection_failed",
                error=str(exc),
                status_code=exc.status_code,
            )
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        except RuntimeError as exc:
            if "empty text" in str(exc).lower():
                return {
                    "detected": False,
                    "command": "",
                    "transcription": {
                        "text": "",
                        "model": request.app.state.settings.transcription_model,
                        "audio_bytes": 0,
                    },
                }
            current_event_log.add_event("wake_word_detection_failed", error=str(exc))
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except httpx.HTTPError as exc:
            detail = f"Wake word transcription request failed: {exc}"
            current_event_log.add_event("wake_word_detection_failed", error=detail)
            raise HTTPException(status_code=502, detail=detail) from exc

        command = extract_wake_command(transcription["text"])
        if command:
            current_event_log.add_event(
                "wake_word_detected",
                text=transcription["text"],
                command=command,
                model=transcription["model"],
                audio_bytes=transcription["audio_bytes"],
            )

        return {
            "detected": command is not None,
            "command": command or "",
            "transcription": transcription,
        }

    @app.get("/tasks")
    def list_tasks(request: Request) -> list[dict[str, Any]]:
        current_task_store = get_task_store(request)
        return [task.model_dump() for task in current_task_store.list_tasks()]

    @app.get("/tasks/{task_id}")
    def get_task(task_id: str, request: Request) -> dict[str, Any]:
        current_task_store = get_task_store(request)
        task = current_task_store.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found.")
        return task.model_dump()

    @app.post("/tasks/{task_id}/approve")
    async def approve_task(
        task_id: str,
        payload: ApproveTaskRequest,
        background_tasks: BackgroundTasks,
        request: Request,
    ) -> dict[str, Any]:
        current_coordinator = get_coordinator(request)
        current_task_store = get_task_store(request)
        try:
            updated_task = await current_coordinator.approve_task(task_id, payload.approved)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if payload.approved:
            background_tasks.add_task(current_coordinator.run_approved_action, task_id)

        latest_task = current_task_store.get_task(updated_task.id)
        if not latest_task:
            raise HTTPException(status_code=404, detail="Task not found after approval.")
        return latest_task.model_dump()

    @app.get("/events")
    def list_events(request: Request) -> list[dict[str, Any]]:
        current_event_log = get_event_log(request)
        return [event.model_dump() for event in current_event_log.list_events()]

    @app.post("/demo/reset-downloads")
    async def reset_demo_downloads(request: Request) -> dict[str, Any]:
        current_worker: AgentWorker = request.app.state.worker
        try:
            result = await current_worker.reset_demo_downloads()
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        return {"ok": True, "result": result}

    return app


app = create_app()
