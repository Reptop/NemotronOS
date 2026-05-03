#!/usr/bin/env python3

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_DIR = REPO_ROOT / ".venv"
DASHBOARD_DIR = REPO_ROOT / "apps" / "dashboard"


def _venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def _npm_command() -> str:
    return "npm.cmd" if os.name == "nt" else "npm"


def _run_checked(command: list[str], cwd: Path | None = None) -> None:
    print(f"+ {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=cwd or REPO_ROOT, check=True)


def _ensure_env_file() -> None:
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        return
    raise SystemExit("Missing .env. Complete README step 2 first, then rerun this script.")


def _ensure_python_environment() -> Path:
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
            "apps/tool-server",
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
    _run_checked([_npm_command(), "install"], cwd=DASHBOARD_DIR)


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
    _ensure_env_file()
    venv_python = _ensure_python_environment()
    _ensure_dashboard_dependencies()

    processes: list[tuple[str, subprocess.Popen[bytes]]] = []
    try:
        processes.append(
            (
                "tool server",
                _start_process(
                    [
                        str(venv_python),
                        "-m",
                        "uvicorn",
                        "nemotronos_tools.main:app",
                        "--app-dir",
                        "apps/tool-server",
                        "--reload",
                        "--port",
                        "5050",
                        "--env-file",
                        ".env",
                    ]
                ),
            )
        )
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
                _start_process([_npm_command(), "run", "dev"], cwd=DASHBOARD_DIR),
            )
        )

        print("Local stack running. Press Ctrl+C to stop all processes.", flush=True)

        while True:
            for name, process in processes:
                return_code = process.poll()
                if return_code is None:
                    continue
                if name == "dashboard":
                    return return_code
                raise RuntimeError(f"{name} exited early with code {return_code}")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping local stack...", flush=True)
        return 0
    finally:
        _stop_processes(processes)


if __name__ == "__main__":
    raise SystemExit(main())
