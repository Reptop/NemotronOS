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

try:
    from PIL import ImageGrab
except ImportError:  # pragma: no cover - exercised in runtime environments without Pillow
    ImageGrab = None  # type: ignore[assignment]


ALLOWED_APPS: dict[str, str] = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "paint": "mspaint.exe",
    "mspaint": "mspaint.exe",
    "discord": "discord:",
}

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
ULONG_PTR = wintypes.WPARAM
IS_WINDOWS_RUNTIME = hasattr(ctypes, "WinDLL")
USER32 = ctypes.WinDLL("user32", use_last_error=True) if IS_WINDOWS_RUNTIME else None
KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True) if IS_WINDOWS_RUNTIME else None
SW_RESTORE = 9
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
VK_CONTROL = 0x11
VK_ESCAPE = 0x1B
VK_RETURN = 0x0D
VK_V = 0x56
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77

if IS_WINDOWS_RUNTIME:
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


if IS_WINDOWS_RUNTIME:
    USER32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
    USER32.SetCursorPos.restype = wintypes.BOOL
    USER32.GetForegroundWindow.argtypes = []
    USER32.GetForegroundWindow.restype = wintypes.HWND
    USER32.GetSystemMetrics.argtypes = [ctypes.c_int]
    USER32.GetSystemMetrics.restype = ctypes.c_int
    USER32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    USER32.GetWindowRect.restype = wintypes.BOOL
    USER32.mouse_event.argtypes = [
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        ULONG_PTR,
    ]
    USER32.mouse_event.restype = None
    USER32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int]
    USER32.SendInput.restype = wintypes.UINT


class WindowsDesktopBackend(DesktopBackend):
    def __init__(self) -> None:
        self._last_process_id: int | None = None
        self._last_window_title_hint: str | None = None

    def capture_screen(self) -> dict[str, Any]:
        self._ensure_windows_runtime()
        if ImageGrab is None:
            raise OSError(
                "screen_capture requires Pillow. Install tool-server dependencies first."
            )

        screenshot_dir = self._screenshot_directory()
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = screenshot_dir / f"screenshot-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{uuid4().hex[:8]}.png"

        try:
            screenshot = ImageGrab.grab(all_screens=True)
            screenshot.save(screenshot_path, format="PNG")
        except Exception as exc:  # noqa: BLE001
            raise OSError(f"screen_capture failed: {exc}") from exc

        width, height = screenshot.size
        captured_at = datetime.now(timezone.utc).isoformat()
        try:
            foreground_window = self._foreground_window_rect()
        except Exception:  # noqa: BLE001 - screenshot metadata should not block capture success
            foreground_window = None
        try:
            virtual_screen_origin = self._virtual_screen_origin()
        except Exception:  # noqa: BLE001 - fallback for non-Windows test environments
            virtual_screen_origin = {"x": 0, "y": 0}
        return {
            "mode": "windows",
            "captured": True,
            "captured_at": captured_at,
            "path": str(screenshot_path),
            "image_ref": str(screenshot_path),
            "mime_type": "image/png",
            "width": width,
            "height": height,
            "virtual_screen_origin": virtual_screen_origin,
            **({"foreground_window": foreground_window} if foreground_window else {}),
        }

    def launch_app(self, app_name: str) -> dict[str, Any]:
        self._ensure_windows_runtime()
        normalized_name = app_name.strip().lower()
        executable = ALLOWED_APPS.get(normalized_name)
        if not executable:
            allowed = ", ".join(sorted(ALLOWED_APPS))
            raise ValueError(f"Unsupported app_name: {app_name}. Allowed apps: {allowed}.")

        launch_args = [executable]
        document_path: Path | None = None
        if normalized_name == "discord":
            process = subprocess.Popen(  # noqa: S603
                ["explorer.exe", executable],
                close_fds=True,
            )
            self._last_process_id = None
            self._last_window_title_hint = "discord"
            time.sleep(1.5)
            focused = self._focus_window_by_title_with_retry("discord")
            return {
                "mode": "windows",
                "app_name": normalized_name,
                "executable": executable,
                "pid": process.pid,
                "launched": True,
                "focused": focused,
                "launched_at": datetime.now(timezone.utc).isoformat(),
            }

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
        self._ensure_windows_runtime()
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

    def press_enter(self) -> dict[str, Any]:
        self._ensure_windows_runtime()
        self._send_hotkey([VK_RETURN])
        return {
            "mode": "windows",
            "pressed": "enter",
            "pressed_at": datetime.now(timezone.utc).isoformat(),
        }

    def press_escape(self) -> dict[str, Any]:
        self._ensure_windows_runtime()
        self._send_hotkey([VK_ESCAPE])
        return {
            "mode": "windows",
            "pressed": "escape",
            "pressed_at": datetime.now(timezone.utc).isoformat(),
        }

    def open_browser(self, url: str) -> dict[str, Any]:
        self._ensure_windows_runtime()
        opened = webbrowser.open(url, new=2, autoraise=True)
        if "youtube.com" in url.lower() or "youtu.be" in url.lower():
            self._last_window_title_hint = "youtube"
        return {
            "mode": "windows",
            "opened": opened,
            "url": url,
            "browser": "default",
            "opened_at": datetime.now(timezone.utc).isoformat(),
        }

    def focus_window(self, title_hint: str) -> dict[str, Any]:
        self._ensure_windows_runtime()
        cleaned_hint = title_hint.strip()
        if not cleaned_hint:
            raise ValueError("focus_window requires title_hint.")

        focused = self._focus_window_by_title_with_retry(cleaned_hint)
        if focused:
            self._last_process_id = None
            self._last_window_title_hint = cleaned_hint
        return {
            "mode": "windows",
            "focused": focused,
            "title_hint": cleaned_hint,
            "focused_at": datetime.now(timezone.utc).isoformat(),
        }

    def click_at(self, x: int, y: int) -> dict[str, Any]:
        self._ensure_windows_runtime()
        if not USER32.SetCursorPos(int(x), int(y)):
            raise OSError(ctypes.get_last_error(), "SetCursorPos failed.")
        self._send_mouse_click()
        return {
            "mode": "windows",
            "clicked": True,
            "x": int(x),
            "y": int(y),
            "clicked_at": datetime.now(timezone.utc).isoformat(),
        }

    def click_foreground_relative(self, x_ratio: float, y_ratio: float) -> dict[str, Any]:
        self._ensure_windows_runtime()
        window_rect = self._foreground_window_rect()
        left = window_rect["left"]
        top = window_rect["top"]
        width = max(1, window_rect["right"] - left)
        height = max(1, window_rect["bottom"] - top)
        x = left + round(width * x_ratio)
        y = top + round(height * y_ratio)
        result = self.click_at(x, y)
        return {
            **result,
            "x_ratio": x_ratio,
            "y_ratio": y_ratio,
            "foreground_window": window_rect,
        }

    def _title_hint_for(self, app_name: str) -> str:
        if app_name in {"notepad"}:
            return "notepad"
        if app_name in {"calculator", "calc"}:
            return "calculator"
        if app_name in {"paint", "mspaint"}:
            return "paint"
        return app_name

    def _screenshot_directory(self) -> Path:
        return Path(tempfile.gettempdir()) / "NemotronOS" / "screenshots"

    def _ensure_windows_runtime(self) -> None:
        if not IS_WINDOWS_RUNTIME or USER32 is None or KERNEL32 is None:
            raise OSError(
                "The Windows desktop backend must run on Windows from an interactive desktop session."
            )

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

    def _foreground_window_rect(self) -> dict[str, int]:
        hwnd = USER32.GetForegroundWindow()
        if not hwnd:
            raise OSError(ctypes.get_last_error(), "GetForegroundWindow failed.")

        rect = wintypes.RECT()
        if not USER32.GetWindowRect(hwnd, ctypes.byref(rect)):
            raise OSError(ctypes.get_last_error(), "GetWindowRect failed.")

        return {
            "left": int(rect.left),
            "top": int(rect.top),
            "right": int(rect.right),
            "bottom": int(rect.bottom),
        }

    def _virtual_screen_origin(self) -> dict[str, int]:
        return {
            "x": int(USER32.GetSystemMetrics(SM_XVIRTUALSCREEN)),
            "y": int(USER32.GetSystemMetrics(SM_YVIRTUALSCREEN)),
        }

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

    def _send_mouse_click(self) -> None:
        USER32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.08)
        USER32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

    def _mouse_click_input(self, flags: int) -> Input:
        return Input(
            type=0,
            union=InputUnion(
                mi=MouseInput(
                    dx=0,
                    dy=0,
                    mouseData=0,
                    dwFlags=flags,
                    time=0,
                    dwExtraInfo=0,
                )
            ),
        )

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
