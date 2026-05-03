from __future__ import annotations

from urllib.parse import quote_plus, urlparse
from typing import Any

from .desktop_base import DesktopBackend


SITE_ALIASES = {
    "canvas": "https://canvas.instructure.com",
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "github": "https://github.com",
}


def app_launch(arguments: dict[str, Any], desktop_backend: DesktopBackend) -> dict[str, Any]:
    app_name = str(arguments.get("app_name", "")).strip()
    if not app_name:
        raise ValueError("app_launch requires app_name.")

    return desktop_backend.launch_app(app_name)


def keyboard_type(arguments: dict[str, Any], desktop_backend: DesktopBackend) -> dict[str, Any]:
    text = str(arguments.get("text", ""))
    if not text:
        raise ValueError("keyboard_type requires text.")

    return desktop_backend.type_text(text)


def browser_open(arguments: dict[str, Any], desktop_backend: DesktopBackend) -> dict[str, Any]:
    raw_target = str(arguments.get("url") or arguments.get("target") or "").strip()
    if not raw_target:
        raise ValueError("browser_open requires url.")

    url = normalize_browser_target(raw_target)
    return desktop_backend.open_browser(url)


def normalize_browser_target(target: str) -> str:
    cleaned = target.strip().strip("\"'")
    lowered = cleaned.lower()
    if lowered in SITE_ALIASES:
        return SITE_ALIASES[lowered]

    parsed = urlparse(cleaned)
    if parsed.scheme:
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("browser_open only supports http and https URLs.")
        if not parsed.netloc:
            raise ValueError("browser_open requires a valid URL host.")
        return cleaned

    if "." in cleaned and " " not in cleaned:
        return f"https://{cleaned}"

    return f"https://www.bing.com/search?q={quote_plus(cleaned)}"
