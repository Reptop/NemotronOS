from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = APP_DIR.parent.parent


@dataclass(frozen=True, slots=True)
class ToolServerSettings:
    app_env: str
    tool_mode: str
    fake_windows_root: Path
    default_downloads_path: str


def _resolve_fake_windows_root(raw_value: str) -> Path:
    candidate = Path(raw_value)
    if not candidate.is_absolute():
        candidate = (APP_DIR / candidate).resolve()
    return candidate


def get_settings() -> ToolServerSettings:
    return ToolServerSettings(
        app_env=os.getenv("APP_ENV", "mac_dev"),
        tool_mode=os.getenv("TOOL_MODE", "mock_windows"),
        fake_windows_root=_resolve_fake_windows_root(
            os.getenv("FAKE_WINDOWS_ROOT", "../../sandbox/fake_windows_home")
        ),
        default_downloads_path=os.getenv(
            "DEFAULT_DOWNLOADS_PATH",
            r"C:\Users\Raed\Downloads",
        ),
    )
