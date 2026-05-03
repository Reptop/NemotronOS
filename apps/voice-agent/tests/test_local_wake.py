from __future__ import annotations

import unittest

from nemotronos_voice_agent.local_wake import _normalize_scores


class LocalWakeTests(unittest.TestCase):
    def test_normalizes_prediction_scores(self) -> None:
        self.assertEqual(
            _normalize_scores({"hey_jarvis": "0.75", "noise": None}),
            {"hey_jarvis": 0.75},
        )

    def test_returns_unknown_score_for_empty_prediction(self) -> None:
        self.assertEqual(_normalize_scores({}), {"unknown": 0.0})


if __name__ == "__main__":
    unittest.main()
