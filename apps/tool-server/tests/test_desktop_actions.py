from __future__ import annotations

import unittest
from pathlib import Path
from uuid import uuid4

from nemotronos_tools.tools.desktop_actions import (
    build_youtube_url,
    choose_youtube_thumbnail_candidate,
    canvas_open_course,
    discord_send_message,
    find_youtube_thumbnail_candidates,
    normalize_browser_target,
    normalize_youtube_url,
    resolve_canvas_course,
    vscode_paste_code,
    youtube_search_url,
)
from nemotronos_tools.tools.desktop_base import DesktopBackend


class RecordingDesktopBackend(DesktopBackend):
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def capture_screen(self) -> dict:
        self.calls.append(("capture_screen", None))
        return {"image_ref": "mock://screen/latest"}

    def launch_app(self, app_name: str) -> dict:
        self.calls.append(("launch_app", app_name))
        return {"mode": "test", "app_name": app_name, "launched": True, "focused": True}

    def type_text(self, text: str) -> dict:
        self.calls.append(("type_text", text))
        return {"mode": "test", "typed": True, "characters": len(text)}

    def open_code_editor(
        self,
        code: str,
        language: str,
        open_new_window: bool,
        command: str,
    ) -> dict:
        self.calls.append(
            (
                "open_code_editor",
                {
                    "code": code,
                    "language": language,
                    "open_new_window": open_new_window,
                    "command": command,
                },
            )
        )
        return {
            "mode": "test",
            "editor": "vscode",
            "opened": True,
            "inserted": True,
            "characters": len(code),
        }

    def press_enter(self) -> dict:
        self.calls.append(("press_enter", None))
        return {"mode": "test", "pressed": "enter"}

    def press_escape(self) -> dict:
        self.calls.append(("press_escape", None))
        return {"mode": "test", "pressed": "escape"}

    def open_browser(self, url: str) -> dict:
        self.calls.append(("open_browser", url))
        return {"mode": "test", "opened": True, "url": url}

    def focus_window(self, title_hint: str) -> dict:
        self.calls.append(("focus_window", title_hint))
        return {"mode": "test", "focused": True, "title_hint": title_hint}

    def click_at(self, x: int, y: int) -> dict:
        self.calls.append(("click_at", (x, y)))
        return {"mode": "test", "clicked": True, "x": x, "y": y}

    def click_foreground_relative(self, x_ratio: float, y_ratio: float) -> dict:
        self.calls.append(("click_foreground_relative", (x_ratio, y_ratio)))
        return {
            "mode": "test",
            "clicked": True,
            "x_ratio": x_ratio,
            "y_ratio": y_ratio,
        }


class DesktopActionTests(unittest.TestCase):
    def test_normalizes_known_site_alias(self) -> None:
        self.assertEqual(
            normalize_browser_target("canvas"),
            "https://canvas.oregonstate.edu/",
        )

    def test_adds_https_to_domains(self) -> None:
        self.assertEqual(
            normalize_browser_target("example.com"),
            "https://example.com",
        )

    def test_keeps_https_urls(self) -> None:
        self.assertEqual(
            normalize_browser_target("https://github.com"),
            "https://github.com",
        )

    def test_rejects_non_web_scheme(self) -> None:
        with self.assertRaises(ValueError):
            normalize_browser_target("file:///C:/Users/Raed/secret.txt")

    def test_turns_plain_words_into_search(self) -> None:
        self.assertEqual(
            normalize_browser_target("hackathon ideas"),
            "https://www.bing.com/search?q=hackathon+ideas",
        )

    def test_builds_youtube_home_url(self) -> None:
        self.assertEqual(build_youtube_url("home"), ("https://www.youtube.com", "home", None))

    def test_builds_youtube_search_url(self) -> None:
        self.assertEqual(
            youtube_search_url("lofi hip hop"),
            "https://www.youtube.com/results?search_query=lofi+hip+hop",
        )
        self.assertEqual(
            youtube_search_url("Zajef77", prefer_video_results=True),
            "https://www.youtube.com/results?search_query=Zajef77&sp=EgIQAQ%253D%253D",
        )
        self.assertEqual(
            build_youtube_url("search", query="lofi hip hop"),
            (
                "https://www.youtube.com/results?search_query=lofi+hip+hop",
                "search",
                "lofi hip hop",
            ),
        )
        self.assertEqual(
            build_youtube_url("search", query="Zajef77", prefer_video_results=True),
            (
                "https://www.youtube.com/results?search_query=Zajef77&sp=EgIQAQ%253D%253D",
                "search",
                "Zajef77",
            ),
        )

    def test_random_youtube_action_opens_home_for_visible_clicking(self) -> None:
        self.assertEqual(
            build_youtube_url("random"),
            ("https://www.youtube.com", "random", None),
        )

    def test_accepts_youtube_video_urls_only(self) -> None:
        self.assertEqual(
            normalize_youtube_url("youtube.com/watch?v=abc123"),
            "https://youtube.com/watch?v=abc123",
        )
        with self.assertRaises(ValueError):
            normalize_youtube_url("https://example.com/watch?v=abc123")

    def test_discord_send_message_pastes_and_presses_enter(self) -> None:
        backend = RecordingDesktopBackend()

        result = discord_send_message({"text": "hello team"}, backend)

        self.assertTrue(result["sent"])
        self.assertEqual(
            backend.calls,
            [
                ("focus_window", "discord"),
                ("press_escape", None),
                ("type_text", "hello team"),
                ("press_enter", None),
            ],
        )

    def test_vscode_paste_code_opens_editor_with_generated_code(self) -> None:
        backend = RecordingDesktopBackend()

        result = vscode_paste_code(
            {"code": "print('hello')", "language": "python"},
            backend,
            "code",
        )

        self.assertTrue(result["opened"])
        self.assertEqual(result["characters"], len("print('hello')"))
        self.assertEqual(
            backend.calls,
            [
                (
                    "open_code_editor",
                    {
                        "code": "print('hello')",
                        "language": "python",
                        "open_new_window": True,
                        "command": "code",
                    },
                )
            ],
        )

    def test_resolves_canvas_course_from_alias(self) -> None:
        resolution = resolve_canvas_course(
            "intro to AI",
            "https://canvas.oregonstate.edu/",
            {"intro to ai": "/courses/12345"},
        )

        self.assertEqual(resolution["url"], "https://canvas.oregonstate.edu/courses/12345")
        self.assertEqual(resolution["resolution"], "configured_alias")

    def test_canvas_course_falls_back_to_courses_page(self) -> None:
        backend = RecordingDesktopBackend()

        result = canvas_open_course(
            {"course_query": "intro to AI"},
            backend,
            "https://canvas.oregonstate.edu",
            {},
            "",
        )

        self.assertEqual(result["url"], "https://canvas.oregonstate.edu/courses")
        self.assertEqual(result["resolution"], "courses_page_fallback")
        self.assertTrue(result["needs_course_alias"])
        self.assertEqual(
            backend.calls,
            [("open_browser", "https://canvas.oregonstate.edu/courses")],
        )

    def test_detects_visible_youtube_thumbnail_from_screenshot(self) -> None:
        from PIL import Image, ImageDraw

        temp_dir = Path.cwd() / ".tmp_tests" / f"desktop-actions-{uuid4().hex}"
        temp_dir.mkdir(parents=True, exist_ok=True)
        image_path = temp_dir / "youtube.png"
        try:
            image = Image.new("RGB", (1200, 800), "white")
            draw = ImageDraw.Draw(image)
            draw.rectangle((0, 0, 1200, 90), fill=(245, 245, 245))
            draw.rectangle((40, 90, 120, 800), fill=(250, 250, 250))
            draw.rectangle((180, 190, 500, 370), fill=(22, 68, 145))
            draw.rectangle((185, 195, 495, 365), fill=(225, 70, 52))
            draw.rectangle((560, 190, 880, 370), fill=(20, 92, 70))
            draw.rectangle((565, 195, 875, 365), fill=(60, 180, 230))
            image.save(image_path)

            candidates = find_youtube_thumbnail_candidates(
                str(image_path),
                foreground_window={"left": 0, "top": 0, "right": 1200, "bottom": 800},
                virtual_screen_origin={"x": 0, "y": 0},
            )
            target = choose_youtube_thumbnail_candidate("first_result", candidates)

            self.assertIsNotNone(target)
            assert target is not None
            self.assertGreaterEqual(target["center_y"], 180)
            self.assertLessEqual(target["center_y"], 400)
        finally:
            if image_path.exists():
                image_path.unlink()
            if temp_dir.exists():
                temp_dir.rmdir()

    def test_first_video_result_skips_channel_header_candidate(self) -> None:
        candidates = [
            {
                "left": 280,
                "top": 120,
                "right": 380,
                "bottom": 220,
                "center_x": 330,
                "center_y": 170,
                "score": 90,
            },
            {
                "left": 92,
                "top": 330,
                "right": 592,
                "bottom": 611,
                "center_x": 342,
                "center_y": 470,
                "score": 50,
            },
            {
                "left": 92,
                "top": 628,
                "right": 592,
                "bottom": 909,
                "center_x": 342,
                "center_y": 768,
                "score": 95,
            },
        ]

        target = choose_youtube_thumbnail_candidate("first_video_result", candidates)

        self.assertIsNotNone(target)
        assert target is not None
        self.assertEqual(target["top"], 330)


if __name__ == "__main__":
    unittest.main()
