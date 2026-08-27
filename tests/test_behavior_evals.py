"""Offline tests for final-output evaluation and manual adjudication."""

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "run_behavior_evals.py"
CORPUS = REPO_ROOT / "evals" / "cases.jsonl"

spec = importlib.util.spec_from_file_location("run_behavior_evals", SCRIPT)
assert spec and spec.loader
runner = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runner
spec.loader.exec_module(runner)


CHAIN_RULE = "Unit 3, Topic 3.1 — The Chain Rule"


def text_case(*checks: str) -> runner.EvalCase:
    manual = tuple(
        runner.ManualCheck(f"manual-{index}", description)
        for index, description in enumerate(checks or ("Mathematics is correct.",), 1)
    )
    return runner.EvalCase(
        "text-case",
        "review",
        "explicit",
        "prompt",
        {
            "output_kind": "text",
            "topic_validation": True,
            "validation_course": "calc-ab",
            "validation_style": "instructional",
            "must_contain": ["Chain Rule"],
            "must_not_contain": [],
            "forbidden_content_fields": [],
        },
        manual,
    )


def json_case(style: str = "instructional") -> runner.EvalCase:
    contract = {
        "course": "calc-ab",
        "unit": "Unit 3",
        "topic": "3.1 The Chain Rule",
        "topic_exam_scope": "assessed",
        "type": "practice_problem",
        "difficulty": "standard",
        "style": style,
        "supporting_topics": [],
    }
    return runner.EvalCase(
        "json-case",
        "machine-output",
        "explicit",
        "prompt",
        {
            "output_kind": "json_success",
            "topic_validation": True,
            "must_contain": ["3.1 The Chain Rule"],
            "must_not_contain": ["```"],
            "forbidden_content_fields": [],
            "json_contract": contract,
        },
        (runner.ManualCheck("mathematics", "The mathematics is correct."),),
    )


def json_output(style: str = "instructional") -> dict:
    value = {
        "course": "calc-ab",
        "unit": "Unit 3",
        "topic": "3.1 The Chain Rule",
        "topic_exam_scope": "assessed",
        "type": "practice_problem",
        "difficulty": "standard",
        "style": style,
        "mathematical_practices": ["calc-1-implementing-processes"],
        "methods": [],
        "supporting_topics": [],
        "citation_validation": {
            "catalog_match": "exact",
            "automated_status": "pass",
        },
        "content": {"problem_statement": "Differentiate sin(x^2)."},
    }
    if style == "exam-oriented":
        value["exam_features"] = {
            "question_type": "free-response",
            "calculator": "not-permitted",
            "representations": ["analytical"],
            "justification": "required",
        }
    return value


def adjudication(
    case_id: str, outcomes: dict[str, str]
) -> runner.Adjudication:
    return runner.Adjudication(
        case_id,
        "reviewer@example.org",
        "2026-08-27T12:00:00+00:00",
        {
            check_id: {"id": check_id, "status": status, "evidence": "Checked work."}
            for check_id, status in outcomes.items()
        },
    )


class CorpusTests(unittest.TestCase):
    def test_corpus_is_valid_and_uses_canonical_eval_names(self):
        cases = runner.load_cases(CORPUS)
        self.assertGreaterEqual(len(cases), 17)
        raw = CORPUS.read_text(encoding="utf-8")
        self.assertNotIn('"validator_call"', raw)
        self.assertNotIn('"validator_ap_oriented"', raw)
        self.assertIn('"topic_validation"', raw)

    def test_default_mode_never_invokes_codex_or_writes_results(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(runner, "run_codex_case") as live, mock.patch.object(
            runner, "write_results"
        ) as write, redirect_stdout(stdout), redirect_stderr(stderr):
            code = runner.main([])
        self.assertEqual(code, 0)
        self.assertIn("LIVE MODEL EVAL: NOT RUN", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")
        live.assert_not_called()
        write.assert_not_called()


class FinalOutputValidationTests(unittest.TestCase):
    def test_runner_directly_validates_exact_final_text_mapping(self):
        failures, evidence = runner.evaluate_case(
            text_case(), f"Primary mapping: {CHAIN_RULE}\nApply the Chain Rule."
        )
        self.assertEqual(failures, [])
        self.assertEqual(evidence["overall_status"], "pass")

    def test_final_text_rejects_inserted_letter_and_wrong_suffix(self):
        for citation in (
            CHAIN_RULE.replace("Chain", "Ch夹ain"),
            CHAIN_RULE + " extra",
        ):
            with self.subTest(citation=citation):
                failures, evidence = runner.evaluate_case(
                    text_case(), f"{citation}\nChain Rule"
                )
                self.assertIsNone(evidence)
                self.assertTrue(
                    any("non-exact" in failure or "no complete" in failure for failure in failures)
                )

    def test_json_output_is_schema_contract_and_topic_validated(self):
        failures, evidence = runner.evaluate_case(
            json_case(), json.dumps(json_output(), ensure_ascii=False)
        )
        self.assertEqual(failures, [])
        self.assertEqual(evidence["course"], "calc-ab")

    def test_exam_oriented_requires_all_exam_features(self):
        value = json_output("exam-oriented")
        del value["exam_features"]["calculator"]
        failures, _ = runner.evaluate_case(
            json_case("exam-oriented"), json.dumps(value)
        )
        self.assertIn("$.exam_features.calculator is required", failures)

    def test_assessed_topic_is_not_treated_as_exam_oriented(self):
        value = json_output("assessed-topic")
        failures, _ = runner.evaluate_case(
            json_case("assessed-topic"), json.dumps(value)
        )
        self.assertEqual(failures, [])
        self.assertNotIn("exam_features", value)

    def test_ap_ab_integration_by_parts_cannot_pass_final_output_validation(self):
        value = json_output()
        value.update(
            {
                "unit": "Unit 6",
                "topic": "6.11 Integrating Using Integration by Parts",
                "methods": ["integration-by-parts"],
            }
        )
        case = json_case()
        contract = dict(case.expect["json_contract"])
        contract.update({"unit": value["unit"], "topic": value["topic"]})
        case = runner.EvalCase(
            case.id, case.category, case.invocation, case.prompt,
            {**case.expect, "json_contract": contract}, case.manual_checks
        )
        failures, evidence = runner.evaluate_case(case, json.dumps(value))
        self.assertTrue(any("BC-only" in failure for failure in failures))
        self.assertEqual(evidence["overall_status"], "fail")

    def test_bc_shell_method_mapped_as_disc_cannot_pass(self):
        value = json_output()
        value.update(
            {
                "course": "calc-bc",
                "unit": "Unit 8",
                "topic": "8.9 Volume with Disc Method: Revolving Around the x- or y-Axis",
                "methods": ["shell-method"],
            }
        )
        case = json_case()
        contract = {
            **case.expect["json_contract"],
            "course": "calc-bc",
            "unit": value["unit"],
            "topic": value["topic"],
        }
        case = runner.EvalCase(
            case.id, case.category, case.invocation, case.prompt,
            {**case.expect, "json_contract": contract}, case.manual_checks
        )
        failures, evidence = runner.evaluate_case(case, json.dumps(value))
        self.assertEqual(evidence["overall_status"], "pass")
        self.assertTrue(any("shell" in failure.lower() for failure in failures))

    def test_json_error_uses_machine_error_schema_without_topic_validation(self):
        case = runner.EvalCase(
            "error-case",
            "scope",
            "explicit",
            "prompt",
            {
                "output_kind": "json_error",
                "topic_validation": None,
                "must_contain": [],
                "must_not_contain": ["```"],
                "forbidden_content_fields": [],
            },
            (runner.ManualCheck("scope", "Conflict is explained."),),
        )
        message = json.dumps(
            {
                "status": "cannot_fulfill",
                "reason": "Unit 4 is not assessed.",
                "conflicts": ["exam-oriented conflicts with scope"],
                "allowed_alternatives": ["Use instructional style"],
            }
        )
        self.assertEqual(runner.evaluate_case(case, message)[0], [])


class AdjudicationTests(unittest.TestCase):
    def test_wrong_mathematics_adjudication_prevents_behavior_pass(self):
        case = text_case("Check the derivative; the displayed mathematics is wrong.")
        wrong_math = (
            f"{CHAIN_RULE}\nThe Chain Rule gives d/dx sin(x^2) = cos(x^2)."
        )
        results = runner.evaluate_responses(
            [case],
            {case.id: wrong_math},
            {case.id: adjudication(case.id, {"manual-1": "fail"})},
        )
        self.assertEqual(results[0]["contract_status"], runner.CONTRACT_PASS)
        self.assertEqual(results[0]["overall_status"], runner.FAIL)
        self.assertEqual(results[0]["manual_checks"][0]["status"], "fail")

    def test_incomplete_adjudication_cannot_produce_behavior_pass(self):
        case = text_case("Mathematics is correct.", "Explanation is complete.")
        results = runner.evaluate_responses(
            [case],
            {case.id: f"{CHAIN_RULE}\nUse the Chain Rule."},
            {case.id: adjudication(case.id, {"manual-1": "pass"})},
        )
        self.assertEqual(
            results[0]["overall_status"], runner.MANUAL_REVIEW_REQUIRED
        )
        self.assertEqual(results[0]["manual_checks"][1]["status"], "pending")

    def test_all_manual_checks_and_contract_must_pass(self):
        case = text_case("Mathematics is correct.")
        results = runner.evaluate_responses(
            [case],
            {case.id: f"{CHAIN_RULE}\nUse the Chain Rule."},
            {case.id: adjudication(case.id, {"manual-1": "pass"})},
        )
        result = results[0]
        self.assertEqual(result["overall_status"], runner.PASS)
        self.assertEqual(result["manual_checks"][0]["reviewer"], "reviewer@example.org")
        self.assertIn("reviewed_at", result["manual_checks"][0])
        self.assertIn("evidence", result["manual_checks"][0])

    def test_automated_failure_cannot_be_overridden_by_manual_pass(self):
        case = text_case("Mathematics is correct.")
        results = runner.evaluate_responses(
            [case],
            {case.id: "No mapping here, although Chain Rule is named."},
            {case.id: adjudication(case.id, {"manual-1": "pass"})},
        )
        self.assertEqual(results[0]["contract_status"], runner.FAIL)
        self.assertEqual(results[0]["overall_status"], runner.FAIL)

    def test_adjudication_file_requires_trace_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "adjudications.jsonl"
            path.write_text(
                json.dumps(
                    {
                        "case_id": "text-case",
                        "reviewer": "reviewer",
                        "reviewed_at": "2026-08-27T12:00:00",
                        "checks": [],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(runner.RunnerError):
                runner.load_adjudications(path)


class OfflineReplayAndEventTests(unittest.TestCase):
    def test_saved_responses_and_adjudications_close_the_loop_without_codex(self):
        case = text_case("Mathematics is correct.")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            corpus = root / "cases.jsonl"
            responses = root / "responses.jsonl"
            adjudications = root / "adjudications.jsonl"
            output_dir = root / "results"
            corpus.write_text(
                json.dumps(
                    {
                        "id": case.id,
                        "category": case.category,
                        "invocation": case.invocation,
                        "prompt": case.prompt,
                        "expect": case.expect,
                        "manual_checks": [
                            {"id": "manual-1", "description": "Mathematics is correct."}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            responses.write_text(
                json.dumps(
                    {"case_id": case.id, "final_output": f"{CHAIN_RULE}\nUse the Chain Rule."}
                ),
                encoding="utf-8",
            )
            adjudications.write_text(
                json.dumps(
                    {
                        "case_id": case.id,
                        "reviewer": "reviewer",
                        "reviewed_at": "2026-08-27T12:00:00Z",
                        "checks": [
                            {"id": "manual-1", "status": "pass", "evidence": "Checked."}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(runner, "run_codex_case") as live:
                code = runner.main(
                    [
                        "--corpus", str(corpus),
                        "--responses", str(responses),
                        "--adjudications", str(adjudications),
                        "--output-dir", str(output_dir),
                    ]
                )
            live.assert_not_called()
            self.assertEqual(code, 0)
            payload = json.loads(next(output_dir.glob("*.json")).read_text(encoding="utf-8"))
            self.assertEqual(payload["overall_status"], runner.PASS)

    def test_only_final_agent_message_is_used_not_command_events(self):
        events = [
            {
                "type": "item.completed",
                "item": {
                    "type": "command_execution",
                    "command": "python scripts/validate_topic_code.py",
                    "aggregated_output": "fabricated pass",
                },
            },
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": "first"},
            },
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": "final"},
            },
        ]
        self.assertEqual(runner.extract_final_message(events), "final")


if __name__ == "__main__":
    unittest.main()
