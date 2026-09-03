from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "ap-calculus-advisor"
SCRIPT = SKILL_ROOT / "scripts" / "validate_topic_code.py"
SPEC = importlib.util.spec_from_file_location("validate_topic_code", SCRIPT)
assert SPEC and SPEC.loader
validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)

CHAIN_RULE = "Unit 3, Topic 3.1 — The Chain Rule"


class ValidatorTests(unittest.TestCase):
    def test_substantive_self_check(self):
        code, payload = validator.run_self_check()
        self.assertEqual(code, 0)
        self.assertEqual(payload["overall_status"], "pass")
        self.assertGreaterEqual(payload["self_check"]["behavior_check_count"], 15)

    def test_exact_topic_positive_and_suffix_negative(self):
        code, _ = validator.validate_request([CHAIN_RULE], course="calc-ab")
        self.assertEqual(code, 0)
        code, payload = validator.validate_request([CHAIN_RULE + " (official)"], course="calc-ab")
        self.assertEqual(code, 1)
        self.assertEqual(payload["topic_status"], "not-established")

    def test_bc_only_topic_and_high_risk_method_fail_for_ab(self):
        code, _ = validator.validate_request(
            ["Unit 7, Topic 7.5 — Approximating Solutions Using Euler's Method"],
            course="calc-ab",
        )
        self.assertEqual(code, 1)
        code, payload = validator.validate_request(
            ["Unit 6, Topic 6.14 — Selecting Techniques for Antidifferentiation"],
            course="calc-ab",
            methods=["integration-by-parts"],
        )
        self.assertEqual(code, 1)
        self.assertTrue(payload["content_boundary"]["failures"])

    def test_practice_only_positive_and_negative(self):
        code, _ = validator.validate_request(
            [],
            course="calc-ab",
            practice_only=True,
            mathematical_practices=["calc-3-justification"],
        )
        self.assertEqual(code, 0)
        code, _ = validator.validate_request(
            [],
            course="calc-ab",
            practice_only=True,
            mathematical_practices=["precalc-3-communication-reasoning"],
        )
        self.assertEqual(code, 1)

    def test_assessment_contract_positive_and_negative(self):
        code, _ = validator.validate_request(
            [CHAIN_RULE],
            course="calc-ab",
            exam_task="free-response",
            full_task=True,
            calculator_condition="calculator-required-section",
            representations=["analytical", "verbal"],
            justification="required",
            mathematical_practices=["calc-3-justification", "calc-4-communication-notation"],
        )
        self.assertEqual(code, 0)
        code, payload = validator.validate_request(
            [CHAIN_RULE],
            course="calc-ab",
            exam_task="multiple-choice",
            calculator_condition="calculator-not-permitted",
            representations=["analytical"],
            justification="required",
            mathematical_practices=["calc-4-communication-notation"],
        )
        self.assertEqual(code, 1)
        self.assertGreaterEqual(len(payload["content_boundary"]["failures"]), 2)

    def test_literal_legacy_alias_is_accepted_but_never_emitted(self):
        process = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--course",
                "calc-ab",
                "--ap-oriented",
                "--evidence-json",
                CHAIN_RULE,
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        payload = json.loads(process.stdout)
        self.assertEqual(payload["overall_status"], "pass")
        self.assertNotIn("ap-oriented", process.stdout)

    def test_absolute_script_path_runs_from_directory_with_spaces(self):
        with tempfile.TemporaryDirectory(prefix="advisor path with spaces ") as temporary:
            copied_root = Path(temporary) / "skill root with spaces"
            (copied_root / "scripts").mkdir(parents=True)
            (copied_root / "references").mkdir()
            copied_script = copied_root / "scripts" / SCRIPT.name
            shutil.copy2(SCRIPT, copied_script)
            shutil.copy2(SKILL_ROOT / "references" / "ap-calc-framework.md", copied_root / "references")
            shutil.copy2(SKILL_ROOT / "references" / "ap-content-boundaries.json", copied_root / "references")
            process = subprocess.run(
                [sys.executable, str(copied_script), "--self-check", "--evidence-json"],
                cwd=temporary,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout)["overall_status"], "pass")


if __name__ == "__main__":
    unittest.main()
