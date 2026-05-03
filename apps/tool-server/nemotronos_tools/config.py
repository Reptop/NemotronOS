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
    browser_automation_enabled: bool
    browser_chrome_executable: str
    browser_user_data_dir: str
    browser_profile_dir: str
    browser_headless: bool
    browser_default_timeout_ms: int
    canvas_base_url: str
    canvas_api_token: str
    canvas_course_aliases: dict[str, str]
    vscode_command: str
    gmail_client_secrets_path: str = ""
    gmail_token_path: str = ""


def _resolve_fake_windows_root(raw_value: str) -> Path:
    candidate = Path(raw_value)
    if not candidate.is_absolute():
        candidate = (APP_DIR / candidate).resolve()
    return candidate


def _resolve_project_path(raw_value: str) -> str:
    if not raw_value.strip():
        return ""
    candidate = Path(raw_value).expanduser()
    if not candidate.is_absolute():
        candidate = (PROJECT_ROOT / candidate).resolve()
    return str(candidate)


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
        browser_automation_enabled=_env_bool("BROWSER_AUTOMATION_ENABLED", True),
        browser_chrome_executable=os.getenv("BROWSER_CHROME_EXECUTABLE", "").strip(),
        browser_user_data_dir=os.getenv("BROWSER_USER_DATA_DIR", "").strip(),
        browser_profile_dir=os.getenv("BROWSER_PROFILE_DIR", "Default").strip() or "Default",
        browser_headless=_env_bool("BROWSER_HEADLESS", False),
        browser_default_timeout_ms=int(os.getenv("BROWSER_DEFAULT_TIMEOUT_MS", "10000")),
        canvas_base_url=os.getenv("CANVAS_BASE_URL", "https://canvas.oregonstate.edu"),
        canvas_api_token=os.getenv("CANVAS_API_TOKEN", ""),
        canvas_course_aliases=_canvas_course_aliases(),
        vscode_command=os.getenv("VSCODE_COMMAND", "code"),
        gmail_client_secrets_path=_resolve_project_path(
            os.getenv("GMAIL_CLIENT_SECRETS_PATH", "")
        ),
        gmail_token_path=_resolve_project_path(
            os.getenv("GMAIL_TOKEN_PATH", ".secrets/gmail_token.json")
        ),
    )


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _canvas_course_aliases() -> dict[str, str]:
    aliases: dict[str, str] = {}
    raw_aliases = os.getenv("CANVAS_COURSE_ALIASES", "")
    for raw_pair in raw_aliases.split(";"):
        if "=" not in raw_pair:
            continue
        alias, url = raw_pair.split("=", 1)
        alias = alias.strip().lower()
        url = url.strip()
        if alias and url:
            aliases[alias] = url

    intro_to_ai_url = os.getenv("CANVAS_INTRO_TO_AI_URL", "").strip()
    if intro_to_ai_url:
        for alias in (
            "intro to ai",
            "intro to artificial intelligence",
            "introduction to ai",
            "introduction to artificial intelligence",
            "ai",
        ):
            aliases.setdefault(alias, intro_to_ai_url)

    return aliases
