from __future__ import annotations

import ctypes
import subprocess
import tempfile
import time
import webbrowser
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .desktop_base import DesktopBackend


ALLOWED_APPS: dict[str, str] = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "paint": "mspaint.exe",
    "mspaint": "mspaint.exe",
}

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
ULONG_PTR = wintypes.WPARAM
USER32 = ctypes.WinDLL("user32", use_last_error=True)
KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
SW_RESTORE = 9
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
VK_CONTROL = 0x11
VK_V = 0x56

USER32.OpenClipboard.argtypes = [wintypes.HWND]
USER32.OpenClipboard.restype = wintypes.BOOL
USER32.EmptyClipboard.argtypes = []
USER32.EmptyClipboard.restype = wintypes.BOOL
USER32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
USER32.SetClipboardData.restype = wintypes.HANDLE
USER32.CloseClipboard.argtypes = []
USER32.CloseClipboard.restype = wintypes.BOOL
KERNEL32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
KERNEL32.GlobalAlloc.restype = wintypes.HGLOBAL
KERNEL32.GlobalLock.argtypes = [wintypes.HGLOBAL]
KERNEL32.GlobalLock.restype = ctypes.c_void_p
KERNEL32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
KERNEL32.GlobalUnlock.restype = wintypes.BOOL


class KeyBdInput(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HardwareInput(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class InputUnion(ctypes.Union):
    _fields_ = [
        ("mi", MouseInput),
        ("ki", KeyBdInput),
        ("hi", HardwareInput),
    ]


class Input(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", InputUnion),
    ]


USER32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int]
USER32.SendInput.restype = wintypes.UINT


class WindowsDesktopBackend(DesktopBackend):
    def __init__(self) -> None:
        self._last_process_id: int | None = None
        self._last_window_title_hint: str | None = None

    def capture_screen(self) -> dict[str, Any]:
        raise NotImplementedError("The real Windows desktop backend is not implemented yet.")

    def launch_app(self, app_name: str) -> dict[str, Any]:
        normalized_name = app_name.strip().lower()
        executable = ALLOWED_APPS.get(normalized_name)
        if not executable:
            allowed = ", ".join(sorted(ALLOWED_APPS))
            raise ValueError(f"Unsupported app_name: {app_name}. Allowed apps: {allowed}.")

        launch_args = [executable]
        document_path: Path | None = None
        if normalized_name == "notepad":
            document_path = self._create_notepad_document()
            launch_args.append(str(document_path))

        process = subprocess.Popen(  # noqa: S603
            launch_args,
            close_fds=True,
        )
        self._last_process_id = process.pid
        self._last_window_title_hint = (
            document_path.stem if document_path is not None else self._title_hint_for(normalized_name)
        )
        self._wait_for_input_idle(process)
        focused = self._focus_process_window(process.pid)
        if not focused and self._last_window_title_hint:
            focused = self._focus_window_by_title_with_retry(self._last_window_title_hint)
        return {
            "mode": "windows",
            "app_name": normalized_name,
            "executable": executable,
            "pid": process.pid,
            "launched": True,
            "focused": focused,
            **({"document_path": str(document_path)} if document_path is not None else {}),
            "launched_at": datetime.now(timezone.utc).isoformat(),
        }

    def type_text(self, text: str) -> dict[str, Any]:
        if not text:
            raise ValueError("keyboard_type requires non-empty text.")

        focused = False
        if self._last_process_id is not None:
            focused = self._focus_process_window(self._last_process_id)
            if not focused and self._last_window_title_hint:
                focused = self._focus_window_by_title(self._last_window_title_hint)
            time.sleep(0.2)

        self._paste_text(text)

        return {
            "mode": "windows",
            "typed": True,
            "input_method": "clipboard_paste",
            "focused_last_app": focused,
            "characters": len(text),
            "typed_at": datetime.now(timezone.utc).isoformat(),
        }

    def open_browser(self, url: str) -> dict[str, Any]:
        opened = webbrowser.open(url, new=2, autoraise=True)
        return {
            "mode": "windows",
            "opened": opened,
            "url": url,
            "browser": "default",
            "opened_at": datetime.now(timezone.utc).isoformat(),
        }

    def _title_hint_for(self, app_name: str) -> str:
        if app_name in {"notepad"}:
            return "notepad"
        if app_name in {"calculator", "calc"}:
            return "calculator"
        if app_name in {"paint", "mspaint"}:
            return "paint"
        return app_name

    def _create_notepad_document(self) -> Path:
        document_dir = Path(tempfile.gettempdir()) / "NemotronOS" / "notepad"
        document_dir.mkdir(parents=True, exist_ok=True)
        document_path = document_dir / f"nemotronos-note-{uuid4().hex[:8]}.txt"
        document_path.write_text("", encoding="utf-8")
        return document_path

    def _focus_window_by_title_with_retry(self, title_hint: str) -> bool:
        for _ in range(8):
            if self._focus_window_by_title(title_hint):
                return True
            time.sleep(0.25)
        return False

    def _wait_for_input_idle(self, process: subprocess.Popen[Any]) -> None:
        try:
            KERNEL32.WaitForInputIdle(process._handle, 3000)  # noqa: SLF001
        except Exception:
            time.sleep(1.0)

    def _focus_process_window(self, process_id: int) -> bool:
        windows: list[int] = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def enum_window(hwnd: int, lparam: int) -> bool:
            del lparam
            window_process_id = wintypes.DWORD()
            USER32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_process_id))
            if window_process_id.value == process_id and USER32.IsWindowVisible(hwnd):
                windows.append(hwnd)
                return False
            return True

        USER32.EnumWindows(enum_window, 0)
        if not windows:
            return False

        hwnd = windows[0]
        USER32.ShowWindow(hwnd, SW_RESTORE)
        return bool(USER32.SetForegroundWindow(hwnd))

    def _focus_window_by_title(self, title_hint: str) -> bool:
        lowered_hint = title_hint.lower()
        windows: list[int] = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def enum_window(hwnd: int, lparam: int) -> bool:
            del lparam
            if not USER32.IsWindowVisible(hwnd):
                return True

            title_length = USER32.GetWindowTextLengthW(hwnd)
            if title_length <= 0:
                return True

            buffer = ctypes.create_unicode_buffer(title_length + 1)
            USER32.GetWindowTextW(hwnd, buffer, title_length + 1)
            if lowered_hint in buffer.value.lower():
                windows.append(hwnd)
                return False
            return True

        USER32.EnumWindows(enum_window, 0)
        if not windows:
            return False

        hwnd = windows[0]
        USER32.ShowWindow(hwnd, SW_RESTORE)
        return bool(USER32.SetForegroundWindow(hwnd))

    def _paste_text(self, text: str) -> None:
        self._set_clipboard_text(text)
        time.sleep(0.1)
        self._send_hotkey([VK_CONTROL, VK_V])

    def _set_clipboard_text(self, text: str) -> None:
        if not USER32.OpenClipboard(None):
            raise OSError(ctypes.get_last_error(), "OpenClipboard failed.")

        try:
            if not USER32.EmptyClipboard():
                raise OSError(ctypes.get_last_error(), "EmptyClipboard failed.")

            encoded_text = f"{text}\0".encode("utf-16-le")
            handle = KERNEL32.GlobalAlloc(GMEM_MOVEABLE, len(encoded_text))
            if not handle:
                raise OSError(ctypes.get_last_error(), "GlobalAlloc failed.")

            locked_memory = KERNEL32.GlobalLock(handle)
            if not locked_memory:
                raise OSError(ctypes.get_last_error(), "GlobalLock failed.")

            try:
                ctypes.memmove(locked_memory, encoded_text, len(encoded_text))
            finally:
                KERNEL32.GlobalUnlock(handle)

            if not USER32.SetClipboardData(CF_UNICODETEXT, handle):
                raise OSError(ctypes.get_last_error(), "SetClipboardData failed.")
        finally:
            USER32.CloseClipboard()

    def _send_hotkey(self, virtual_keys: list[int]) -> None:
        inputs: list[Input] = []
        for virtual_key in virtual_keys:
            inputs.append(self._virtual_key_input(virtual_key, key_up=False))
        for virtual_key in reversed(virtual_keys):
            inputs.append(self._virtual_key_input(virtual_key, key_up=True))

        input_array = (Input * len(inputs))(*inputs)
        sent = USER32.SendInput(len(inputs), input_array, ctypes.sizeof(Input))
        if sent != len(inputs):
            error_code = ctypes.get_last_error()
            raise OSError(error_code, "SendInput failed while sending hotkey.")

    def _virtual_key_input(self, virtual_key: int, key_up: bool) -> Input:
        return Input(
            type=INPUT_KEYBOARD,
            union=InputUnion(
                ki=KeyBdInput(
                    wVk=virtual_key,
                    wScan=0,
                    dwFlags=KEYEVENTF_KEYUP if key_up else 0,
                    time=0,
                    dwExtraInfo=0,
                )
            ),
        )
