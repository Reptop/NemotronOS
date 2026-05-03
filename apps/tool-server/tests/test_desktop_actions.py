from __future__ import annotations

import unittest
from pathlib import Path
from uuid import uuid4

from nemotronos_tools.tools.desktop_actions import (
    build_youtube_url,
    choose_youtube_thumbnail_candidate,
    find_youtube_thumbnail_candidates,
    normalize_browser_target,
    normalize_youtube_url,
    youtube_search_url,
)


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
            build_youtube_url("search", query="lofi hip hop"),
            (
                "https://www.youtube.com/results?search_query=lofi+hip+hop",
                "search",
                "lofi hip hop",
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
            self.assertGreaterEqual(target["center_x"], 220)
            self.assertLessEqual(target["center_x"], 520)
            self.assertGreaterEqual(target["center_y"], 210)
            self.assertLessEqual(target["center_y"], 400)
        finally:
            if image_path.exists():
                image_path.unlink()
            if temp_dir.exists():
                temp_dir.rmdir()


if __name__ == "__main__":
    unittest.main()
