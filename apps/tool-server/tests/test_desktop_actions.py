from __future__ import annotations

import unittest

from nemotronos_tools.tools.desktop_actions import normalize_browser_target


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


if __name__ == "__main__":
    unittest.main()
