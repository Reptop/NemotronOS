from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from nemotronos_tools.tools.desktop_windows import WindowsDesktopBackend


class _FakeScreenshot:
    def __init__(self, size: tuple[int, int] = (1920, 1080)) -> None:
        self.size = size
        self.saved_path: Path | None = None
        self.saved_format: str | None = None

    def save(self, path: str | Path, format: str) -> None:
        self.saved_path = Path(path)
        self.saved_format = format
        self.saved_path.write_bytes(b"fake-png-data")


class ScreenCaptureTests(unittest.TestCase):
    def test_capture_screen_saves_png_and_returns_metadata(self) -> None:
        backend = WindowsDesktopBackend()
        fake_screenshot = _FakeScreenshot()

        screenshot_dir = Path(__file__).resolve().parent
        with (
            patch(
                "nemotronos_tools.tools.desktop_windows.ImageGrab.grab",
                return_value=fake_screenshot,
            ) as grab_mock,
            patch.object(WindowsDesktopBackend, "_ensure_windows_runtime"),
            patch.object(
                WindowsDesktopBackend,
                "_screenshot_directory",
                return_value=screenshot_dir,
            ),
        ):
            result = backend.capture_screen()

        Path(result["path"]).unlink(missing_ok=True)

        grab_mock.assert_called_once_with(all_screens=True)
        self.assertTrue(result["captured"])
        self.assertEqual(result["mode"], "windows")
        self.assertEqual(result["mime_type"], "image/png")
        self.assertEqual(result["width"], 1920)
        self.assertEqual(result["height"], 1080)
        self.assertTrue(result["path"].endswith(".png"))
        self.assertEqual(result["path"], result["image_ref"])
        self.assertIsNotNone(fake_screenshot.saved_path)
        self.assertEqual(Path(result["path"]), fake_screenshot.saved_path)
        self.assertEqual(fake_screenshot.saved_format, "PNG")

    def test_open_last_screenshot_uses_default_windows_viewer(self) -> None:
        backend = WindowsDesktopBackend()
        with TemporaryDirectory() as temp_dir:
            screenshot_dir = Path(temp_dir)
            screenshot_path = screenshot_dir / "screenshot-20260818T120000-abcd1234.png"
            screenshot_path.write_bytes(b"fake-png-data")
            backend._last_screenshot_path = screenshot_path

            with (
                patch.object(WindowsDesktopBackend, "_ensure_windows_runtime"),
                patch.object(
                    WindowsDesktopBackend,
                    "_screenshot_directory",
                    return_value=screenshot_dir,
                ),
                patch(
                    "nemotronos_tools.tools.desktop_windows.subprocess.Popen",
                    return_value=SimpleNamespace(pid=4321),
                ) as popen_mock,
            ):
                result = backend.open_last_screenshot()

        popen_mock.assert_called_once_with(
            ["explorer.exe", str(screenshot_path.resolve())],
            close_fds=True,
        )
        self.assertTrue(result["opened"])
        self.assertEqual(result["path"], str(screenshot_path.resolve()))
        self.assertEqual(result["pid"], 4321)

    def test_open_last_screenshot_reports_when_none_exists(self) -> None:
        backend = WindowsDesktopBackend()
        with TemporaryDirectory() as temp_dir:
            with (
                patch.object(WindowsDesktopBackend, "_ensure_windows_runtime"),
                patch.object(
                    WindowsDesktopBackend,
                    "_screenshot_directory",
                    return_value=Path(temp_dir),
                ),
            ):
                with self.assertRaisesRegex(ValueError, "No NemotronOS screenshot"):
                    backend.open_last_screenshot()


if __name__ == "__main__":
    unittest.main()
