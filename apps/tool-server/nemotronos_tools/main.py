from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .config import ToolServerSettings, get_settings
from .registry import ToolRegistry, build_tool_registry


class ToolRequest(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="NemotronOS Tool Server", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    registry = build_tool_registry(settings)
    app.state.settings = settings
    app.state.registry = registry

    @app.get("/health")
    def health() -> dict[str, Any]:
        current_settings: ToolServerSettings = app.state.settings
        current_registry: ToolRegistry = app.state.registry
        return {
            "status": "ok",
            "tool_mode": current_settings.tool_mode,
            "fake_windows_root": str(current_settings.fake_windows_root),
            "registered_tools": current_registry.names,
        }

    @app.post("/tool")
    def run_tool(request: ToolRequest) -> dict[str, Any]:
        current_registry: ToolRegistry = app.state.registry
        try:
            result = current_registry.call(request.name, request.arguments)
        except (NotImplementedError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return {"ok": True, "name": request.name, "result": result}

    return app


app = create_app()
