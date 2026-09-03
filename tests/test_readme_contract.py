from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReadmeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.english = (ROOT / "README.md").read_text(encoding="utf-8")
        cls.chinese = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")

    def test_both_languages_state_scope_privacy_and_calibration_limits(self):
        for text in (self.english, self.chinese):
            with self.subTest(language="zh-CN" if text is self.chinese else "en"):
                for token in (
                    "AP Calculus AB",
                    "Precalculus",
                    "BC",
                    "AP Psychology",
                    "AP Biology",
                    "Coach",
                    "Units 1–8",
                    "session-only",
                    "clear-test-profile",
                    "provisional",
                    "insufficient_data",
                ):
                    self.assertIn(token, text)

    def test_local_state_example_selects_its_math_course_explicitly(self):
        for text in (self.english, self.chinese):
            self.assertIn("--course calc-ab", text)

    def test_verification_commands_are_kept_in_sync(self):
        commands = (
            "python ap-calculus-advisor/scripts/validate_topic_code.py --self-check --evidence-json",
            "python scripts/run_evals.py --self-check --evidence-json",
            "python -m unittest discover -s tests -v",
            "python scripts/check_release.py --evidence-json",
        )
        for command in commands:
            self.assertIn(command, self.english)
            self.assertIn(command, self.chinese)

    def test_both_languages_disclaim_official_or_secure_bank_content(self):
        self.assertIn("not an official College", self.english)
        self.assertIn("Board publication", self.english)
        self.assertIn("不是 College Board 官方出版物", self.chinese)
        for text in (self.english, self.chinese):
            self.assertIn("AP Classroom", text)
            self.assertIn("Practice Exam", text)


if __name__ == "__main__":
    unittest.main()
