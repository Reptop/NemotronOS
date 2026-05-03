from __future__ import annotations

import unittest
from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
