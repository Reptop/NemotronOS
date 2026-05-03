#!/usr/bin/env python3

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_DIR = REPO_ROOT / ".venv"
DASHBOARD_DIR = REPO_ROOT / "apps" / "dashboard"


def _venv_python() -> Path:
    return VENV_DIR / "bin" / "python"


def _run_checked(command: list[str], cwd: Path | None = None) -> None:
    print(f"+ {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=cwd or REPO_ROOT, check=True)


def _ensure_env_file() -> None:
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        return
    raise SystemExit("Missing .env. Complete README step 2 first, then rerun this script.")


def _ensure_wsl_environment() -> Path:
    venv_python = _venv_python()
    if not venv_python.exists():
        _run_checked([sys.executable, "-m", "venv", str(VENV_DIR)])

    _run_checked(
        [
            str(venv_python),
            "-m",
            "pip",
            "install",
            "-e",
            "apps/agent-server",
            "-e",
            "apps/voice-agent",
        ]
    )
    return venv_python


def _ensure_dashboard_dependencies() -> None:
    if (DASHBOARD_DIR / "node_modules").exists():
        return
    _run_checked(["npm", "install"], cwd=DASHBOARD_DIR)


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


def _launch_windows_tool_server() -> None:
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


def _start_process(command: list[str], cwd: Path | None = None) -> subprocess.Popen[bytes]:
    print(f"+ {' '.join(command)}", flush=True)
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    return subprocess.Popen(command, cwd=cwd or REPO_ROOT, env=env)


def _stop_processes(processes: list[tuple[str, subprocess.Popen[bytes]]]) -> None:
    for _, process in reversed(processes):
        if process.poll() is None:
            process.terminate()

    deadline = time.time() + 5
    for _, process in reversed(processes):
        if process.poll() is not None:
            continue
        timeout = max(0.0, deadline - time.time())
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()


def main() -> int:
    if "WSL_DISTRO_NAME" not in os.environ:
        raise SystemExit("run_hybrid_stack.py is intended to be run from WSL.")

    _ensure_env_file()
    venv_python = _ensure_wsl_environment()
    _ensure_dashboard_dependencies()
    _launch_windows_tool_server()

    processes: list[tuple[str, subprocess.Popen[bytes]]] = []
    try:
        processes.append(
            (
                "agent server",
                _start_process(
                    [
                        str(venv_python),
                        "-m",
                        "uvicorn",
                        "nemotronos_agent.main:app",
                        "--app-dir",
                        "apps/agent-server",
                        "--reload",
                        "--port",
                        "5051",
                        "--env-file",
                        ".env",
                    ]
                ),
            )
        )
        processes.append(
            (
                "dashboard",
                _start_process(["npm", "run", "dev"], cwd=DASHBOARD_DIR),
            )
        )

        print(
            "Hybrid stack running. Agent and dashboard are in WSL; tool server is in a Windows PowerShell window.",
            flush=True,
        )
        print(
            "Stop the WSL processes with Ctrl+C here. Close the Windows PowerShell window separately when finished.",
            flush=True,
        )

        while True:
            for name, process in processes:
                return_code = process.poll()
                if return_code is None:
                    continue
                raise RuntimeError(f"{name} exited early with code {return_code}")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping WSL processes...", flush=True)
        return 0
    finally:
        _stop_processes(processes)


if __name__ == "__main__":
    raise SystemExit(main())
