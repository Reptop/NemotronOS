from __future__ import annotations

from typing import Any

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
from .worker import AgentWorker


class CreateTaskRequest(BaseModel):
    goal: str


class ApproveTaskRequest(BaseModel):
    approved: bool


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
            background_tasks.add_task(current_coordinator.apply_approved_plan, task_id)

        latest_task = current_task_store.get_task(updated_task.id)
        if not latest_task:
            raise HTTPException(status_code=404, detail="Task not found after approval.")
        return latest_task.model_dump()

    @app.get("/events")
    def list_events(request: Request) -> list[dict[str, Any]]:
        current_event_log = get_event_log(request)
        return [event.model_dump() for event in current_event_log.list_events()]

    return app


app = create_app()
