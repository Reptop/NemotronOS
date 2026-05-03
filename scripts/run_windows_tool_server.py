#!/usr/bin/env python3

from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _ensure_env_file() -> None:
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        return
    raise SystemExit("Missing .env. Complete README step 2 first, then rerun this script.")


def _wslpath_windows(path: Path) -> str:
    result = subprocess.run(
        ["wslpath", "-w", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _powershell_literal(value: str) -> str:
    return value.replace("'", "''")


def _windows_tool_python(repo_root_windows: str) -> str:
    configured = os.getenv("WINDOWS_TOOL_PYTHON", "").strip()
    if configured:
        return configured
    return f"{repo_root_windows}\\.venv-win\\Scripts\\python.exe"


def main() -> int:
    if "WSL_DISTRO_NAME" not in os.environ:
        raise SystemExit("run_windows_tool_server.py is intended to be run from WSL.")

    _ensure_env_file()
    repo_root_windows = _wslpath_windows(REPO_ROOT)
    tool_python = _windows_tool_python(repo_root_windows)
    tool_port = os.getenv("TOOL_SERVER_PORT", "5050")

    tool_command = (
        f"Set-Location -LiteralPath '{_powershell_literal(repo_root_windows)}'; "
        f"& '{_powershell_literal(tool_python)}' -m uvicorn "
        "nemotronos_tools.main:app "
        "--app-dir apps/tool-server "
        "--reload "
        f"--port {tool_port} "
        "--env-file .env"
    )
    bootstrap = (
        "$host.UI.RawUI.WindowTitle = 'NemotronOS Tool Server'; "
        f"$cmd = '{_powershell_literal(tool_command)}'; "
        "Start-Process powershell "
        "-ArgumentList @('-NoExit','-ExecutionPolicy','Bypass','-Command',$cmd)"
    )

    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        bootstrap,
    ]
    print("+ launching Windows PowerShell tool server window", flush=True)
    subprocess.run(command, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
