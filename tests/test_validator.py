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


PRECALCULUS_TOPICS = {
    topic.topic_num: topic.citation
    for topic in validator.filter_by_course(validator.parse_framework(), "precalculus")
}
PRECALC_P1 = "precalc-1-procedural-symbolic-fluency"
PRECALC_P2 = "precalc-2-multiple-representations"
PRECALC_P3 = "precalc-3-communication-reasoning"


class ValidatorTests(unittest.TestCase):
    def test_substantive_self_check(self):
        code, payload = validator.run_self_check()
        self.assertEqual(code, 0)
        self.assertEqual(payload["overall_status"], "pass")
        self.assertGreaterEqual(payload["self_check"]["behavior_check_count"], 27)

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

    def test_precalculus_mcq_and_all_four_frq_contracts(self):
        code, _ = validator.validate_request(
            [PRECALCULUS_TOPICS["2.8"]],
            course="precalculus",
            exam_task="multiple-choice",
            calculator_condition="calculator-not-permitted",
            representations=["analytical"],
            justification="not-required",
            mathematical_practices=[PRECALC_P1],
        )
        self.assertEqual(code, 0)

        cases = (
            (
                "function-concepts",
                "2.8",
                "calculator-required-section",
                ["analytical", "graphical", "tabular"],
                "required",
                [PRECALC_P1, PRECALC_P2, PRECALC_P3],
            ),
            (
                "modeling-non-periodic-context",
                "2.5",
                "calculator-required-section",
                ["numerical", "verbal"],
                "required",
                [PRECALC_P1, PRECALC_P3],
            ),
            (
                "modeling-periodic-context",
                "3.7",
                "calculator-not-permitted",
                ["analytical", "graphical"],
                "not-required",
                [PRECALC_P1, PRECALC_P2, PRECALC_P3],
            ),
            (
                "symbolic-manipulations",
                "3.12",
                "calculator-not-permitted",
                ["analytical"],
                "not-required",
                [PRECALC_P1],
            ),
        )
        for task_type, topic, calculator, representations, justification, practices in cases:
            with self.subTest(task_type=task_type):
                code, payload = validator.validate_request(
                    [PRECALCULUS_TOPICS[topic]],
                    course="precalculus",
                    exam_task="free-response",
                    free_response_type=task_type,
                    full_task=True,
                    calculator_condition=calculator,
                    representations=representations,
                    justification=justification,
                    mathematical_practices=practices,
                )
                self.assertEqual(code, 0, payload)
                self.assertEqual(
                    payload["content_boundary"]["free_response_type"], task_type
                )

    def test_precalculus_frq_rejects_missing_or_inconsistent_metadata(self):
        base = {
            "course": "precalculus",
            "exam_task": "free-response",
            "calculator_condition": "calculator-required-section",
            "representations": ["analytical"],
            "justification": "required",
            "mathematical_practices": [PRECALC_P1],
        }
        code, payload = validator.validate_request(
            [PRECALCULUS_TOPICS["2.8"]], **base
        )
        self.assertEqual(code, 1)
        self.assertIn(
            "requires --free-response-type",
            " ".join(payload["content_boundary"]["failures"]),
        )

        negative_cases = (
            (
                "wrong calculator",
                "3.7",
                {
                    **base,
                    "free_response_type": "modeling-periodic-context",
                    "mathematical_practices": [PRECALC_P2],
                },
            ),
            (
                "wrong Unit",
                "2.8",
                {
                    **base,
                    "free_response_type": "modeling-periodic-context",
                    "calculator_condition": "calculator-not-permitted",
                },
            ),
            (
                "wrong Practice",
                "3.12",
                {
                    **base,
                    "free_response_type": "symbolic-manipulations",
                    "calculator_condition": "calculator-not-permitted",
                    "justification": "not-required",
                    "mathematical_practices": [PRECALC_P2],
                },
            ),
        )
        for label, topic, arguments in negative_cases:
            with self.subTest(label=label):
                code, payload = validator.validate_request(
                    [PRECALCULUS_TOPICS[topic]], **arguments
                )
                self.assertEqual(code, 1, payload)

    def test_precalculus_subtype_is_forbidden_elsewhere(self):
        code, _ = validator.validate_request(
            [PRECALCULUS_TOPICS["2.8"]],
            course="precalculus",
            exam_task="multiple-choice",
            free_response_type="function-concepts",
            calculator_condition="calculator-not-permitted",
            representations=["analytical"],
            justification="not-required",
            mathematical_practices=[PRECALC_P1],
        )
        self.assertEqual(code, 1)
        code, _ = validator.validate_request(
            [CHAIN_RULE],
            course="calc-ab",
            exam_task="free-response",
            free_response_type="function-concepts",
            calculator_condition="calculator-required-section",
            representations=["analytical"],
            justification="required",
            mathematical_practices=["calc-3-justification"],
        )
        self.assertEqual(code, 1)

    def test_full_function_concepts_requires_each_fixed_component(self):
        base = {
            "course": "precalculus",
            "exam_task": "free-response",
            "free_response_type": "function-concepts",
            "full_task": True,
            "calculator_condition": "calculator-required-section",
            "representations": ["analytical", "graphical", "numerical"],
            "justification": "required",
            "mathematical_practices": [PRECALC_P1, PRECALC_P2, PRECALC_P3],
        }
        cases = (
            (
                "numerical representation",
                {**base, "representations": ["analytical", "graphical"]},
                "representation group",
            ),
            (
                "Practice 3",
                {**base, "mathematical_practices": [PRECALC_P1, PRECALC_P2]},
                "missing Mathematical Practice",
            ),
            (
                "justification",
                {**base, "justification": "not-required"},
                "requires written justification",
            ),
        )
        for label, arguments, expected_message in cases:
            with self.subTest(label=label):
                code, payload = validator.validate_request(
                    [PRECALCULUS_TOPICS["2.8"]], **arguments
                )
                self.assertEqual(code, 1, payload)
                self.assertIn(
                    expected_message,
                    " ".join(payload["content_boundary"]["failures"]),
                )

    def test_precalculus_exam_scope_rejects_supporting_unit_four(self):
        failures = validator.validate_content_boundary(
            course="precalculus",
            content_topic="2.8",
            supporting_topics=["4.10"],
            assessed_topic=True,
        )
        self.assertTrue(any("Unit 4" in failure for failure in failures))
        code, payload = validator.validate_request(
            [PRECALCULUS_TOPICS["2.8"], PRECALCULUS_TOPICS["4.10"]],
            course="precalculus",
            exam_task="multiple-choice",
            calculator_condition="calculator-not-permitted",
            representations=["analytical"],
            justification="not-required",
            mathematical_practices=[PRECALC_P1],
        )
        self.assertEqual(code, 1)
        self.assertTrue(any(row["status"] == "fail" for row in payload["results"]))

    def test_precalculus_practice_only_exam_contract(self):
        code, payload = validator.validate_request(
            [],
            course="precalculus",
            practice_only=True,
            exam_task="free-response",
            free_response_type="symbolic-manipulations",
            calculator_condition="calculator-not-permitted",
            representations=["analytical"],
            justification="not-required",
            mathematical_practices=[PRECALC_P1],
        )
        self.assertEqual(code, 0, payload)

    def test_precalculus_frq_cli_receipt(self):
        process = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--course",
                "precalculus",
                "--exam-task",
                "free-response",
                "--free-response-type",
                "symbolic-manipulations",
                "--calculator-condition",
                "calculator-not-permitted",
                "--representation",
                "analytical",
                "--justification",
                "not-required",
                "--mathematical-practice",
                PRECALC_P1,
                "--evidence-json",
                PRECALCULUS_TOPICS["3.12"],
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        payload = json.loads(process.stdout)
        self.assertEqual(payload["schema_version"], 3)
        self.assertEqual(
            payload["content_boundary"]["free_response_type"],
            "symbolic-manipulations",
        )

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
