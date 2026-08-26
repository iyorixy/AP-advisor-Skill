#!/usr/bin/env python3
"""Offline tests for the AP Advisor behavioral-evaluation infrastructure."""

import importlib.util
import io
import json
import os
import shlex
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "run_behavior_evals.py"
CORPUS_PATH = REPO_ROOT / "evals" / "cases.jsonl"
ERROR_SCHEMA_PATH = REPO_ROOT / "references" / "machine-error-schema.json"

spec = importlib.util.spec_from_file_location("run_behavior_evals", SCRIPT_PATH)
rbe = importlib.util.module_from_spec(spec)
sys.modules["run_behavior_evals"] = rbe
spec.loader.exec_module(rbe)


NO_VALIDATOR = rbe.ValidatorObservation(())


def validator_events(
    *,
    course: str,
    citations: list[tuple[str, str]],
    ap_oriented: bool = False,
    exit_code: int = 0,
    overall_status: str | None = None,
    command: str | None = None,
    evidence_overrides: dict | None = None,
    item_id: str = "validator-1",
) -> list[dict]:
    citation_texts = [citation for citation, _scope in citations]
    if command is None:
        parts = [
            "python",
            "scripts/validate_topic_code.py",
            "--course",
            course,
        ]
        if ap_oriented:
            parts.append("--ap-oriented")
        parts.append("--evidence-json")
        parts.extend(json.dumps(citation, ensure_ascii=False) for citation in citation_texts)
        command = " ".join(parts)
    status = overall_status or ({0: "pass", 1: "fail", 2: "error"}.get(exit_code, "error"))
    results = [
        {
            "input": citation,
            "status": "pass",
            "citation": citation,
            "topic_exam_scope": scope,
        }
        for citation, scope in citations
    ]
    if status == "fail" and results:
        results[-1] = {
            "input": results[-1]["input"],
            "status": "fail",
            "message": "no exact match",
        }
    evidence = {
        "schema_version": 1,
        "validator": "ap-advisor-topic-code",
        "course": course,
        "ap_oriented": ap_oriented,
        "overall_status": status,
        "results": [] if status == "error" else results,
    }
    if status == "error":
        evidence["error"] = "configuration error"
    if evidence_overrides:
        evidence.update(evidence_overrides)
    return [
        {
            "type": "item.started",
            "item": {
                "id": item_id,
                "type": "command_execution",
                "command": command,
                "status": "in_progress",
            },
        },
        {
            "type": "item.completed",
            "item": {
                "id": item_id,
                "type": "command_execution",
                "command": command,
                "status": "completed",
                "exit_code": exit_code,
                "aggregated_output": json.dumps(evidence, ensure_ascii=False),
            },
        },
    ]


def validator_observation(
    *, expected_validator_path: Path | None = None, **kwargs
) -> rbe.ValidatorObservation:
    return rbe.extract_validator_evidence(
        validator_events(**kwargs),
        expected_validator_path=expected_validator_path,
    )


class CorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = rbe.load_cases(CORPUS_PATH)

    def test_corpus_has_realistic_breadth(self):
        self.assertGreaterEqual(len(self.cases), 10)
        self.assertEqual(len(self.cases), len({case.id for case in self.cases}))
        self.assertEqual({case.invocation for case in self.cases}, {"explicit", "implicit"})
        self.assertEqual(
            {case.category for case in self.cases},
            rbe.VALID_CATEGORIES,
        )

    def test_corpus_covers_supported_courses_and_negative_routes(self):
        prompts = "\n".join(case.prompt for case in self.cases).casefold()
        for phrase in (
            "ap precalculus",
            "ap calculus ab",
            "ap calculus bc",
            "university calculus",
            "ap statistics",
        ):
            self.assertIn(phrase, prompts)

    def test_corpus_covers_high_risk_contracts(self):
        by_id = {case.id: case for case in self.cases}
        required_ids = {
            "explicit-ambiguous-bc-only-no-question",
            "precalc-unit4-ap-oriented-text-conflict",
            "precalc-unit4-ap-oriented-json-conflict",
            "calc-ab-chain-rule-review",
            "calc-ab-correct-review",
            "calc-ab-correct-conclusion-underjustified-review",
            "calc-ab-diagnostic-advisor-zh",
            "calc-ab-json-practice-no-answer",
            "calc-ab-broad-weakness-advisor",
            "calc-bc-multitopic-advisor",
        }
        self.assertTrue(required_ids <= by_id.keys())
        self.assertEqual(
            by_id["precalc-unit4-ap-oriented-json-conflict"].expect["output_kind"],
            "json_error",
        )
        self.assertTrue(
            by_id["calc-bc-multitopic-advisor"].expect["validator_call"]
        )
        self.assertIn(
            "10.11 Finding Taylor Polynomial Approximations of Functions",
            by_id["calc-bc-json-success"].expect["must_contain"],
        )

    def test_chinese_diagnostic_advisor_keeps_semantics_in_manual_review(self):
        by_id = {case.id: case for case in self.cases}
        case = by_id["calc-ab-diagnostic-advisor-zh"]
        self.assertEqual(case.category, "advisor")
        self.assertIn("请用中文", case.prompt)
        self.assertEqual(case.expect["must_contain"], [])
        self.assertEqual(case.expect["must_not_contain"], [])
        manual_checks = "\n".join(case.manual_checks)
        self.assertIn("measurable exit criterion", manual_checks)
        self.assertIn("unseen transfer problem", manual_checks)

    def test_multitopic_advisor_prioritization_is_not_a_keyword_contract(self):
        by_id = {case.id: case for case in self.cases}
        case = by_id["calc-bc-multitopic-advisor"]
        self.assertIn("one to three review tasks", case.prompt)
        self.assertEqual(case.expect["must_contain"], [])
        self.assertEqual(case.expect["must_not_contain"], [])
        manual_checks = "\n".join(case.manual_checks)
        self.assertIn("one to three minimal review tasks", manual_checks)
        self.assertIn("rather than inferred from catalog order", manual_checks)

    def test_text_validator_cases_declare_expected_course_and_mode(self):
        for case in self.cases:
            if (
                case.expect["output_kind"] == "text"
                and case.expect["validator_call"] is True
            ):
                self.assertIn(case.expect["validator_course"], rbe.VALID_COURSES)
                self.assertIsInstance(case.expect["validator_ap_oriented"], bool)
                self.assertIn(rbe.TEXT_EVIDENCE_MANUAL_CHECK, case.manual_checks)

    def test_json_success_cases_seal_prompt_fixed_fields(self):
        for case in self.cases:
            if case.expect["output_kind"] == "json_success":
                self.assertEqual(
                    set(case.expect["json_contract"]), rbe.JSON_CONTRACT_FIELDS
                )

    def test_practice_no_answer_case_uses_structured_key_constraints(self):
        by_id = {case.id: case for case in self.cases}
        practice = by_id["calc-ab-json-practice-no-answer"]
        self.assertEqual(
            practice.expect["forbidden_content_fields"],
            ["final_answer", "solution"],
        )
        self.assertNotIn("solution", practice.expect["must_not_contain"])

    def test_natural_prompts_do_not_embed_key_skill_answers(self):
        by_id = {case.id: case for case in self.cases}
        common_prompt = by_id["explicit-ambiguous-common-scope"].prompt.casefold()
        advisor_prompt = by_id["calc-bc-multitopic-advisor"].prompt.casefold()
        self.assertNotIn("ab-safe", common_prompt)
        self.assertNotIn("common to ab and bc", common_prompt)
        self.assertNotIn("equally weak", advisor_prompt)
        self.assertNotIn("catalog topic", advisor_prompt)

    def test_negative_routes_reject_catalog_citations_without_validator(self):
        by_id = {case.id: case for case in self.cases}
        university = by_id["implicit-university-calculus-negative"]
        self.assertEqual(
            rbe.evaluate_case(
                university,
                "Use the product rule: Unit 2, Topic 2.8 — The Product Rule.",
                NO_VALIDATOR,
            ),
            [
                "validator-forbidden text response contains a catalog topic citation"
            ],
        )
        self.assertEqual(
            rbe.evaluate_case(
                university,
                (
                    "Use the product rule to differentiate the two factors. "
                    "Your textbook also discusses this in Topic 6.2."
                ),
                NO_VALIDATOR,
            ),
            [],
        )
        for joined_citation in (
            "Use the product rule; 参考Unit 2, Topic 2.8这个内容。",
            "Use the product rule; see_Unit 2, Topic 2.8_more.",
            "Use the product rule; Unit&nbsp;2, Topic&nbsp;2.8.",
            "Use the product rule; Unit 2, Topic <strong>2.8</strong>.",
        ):
            self.assertEqual(
                rbe.evaluate_case(university, joined_citation, NO_VALIDATOR),
                [
                    "validator-forbidden text response contains a catalog topic citation"
                ],
            )

    def test_semantic_negation_checks_stay_in_manual_review(self):
        by_id = {case.id: case for case in self.cases}
        for case_id, phrase in (
            ("calc-ab-chain-rule-review", "correct as written"),
            ("calc-ab-multi-error-review", "correct as written"),
            ("calc-ab-correct-review", "missing inner derivative"),
            ("calc-ab-broad-weakness-advisor", "equally weak"),
        ):
            self.assertNotIn(phrase, by_id[case_id].expect["must_not_contain"])

    def test_complex_judgments_have_manual_checks(self):
        complex_categories = {"advisor", "review"}
        for case in self.cases:
            if case.category in complex_categories:
                self.assertTrue(case.manual_checks, case.id)

    def test_invalid_json_reports_corpus_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            corpus = Path(temp_dir) / "broken.jsonl"
            corpus.write_text('{"id":\n', encoding="utf-8")
            with self.assertRaisesRegex(rbe.RunnerError, "invalid JSON"):
                rbe.load_cases(corpus)

    def test_duplicate_ids_are_rejected(self):
        record = {
            "id": "duplicate",
            "category": "scope",
            "invocation": "explicit",
            "prompt": "A prompt",
            "expect": {},
            "manual_checks": [],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            corpus = Path(temp_dir) / "duplicate.jsonl"
            line = json.dumps(record)
            corpus.write_text(f"{line}\n{line}\n", encoding="utf-8")
            with self.assertRaisesRegex(rbe.RunnerError, "duplicate case id"):
                rbe.load_cases(corpus)

    def test_non_string_category_is_reported_as_a_corpus_error(self):
        record = {
            "id": "bad-category",
            "category": ["scope"],
            "invocation": "explicit",
            "prompt": "A prompt",
            "expect": {},
            "manual_checks": [],
        }
        with self.assertRaisesRegex(rbe.RunnerError, "category must be one of"):
            rbe.validate_case(record, 1)

    def test_non_string_output_kind_is_reported_as_a_corpus_error(self):
        record = {
            "id": "bad-output-kind",
            "category": "scope",
            "invocation": "explicit",
            "prompt": "A prompt",
            "expect": {"output_kind": ["text"]},
            "manual_checks": [],
        }
        with self.assertRaisesRegex(rbe.RunnerError, "output_kind must be one of"):
            rbe.validate_case(record, 1)

    def test_text_validator_case_missing_course_or_mode_is_rejected(self):
        record = {
            "id": "missing-validator-context",
            "category": "scope",
            "invocation": "explicit",
            "prompt": "A prompt",
            "expect": {"output_kind": "text", "validator_call": True},
            "manual_checks": [],
        }
        with self.assertRaisesRegex(rbe.RunnerError, "must set validator_course"):
            rbe.validate_case(record, 1)

    def test_json_success_case_missing_contract_is_rejected(self):
        record = {
            "id": "missing-json-contract",
            "category": "machine-output",
            "invocation": "explicit",
            "prompt": "A prompt",
            "expect": {"output_kind": "json_success", "validator_call": True},
            "manual_checks": [],
        }
        with self.assertRaisesRegex(rbe.RunnerError, "json_contract must be an object"):
            rbe.validate_case(record, 1)

    def test_forbidden_content_fields_require_json_success_and_known_keys(self):
        base = {
            "id": "bad-content-fields",
            "category": "machine-output",
            "invocation": "explicit",
            "prompt": "prompt",
            "expect": {
                "output_kind": "text",
                "validator_call": None,
                "forbidden_content_fields": ["solution"],
            },
            "manual_checks": [],
        }
        with self.assertRaisesRegex(rbe.RunnerError, "allowed only for json_success"):
            rbe.validate_case(base, 1)

        invalid = json.loads(json.dumps(base))
        invalid["expect"].update(
            {
                "output_kind": "json_success",
                "json_contract": {
                    "course": "calc-ab",
                    "unit": "Unit 3",
                    "topic": "3.1 The Chain Rule",
                    "topic_exam_scope": "assessed",
                    "type": "practice_problem",
                    "difficulty": "standard",
                    "style": "instructional",
                    "supporting_topics": [],
                },
                "forbidden_content_fields": ["answer_key"],
            }
        )
        with self.assertRaisesRegex(rbe.RunnerError, "unknown field"):
            rbe.validate_case(invalid, 1)

    def test_unknown_case_filter_is_rejected(self):
        with self.assertRaisesRegex(rbe.RunnerError, "unknown case id"):
            rbe.select_cases(self.cases, ["does-not-exist"])


class CodexJsonlParsingTests(unittest.TestCase):
    def test_extracts_last_completed_agent_message(self):
        events = [
            {"type": "thread.started", "thread_id": "abc"},
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": "first"},
            },
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": "final"},
            },
        ]
        self.assertEqual(rbe.extract_final_message(events), "final")

    def test_missing_agent_message_is_runner_error(self):
        with self.assertRaisesRegex(rbe.RunnerError, "no completed agent_message"):
            rbe.extract_final_message([{"type": "thread.started"}])

    def test_detects_validator_only_in_command_events(self):
        command_event = {
            "type": "item.completed",
            "item": {
                "type": "command_execution",
                "command": "python scripts/validate_topic_code.py --course calc-ab ...",
            },
        }
        prose_event = {
            "type": "item.completed",
            "item": {
                "type": "agent_message",
                "text": "I could run validate_topic_code.py",
            },
        }
        self.assertTrue(rbe.detected_validator_call([command_event]))
        self.assertFalse(rbe.detected_validator_call([prose_event]))

    def test_reading_or_searching_validator_source_is_not_a_call(self):
        for command in (
            "Get-Content scripts/validate_topic_code.py",
            "rg python scripts/validate_topic_code.py",
        ):
            event = {
                "type": "item.completed",
                "item": {"type": "command_execution", "command": command},
            }
            self.assertFalse(rbe.detected_validator_call([event]), command)

    def test_detects_wrapped_python_validator_call(self):
        commands = (
            "bash -lc python3 scripts/validate_topic_code.py --course calc-ab citation",
            'bash -lc "python3 scripts/validate_topic_code.py --course calc-ab citation"',
            "powershell -Command & 'C:\\Python313\\python.exe' "
            "'scripts\\validate_topic_code.py' --course calc-ab citation",
        )
        for command in commands:
            event = {
                "type": "item.started",
                "item": {"type": "command_execution", "command": command},
            }
            self.assertTrue(rbe.detected_validator_call([event]), command)

    def test_invalid_jsonl_event_is_runner_error(self):
        with self.assertRaisesRegex(rbe.RunnerError, "invalid"):
            rbe.parse_json_events('{"type": "thread.started"}\nnot-json\n')

    def test_duplicate_jsonl_event_key_is_runner_error(self):
        with self.assertRaisesRegex(rbe.RunnerError, "duplicate JSON key"):
            rbe.parse_json_events(
                '{"type":"thread.started","type":"thread.started"}\n'
            )


class ValidatorEvidenceContractTests(unittest.TestCase):
    CHAIN_RULE = "Unit 3, Topic 3.1 — The Chain Rule"
    LAGRANGE = "Unit 10, Topic 10.12 — Lagrange Error Bound"
    TAYLOR = (
        "Unit 10, Topic 10.11 — Finding Taylor Polynomial Approximations of Functions"
    )

    def text_case(self) -> rbe.EvalCase:
        return rbe.EvalCase(
            id="text-evidence",
            category="scope",
            invocation="explicit",
            prompt="prompt",
            expect={
                "output_kind": "text",
                "validator_call": True,
                "validator_course": "calc-ab",
                "validator_ap_oriented": False,
                "must_contain": [],
                "must_not_contain": [],
            },
            manual_checks=(),
        )

    def json_case(self, validator_call: bool | None = True) -> rbe.EvalCase:
        return rbe.EvalCase(
            id="json-evidence",
            category="machine-output",
            invocation="explicit",
            prompt="prompt",
            expect={
                "output_kind": "json_success",
                "validator_call": validator_call,
                "validator_course": None,
                "validator_ap_oriented": None,
                "must_contain": [],
                "must_not_contain": [],
            },
            manual_checks=(),
        )

    def json_message(self, automated_status: str = "pass") -> str:
        return json.dumps(
            {
                "course": "calc-bc",
                "unit": "Unit 10",
                "topic": "10.12 Lagrange Error Bound",
                "topic_exam_scope": "assessed",
                "type": "worked_example",
                "difficulty": "challenge",
                "style": "ap-oriented",
                "citation_validation": {
                    "catalog_match": "exact",
                    "automated_status": automated_status,
                },
                "supporting_topics": [
                    {
                        "unit": "Unit 10",
                        "topic": "10.11 Finding Taylor Polynomial Approximations of Functions",
                        "topic_exam_scope": "assessed",
                    }
                ],
                "content": {"problem_statement": "p", "solution": "s"},
            }
        )

    def test_exact_json_primary_and_supporting_evidence_pass(self):
        observation = validator_observation(
            course="calc-bc",
            ap_oriented=True,
            citations=[(self.LAGRANGE, "assessed"), (self.TAYLOR, "assessed")],
        )
        self.assertEqual(
            rbe.evaluate_case(self.json_case(), self.json_message(), observation), []
        )

    def test_json_evidence_missing_extra_duplicate_or_wrong_scope_fails(self):
        variants = {
            "missing": [(self.LAGRANGE, "assessed")],
            "extra": [
                (self.LAGRANGE, "assessed"),
                (self.TAYLOR, "assessed"),
                ("Unit 10, Topic 10.10 — Alternating Series Error Bound", "assessed"),
            ],
            "duplicate": [
                (self.LAGRANGE, "assessed"),
                (self.TAYLOR, "assessed"),
                (self.TAYLOR, "assessed"),
            ],
            "wrong-scope": [
                (self.LAGRANGE, "not-assessed"),
                (self.TAYLOR, "assessed"),
            ],
        }
        for label, citations in variants.items():
            with self.subTest(label=label):
                observation = validator_observation(
                    course="calc-bc", ap_oriented=True, citations=citations
                )
                failures = rbe.evaluate_case(
                    self.json_case(), self.json_message(), observation
                )
                self.assertTrue(
                    any("do not exactly match JSON output" in item for item in failures),
                    failures,
                )

    def test_wrong_course_and_ap_mode_fail(self):
        course_observation = validator_observation(
            course="calc-ab",
            ap_oriented=True,
            citations=[(self.LAGRANGE, "assessed"), (self.TAYLOR, "assessed")],
        )
        mode_observation = validator_observation(
            course="calc-bc",
            ap_oriented=False,
            citations=[(self.LAGRANGE, "assessed"), (self.TAYLOR, "assessed")],
        )
        course_failures = "\n".join(
            rbe.evaluate_case(self.json_case(), self.json_message(), course_observation)
        )
        mode_failures = "\n".join(
            rbe.evaluate_case(self.json_case(), self.json_message(), mode_observation)
        )
        self.assertIn("validator course expected", course_failures)
        self.assertIn("validator AP-oriented mode expected", mode_failures)

    def test_json_prompt_contract_cannot_be_redefined_by_model_output(self):
        base_case = self.json_case()
        expect = dict(base_case.expect)
        expect["json_contract"] = {
            "course": "calc-ab",
            "unit": "Unit 3",
            "topic": "3.1 The Chain Rule",
            "topic_exam_scope": "assessed",
            "type": "practice_problem",
            "difficulty": "standard",
            "style": "instructional",
            "supporting_topics": [],
        }
        case = rbe.EvalCase(
            id=base_case.id,
            category=base_case.category,
            invocation=base_case.invocation,
            prompt=base_case.prompt,
            expect=expect,
            manual_checks=base_case.manual_checks,
        )
        colluding_evidence = validator_observation(
            course="calc-bc",
            ap_oriented=True,
            citations=[(self.LAGRANGE, "assessed"), (self.TAYLOR, "assessed")],
        )
        failures = "\n".join(
            rbe.evaluate_case(case, self.json_message(), colluding_evidence)
        )
        self.assertIn("JSON field 'course' expected 'calc-ab'", failures)
        self.assertIn("JSON field 'difficulty' expected 'standard'", failures)
        self.assertIn("validator course expected 'calc-ab'", failures)

    def test_malformed_json_field_types_fail_without_runner_exception(self):
        base_case = self.json_case()
        expect = dict(base_case.expect)
        expect["json_contract"] = {
            "course": "calc-bc",
            "unit": "Unit 10",
            "topic": "10.12 Lagrange Error Bound",
            "topic_exam_scope": "assessed",
            "type": "worked_example",
            "difficulty": "challenge",
            "style": "ap-oriented",
            "supporting_topics": [
                {
                    "unit": "Unit 10",
                    "topic": "10.11 Finding Taylor Polynomial Approximations of Functions",
                    "topic_exam_scope": "assessed",
                }
            ],
        }
        case = rbe.EvalCase(
            id=base_case.id,
            category=base_case.category,
            invocation=base_case.invocation,
            prompt=base_case.prompt,
            expect=expect,
            manual_checks=base_case.manual_checks,
        )
        mutations = {
            "course": ("course", []),
            "style": ("style", {}),
            "primary-scope": ("topic_exam_scope", []),
        }
        for label, (field, replacement) in mutations.items():
            with self.subTest(label=label):
                value = json.loads(self.json_message())
                value[field] = replacement
                self.assertTrue(
                    rbe.evaluate_case(case, json.dumps(value), NO_VALIDATOR)
                )
        value = json.loads(self.json_message())
        value["supporting_topics"][0]["unit"] = []
        self.assertTrue(rbe.evaluate_case(case, json.dumps(value), NO_VALIDATOR))

    def test_started_without_completion_is_not_evidence(self):
        events = validator_events(
            course="calc-ab", citations=[(self.CHAIN_RULE, "assessed")]
        )[:1]
        observation = rbe.extract_validator_evidence(events)
        self.assertTrue(observation.observed)
        self.assertEqual(observation.accepted_runs, ())
        failures = "\n".join(
            rbe.evaluate_case(self.text_case(), self.CHAIN_RULE, observation)
        )
        self.assertIn("no matching item.completed", failures)
        self.assertIn("no accepted successful evidence", failures)

    def test_same_id_non_validator_completion_cannot_erase_started_run(self):
        events = validator_events(
            course="calc-ab", citations=[(self.CHAIN_RULE, "assessed")]
        )
        events[1]["item"].update(
            {
                "command": "echo done",
                "aggregated_output": "done\n",
                "exit_code": 0,
            }
        )
        observation = rbe.extract_validator_evidence(events)
        self.assertTrue(observation.observed)
        self.assertTrue(observation.fatal_failures)
        self.assertFalse(observation.accepted_runs)

    def test_same_id_validator_completion_cannot_replace_non_validator_start(self):
        events = validator_events(
            course="calc-ab", citations=[(self.CHAIN_RULE, "assessed")]
        )
        events[0]["item"]["command"] = "echo harmless"
        observation = rbe.extract_validator_evidence(events)
        self.assertTrue(observation.observed)
        self.assertTrue(
            any(
                "started and completed events report different commands" in item
                for item in observation.fatal_failures
            )
        )
        self.assertFalse(observation.accepted_runs)

    def test_late_started_event_cannot_reuse_a_completed_validator_id(self):
        events = validator_events(
            course="calc-ab", citations=[(self.CHAIN_RULE, "assessed")]
        )
        events.append(
            {
                "type": "item.started",
                "item": {
                    "id": "validator-1",
                    "type": "command_execution",
                    "command": "echo harmless",
                    "status": "in_progress",
                },
            }
        )
        observation = rbe.extract_validator_evidence(events)
        self.assertTrue(
            any(
                "item.started appears after item.completed" in failure
                for failure in observation.fatal_failures
            )
        )
        self.assertTrue(
            rbe.evaluate_case(self.text_case(), self.CHAIN_RULE, observation)
        )

    def test_late_started_without_command_cannot_reuse_validator_id(self):
        events = validator_events(
            course="calc-ab", citations=[(self.CHAIN_RULE, "assessed")]
        )
        events.append(
            {
                "type": "item.started",
                "item": {
                    "id": "validator-1",
                    "type": "command_execution",
                    "status": "in_progress",
                },
            }
        )
        observation = rbe.extract_validator_evidence(events)
        self.assertTrue(
            any(
                "item.started command is missing or malformed" in failure
                for failure in observation.fatal_failures
            )
        )
        self.assertTrue(
            any(
                "item.started appears after item.completed" in failure
                for failure in observation.fatal_failures
            )
        )
        self.assertTrue(
            rbe.evaluate_case(self.text_case(), self.CHAIN_RULE, observation)
        )

    def test_duplicate_started_without_command_poison_validator_id(self):
        events = validator_events(
            course="calc-ab", citations=[(self.CHAIN_RULE, "assessed")]
        )
        events.insert(
            1,
            {
                "type": "item.started",
                "item": {
                    "id": "validator-1",
                    "type": "command_execution",
                    "status": "in_progress",
                },
            },
        )
        observation = rbe.extract_validator_evidence(events)
        self.assertTrue(
            any(
                "duplicate item.started id" in failure
                for failure in observation.fatal_failures
            )
        )
        self.assertTrue(
            any(
                "command is missing or malformed" in failure
                for failure in observation.fatal_failures
            )
        )
        self.assertFalse(observation.accepted_runs)

    def test_duplicate_started_id_fails_closed(self):
        events = validator_events(
            course="calc-ab", citations=[(self.CHAIN_RULE, "assessed")]
        )
        events.insert(1, dict(events[0]))
        observation = rbe.extract_validator_evidence(events)
        self.assertTrue(
            any("duplicate item.started id" in item for item in observation.fatal_failures)
        )
        self.assertFalse(observation.accepted_runs)

    def test_duplicate_completed_id_fails_closed_without_started_events(self):
        first = validator_events(
            course="calc-ab",
            citations=[(self.CHAIN_RULE, "assessed")],
            item_id="reused-completion",
        )[1]
        second = validator_events(
            course="calc-ab",
            citations=[(self.CHAIN_RULE, "assessed")],
            item_id="reused-completion",
        )[1]
        observation = rbe.extract_validator_evidence([first, second])
        self.assertTrue(
            any(
                "duplicate item.completed id" in item
                for item in observation.fatal_failures
            )
        )
        self.assertTrue(
            rbe.evaluate_case(self.text_case(), self.CHAIN_RULE, observation)
        )

    def test_exit_one_then_corrected_exit_zero_can_pass(self):
        bad = validator_events(
            course="calc-ab",
            citations=[("Unit 3, Topic 3.99 — Imaginary Rule", "assessed")],
            exit_code=1,
            item_id="validator-bad",
        )
        good = validator_events(
            course="calc-ab",
            citations=[(self.CHAIN_RULE, "assessed")],
            item_id="validator-good",
        )
        bad[1]["item"]["status"] = "failed"
        observation = rbe.extract_validator_evidence([*bad, *good])
        self.assertEqual(len(observation.accepted_runs), 1)
        self.assertEqual(
            rbe.evaluate_case(self.text_case(), self.CHAIN_RULE, observation), []
        )

    def test_exit_two_remains_fatal_after_later_success(self):
        broken = validator_events(
            course="calc-ab",
            citations=[(self.CHAIN_RULE, "assessed")],
            exit_code=2,
            item_id="validator-broken",
        )
        good = validator_events(
            course="calc-ab",
            citations=[(self.CHAIN_RULE, "assessed")],
            item_id="validator-good",
        )
        observation = rbe.extract_validator_evidence([*broken, *good])
        failures = "\n".join(
            rbe.evaluate_case(self.text_case(), self.CHAIN_RULE, observation)
        )
        self.assertIn("fatal setup/data failure", failures)

    def test_missing_output_or_conflicting_event_fields_fail(self):
        missing = validator_events(
            course="calc-ab", citations=[(self.CHAIN_RULE, "assessed")]
        )
        missing[1]["item"].pop("aggregated_output")
        conflicting = validator_events(
            course="calc-ab",
            citations=[(self.CHAIN_RULE, "assessed")],
            item_id="validator-conflict",
        )
        conflicting[1]["item"]["exitCode"] = 1
        boolean_alias = validator_events(
            course="calc-ab",
            citations=[(self.CHAIN_RULE, "assessed")],
            item_id="validator-bool-alias",
        )
        boolean_alias[1]["item"]["exitCode"] = False
        missing_status = validator_events(
            course="calc-ab",
            citations=[(self.CHAIN_RULE, "assessed")],
            item_id="validator-no-status",
        )
        missing_status[1]["item"].pop("status")
        missing_exit = validator_events(
            course="calc-ab",
            citations=[(self.CHAIN_RULE, "assessed")],
            item_id="validator-no-exit",
        )
        missing_exit[1]["item"].pop("exit_code")
        variants = {
            "missing-output": missing,
            "conflicting-fields": conflicting,
            "boolean-exit-alias": boolean_alias,
            "missing-status": missing_status,
            "missing-exit": missing_exit,
        }
        for label, events in variants.items():
            with self.subTest(label=label):
                observation = rbe.extract_validator_evidence(events)
                self.assertTrue(observation.fatal_failures)
                self.assertFalse(observation.accepted_runs)

    def test_framework_override_compound_shell_and_legacy_alias_fail(self):
        commands = {
            "framework": (
                "python scripts/validate_topic_code.py --course calc-ab "
                "--framework references/ap-calc-framework.md --evidence-json "
                f'"{self.CHAIN_RULE}"'
            ),
            "compound": (
                "python scripts/validate_topic_code.py --course calc-ab "
                f'--evidence-json "{self.CHAIN_RULE}" && echo done'
            ),
            "alias": (
                "python scripts/validate_topic_code.py --course calc-ab "
                f'--exam-style --evidence-json "{self.CHAIN_RULE}"'
            ),
            "wrong-script-root": (
                "python C:\\tmp\\scripts\\validate_topic_code.py --course calc-ab "
                f'--evidence-json "{self.CHAIN_RULE}"'
            ),
            "expanded-script-root": (
                "powershell -Command python \"$env:TEMP\\.agents\\skills\\ap-advisor"
                "\\scripts\\validate_topic_code.py\" --course calc-ab "
                f'--evidence-json "{self.CHAIN_RULE}"'
            ),
        }
        for label, command in commands.items():
            with self.subTest(label=label):
                observation = validator_observation(
                    course="calc-ab",
                    citations=[(self.CHAIN_RULE, "assessed")],
                    command=command,
                )
                self.assertTrue(observation.fatal_failures)
                self.assertFalse(observation.accepted_runs)

    def test_live_path_seal_requires_the_exact_staged_validator(self):
        expected = Path(
            "C:/safe/.agents/skills/ap-advisor/scripts/validate_topic_code.py"
        )
        commands = {
            "expected": (
                "python C:/safe/.agents/skills/ap-advisor/scripts"
                f'/validate_topic_code.py --course calc-ab --evidence-json "{self.CHAIN_RULE}"'
            ),
            "attacker": (
                "python C:/attacker/.agents/skills/ap-advisor/scripts"
                f'/validate_topic_code.py --course calc-ab --evidence-json "{self.CHAIN_RULE}"'
            ),
        }
        accepted = validator_observation(
            course="calc-ab",
            citations=[(self.CHAIN_RULE, "assessed")],
            command=commands["expected"],
            expected_validator_path=expected,
        )
        rejected = validator_observation(
            course="calc-ab",
            citations=[(self.CHAIN_RULE, "assessed")],
            command=commands["attacker"],
            expected_validator_path=expected,
        )
        self.assertEqual(len(accepted.accepted_runs), 1)
        self.assertTrue(rejected.fatal_failures)
        self.assertFalse(rejected.accepted_runs)
    def test_course_mode_and_evidence_flags_require_exact_cardinality(self):
        base = "python scripts/validate_topic_code.py"
        quoted = f'"{self.CHAIN_RULE}"'
        commands = {
            "missing-course": f"{base} --evidence-json {quoted}",
            "duplicate-course": (
                f"{base} --course calc-ab --course calc-ab --evidence-json {quoted}"
            ),
            "duplicate-mode": (
                f"{base} --course calc-ab --ap-oriented --ap-oriented "
                f"--evidence-json {quoted}"
            ),
            "missing-evidence-flag": f"{base} --course calc-ab {quoted}",
        }
        for label, command in commands.items():
            with self.subTest(label=label):
                observation = validator_observation(
                    course="calc-ab",
                    citations=[(self.CHAIN_RULE, "assessed")],
                    command=command,
                )
                self.assertTrue(observation.fatal_failures)
                self.assertFalse(observation.accepted_runs)
        equals_observation = validator_observation(
            course="calc-ab",
            citations=[(self.CHAIN_RULE, "assessed")],
            command=f"{base} --course=calc-ab --evidence-json {quoted}",
        )
        self.assertEqual(equals_observation.fatal_failures, ())
        self.assertEqual(len(equals_observation.accepted_runs), 1)

    def test_command_and_evidence_inputs_must_match(self):
        wrong_result = {
            "input": "Unit 2, Topic 2.8 — The Product Rule",
            "status": "pass",
            "citation": "Unit 2, Topic 2.8 — The Product Rule",
            "topic_exam_scope": "assessed",
        }
        observation = validator_observation(
            course="calc-ab",
            citations=[(self.CHAIN_RULE, "assessed")],
            evidence_overrides={"results": [wrong_result]},
        )
        self.assertTrue(
            any("inputs do not exactly match" in item for item in observation.fatal_failures)
        )

    def test_unhashable_malformed_evidence_fails_without_crashing(self):
        malformed_values = {
            "schema-version-float": {"schema_version": 1.0},
            "course": {"course": []},
            "overall-status": {"overall_status": []},
            "scope": {
                "results": [
                    {
                        "input": self.CHAIN_RULE,
                        "status": "pass",
                        "citation": self.CHAIN_RULE,
                        "topic_exam_scope": [],
                    }
                ]
            },
        }
        for label, overrides in malformed_values.items():
            with self.subTest(label=label):
                observation = validator_observation(
                    course="calc-ab",
                    citations=[(self.CHAIN_RULE, "assessed")],
                    evidence_overrides=overrides,
                )
                self.assertTrue(observation.fatal_failures)
                self.assertFalse(observation.accepted_runs)

    def test_duplicate_validator_evidence_key_fails_closed(self):
        events = validator_events(
            course="calc-ab", citations=[(self.CHAIN_RULE, "assessed")]
        )
        output = events[1]["item"]["aggregated_output"]
        events[1]["item"]["aggregated_output"] = output.replace(
            '"schema_version": 1,',
            '"schema_version": 1, "schema_version": 1,',
            1,
        )
        observation = rbe.extract_validator_evidence(events)
        self.assertTrue(
            any("duplicate JSON key" in item for item in observation.fatal_failures)
        )
        self.assertFalse(observation.accepted_runs)

    def test_not_run_claim_conflicts_with_accepted_evidence(self):
        observation = validator_observation(
            course="calc-bc",
            ap_oriented=True,
            citations=[(self.LAGRANGE, "assessed"), (self.TAYLOR, "assessed")],
        )
        failures = "\n".join(
            rbe.evaluate_case(
                self.json_case(validator_call=None),
                self.json_message(automated_status="not_run"),
                observation,
            )
        )
        self.assertIn("not_run despite an observed validator attempt", failures)

    def test_not_run_claim_cannot_hide_a_failed_validator_attempt(self):
        observation = validator_observation(
            course="calc-bc",
            ap_oriented=True,
            citations=[(self.LAGRANGE, "assessed")],
            exit_code=1,
        )
        failures = "\n".join(
            rbe.evaluate_case(
                self.json_case(validator_call=None),
                self.json_message(automated_status="not_run"),
                observation,
            )
        )
        self.assertIn("not_run despite an observed validator attempt", failures)

    def test_json_not_run_requires_every_supported_launcher_to_fail_prestart(self):
        citations = [(self.LAGRANGE, "assessed"), (self.TAYLOR, "assessed")]
        citation_args = " ".join(
            json.dumps(citation, ensure_ascii=False) for citation, _scope in citations
        )
        variants = (
            (
                "python3",
                f"python3 scripts/validate_topic_code.py --course calc-bc "
                f"--ap-oriented --evidence-json {citation_args}",
            ),
            (
                "python",
                f"python scripts/validate_topic_code.py --course calc-bc "
                f"--ap-oriented --evidence-json {citation_args}",
            ),
            (
                "py",
                f"py -3 scripts/validate_topic_code.py --course calc-bc "
                f"--ap-oriented --evidence-json {citation_args}",
            ),
        )
        all_events: list[dict] = []
        for launcher, command in variants:
            events = validator_events(
                course="calc-bc",
                ap_oriented=True,
                citations=citations,
                exit_code=127,
                command=command,
                item_id=f"missing-{launcher}",
            )
            events[1]["item"]["aggregated_output"] = (
                f"/bin/sh: 1: {launcher}: not found\n"
            )
            all_events.extend(events)

        one_failure = rbe.extract_validator_evidence(all_events[:2])
        one_failures = "\n".join(
            rbe.evaluate_case(
                self.json_case(),
                self.json_message(automated_status="not_run"),
                one_failure,
            )
        )
        self.assertIn("before all supported launcher families", one_failures)

        observation = rbe.extract_validator_evidence(all_events)
        self.assertTrue(observation.only_verified_prestart_failures)
        self.assertTrue(observation.exhausted_launcher_families)
        self.assertEqual(observation.fatal_failures, ())
        self.assertEqual(observation.accepted_runs, ())
        self.assertEqual(
            rbe.evaluate_case(
                self.json_case(),
                self.json_message(automated_status="not_run"),
                observation,
            ),
            [],
        )

        failed_status_events = []
        for event in all_events:
            copied = json.loads(json.dumps(event))
            if copied["type"] == "item.completed":
                copied["item"]["status"] = "failed"
            failed_status_events.append(copied)
        failed_status_observation = rbe.extract_validator_evidence(
            failed_status_events
        )
        self.assertTrue(failed_status_observation.exhausted_launcher_families)
        self.assertEqual(failed_status_observation.fatal_failures, ())
        self.assertEqual(
            rbe.evaluate_case(
                self.json_case(),
                self.json_message(automated_status="not_run"),
                failed_status_observation,
            ),
            [],
        )

        unrelated_events: list[dict] = []
        for launcher, command in variants:
            events = validator_events(
                course="calc-bc",
                ap_oriented=True,
                citations=citations,
                exit_code=127,
                command=command,
                item_id=f"unrelated-{launcher}",
            )
            events[1]["item"]["aggregated_output"] = (
                "/bin/sh: 1: jq: command not found\n"
            )
            unrelated_events.extend(events)
        unrelated = rbe.extract_validator_evidence(unrelated_events)
        self.assertFalse(unrelated.only_verified_prestart_failures)
        self.assertTrue(unrelated.fatal_failures)

        fabricated_paths: list[dict] = []
        for launcher, command in variants:
            path_command = command.replace(launcher, f"/missing/{launcher}", 1)
            events = validator_events(
                course="calc-bc",
                ap_oriented=True,
                citations=citations,
                exit_code=127,
                command=path_command,
                item_id=f"fabricated-{launcher}",
            )
            events[1]["item"]["aggregated_output"] = (
                f"/bin/sh: /missing/{launcher}: not found\n"
            )
            fabricated_paths.extend(events)
        fabricated = rbe.extract_validator_evidence(fabricated_paths)
        self.assertTrue(fabricated.only_verified_prestart_failures)
        self.assertFalse(fabricated.exhausted_launcher_families)
        fabricated_failures = "\n".join(
            rbe.evaluate_case(
                self.json_case(),
                self.json_message(automated_status="not_run"),
                fabricated,
            )
        )
        self.assertIn("before all supported launcher families", fabricated_failures)

        versioned_commands = (
            (
                "python3.999",
                variants[0][1].replace("python3", "python3.999", 1),
            ),
            variants[1],
            (
                "py",
                variants[2][1].replace("py -3", "py -3.999", 1),
            ),
        )
        versioned_events: list[dict] = []
        for launcher, command in versioned_commands:
            events = validator_events(
                course="calc-bc",
                ap_oriented=True,
                citations=citations,
                exit_code=127,
                command=command,
                item_id=f"versioned-{launcher}",
            )
            events[1]["item"]["aggregated_output"] = (
                f"/bin/sh: 1: {launcher}: not found\n"
            )
            versioned_events.extend(events)
        versioned = rbe.extract_validator_evidence(versioned_events)
        self.assertTrue(versioned.only_verified_prestart_failures)
        self.assertFalse(versioned.exhausted_launcher_families)

    def test_canonical_launcher_equivalence_is_platform_specific(self):
        with mock.patch.object(rbe.sys, "platform", "linux"):
            self.assertTrue(rbe._is_canonical_launcher_token("python3", "python3"))
            self.assertFalse(rbe._is_canonical_launcher_token("PYTHON3", "python3"))
            self.assertFalse(
                rbe._is_canonical_launcher_token("python3.exe", "python3")
            )
            self.assertFalse(
                rbe._is_canonical_launcher_token("/usr/bin/python3", "python3")
            )

        with mock.patch.object(rbe.sys, "platform", "win32"):
            self.assertTrue(rbe._is_canonical_launcher_token("python3", "python3"))
            self.assertTrue(rbe._is_canonical_launcher_token("PYTHON3", "python3"))
            self.assertTrue(
                rbe._is_canonical_launcher_token("Python3.EXE", "python3")
            )
            self.assertFalse(
                rbe._is_canonical_launcher_token("C:/Python/python3.exe", "python3")
            )

    def test_json_containing_launcher_words_is_not_a_prestart_failure(self):
        events = validator_events(
            course="calc-ab",
            citations=[(self.CHAIN_RULE, "assessed")],
            exit_code=1,
        )
        events[1]["item"]["aggregated_output"] = json.dumps("command not found")
        observation = rbe.extract_validator_evidence(events)
        self.assertFalse(observation.only_verified_prestart_failures)
        self.assertTrue(observation.fatal_failures)

    def test_prestart_failure_is_bound_to_the_exact_launcher_token(self):
        for launcher in ("python3", "python", "py"):
            with self.subTest(launcher=launcher):
                self.assertFalse(
                    rbe._is_verified_launcher_failure(
                        127,
                        f"/bin/sh: 1: not{launcher}: command not found",
                        launcher,
                    )
                )

        self.assertTrue(
            rbe._is_verified_launcher_failure(
                127,
                "/usr/bin/env: ‘python3’: No such file or directory",
                "python3",
            )
        )
        self.assertTrue(
            rbe._is_verified_launcher_failure(
                1,
                "CategoryInfo : ObjectNotFound: (python3:String) [], "
                "CommandNotFoundException",
                "python3",
            )
        )
        self.assertTrue(
            rbe._is_verified_launcher_failure(
                9009,
                "Python was not found; run without arguments to install from "
                "the Microsoft Store.",
                "python",
            )
        )

    def test_pass_claim_without_accepted_evidence_fails(self):
        failures = "\n".join(
            rbe.evaluate_case(self.json_case(), self.json_message(), NO_VALIDATOR)
        )
        self.assertIn("pass without accepted evidence", failures)

    def test_plain_text_extra_or_duplicate_citation_fails(self):
        observation = validator_observation(
            course="calc-ab", citations=[(self.CHAIN_RULE, "assessed")]
        )
        for message in (
            f"{self.CHAIN_RULE}\nUnit 2, Topic 2.8 — The Product Rule",
            f"{self.CHAIN_RULE}\nunit 2, topic 2.8 — The Product Rule",
            f"{self.CHAIN_RULE}\nUnit 2 / Topic 2.8 — The Product Rule",
            f"{self.CHAIN_RULE}\n**Unit 2 / Topic 2.8** — The Product Rule",
            f"{self.CHAIN_RULE}\nUnit 2, Topic **2.8** — The Product Rule",
            f"{self.CHAIN_RULE}\nUnit&nbsp;2, Topic&nbsp;2.8",
            f"{self.CHAIN_RULE}\nUnit 2, Topic <strong>2.8</strong>",
            f"{self.CHAIN_RULE}\n{self.CHAIN_RULE}",
        ):
            with self.subTest(message=message):
                self.assertTrue(
                    rbe.evaluate_case(self.text_case(), message, observation)
                )

    def test_plain_text_citation_must_be_visible(self):
        observation = validator_observation(
            course="calc-ab", citations=[(self.CHAIN_RULE, "assessed")]
        )
        for message in (
            f"<!-- {self.CHAIN_RULE} -->",
            f'<span hidden>{self.CHAIN_RULE}</span>',
            f'<span style="display:none">{self.CHAIN_RULE}</span>',
            f'<span style="opacity:0">{self.CHAIN_RULE}</span>',
            f'<dialog>{self.CHAIN_RULE}</dialog>',
            f'[ref]: https://example.invalid "{self.CHAIN_RULE}"',
            f'[//]: # ({self.CHAIN_RULE})',
            f'![{self.CHAIN_RULE}](https://example.invalid/image.png)',
            f'[click](https://example.invalid "{self.CHAIN_RULE}")',
            f'[click](https://example.invalid/it\'s "{self.CHAIN_RULE}")',
            f'[click [nested]](https://example.invalid "{self.CHAIN_RULE}")',
            f'![alt](https://example.invalid/(foo) "{self.CHAIN_RULE}")',
        ):
            with self.subTest(message=message):
                failures = "\n".join(
                    rbe.evaluate_case(self.text_case(), message, observation)
                )
                self.assertTrue(
                    "observed 0" in failures or "visibility is not sealed" in failures
                    or "Markdown image syntax" in failures
                    or "Markdown link target" in failures,
                    failures,
                )

    def test_zero_width_formatting_cannot_hide_an_extra_text_citation(self):
        observation = validator_observation(
            course="calc-ab", citations=[(self.CHAIN_RULE, "assessed")]
        )
        for hidden_character in ("&#8203;", "\u034f", "\ufe0f"):
            with self.subTest(hidden_character=hidden_character):
                message = (
                    f"{self.CHAIN_RULE}\nUnit 2, To{hidden_character}pic 2.8 - extra"
                )
                failures = "\n".join(
                    rbe.evaluate_case(self.text_case(), message, observation)
                )
                self.assertIn("extra or non-exact catalog citation", failures)

    def test_json_content_cannot_hide_an_unvalidated_catalog_citation(self):
        observation = validator_observation(
            course="calc-bc",
            ap_oriented=True,
            citations=[(self.LAGRANGE, "assessed"), (self.TAYLOR, "assessed")],
        )
        value = json.loads(self.json_message())
        value["content"]["solution"] = (
            "See Unit 9, Topic 9.8 - Finding the Area of a Polar Region."
        )
        failures = "\n".join(
            rbe.evaluate_case(self.json_case(), json.dumps(value), observation)
        )
        self.assertIn("unstructured catalog citation", failures)

        for hidden_markup in (
            '<span hidden>Unit 9, Topic 9.8 - extra</span>',
            '<script>Unit 9, Topic 9.8 - extra</script>',
            '<input hidden>Unit 9, Topic 9.8 - extra',
        ):
            with self.subTest(hidden_markup=hidden_markup):
                value["content"]["solution"] = hidden_markup
                failures = "\n".join(
                    rbe.evaluate_case(
                        self.json_case(), json.dumps(value), observation
                    )
                )
                self.assertIn("unstructured catalog citation", failures)

    def test_duplicate_successful_runs_cannot_justify_duplicate_text(self):
        first = validator_events(
            course="calc-ab",
            citations=[(self.CHAIN_RULE, "assessed")],
            item_id="validator-one",
        )
        second = validator_events(
            course="calc-ab",
            citations=[(self.CHAIN_RULE, "assessed")],
            item_id="validator-two",
        )
        observation = rbe.extract_validator_evidence([*first, *second])
        failures = "\n".join(
            rbe.evaluate_case(
                self.text_case(),
                f"{self.CHAIN_RULE}\n{self.CHAIN_RULE}",
                observation,
            )
        )
        self.assertIn("successful evidence repeats citation", failures)

    def test_disjoint_successful_runs_do_not_replace_one_grouped_run(self):
        first = validator_events(
            course="calc-bc",
            ap_oriented=True,
            citations=[(self.LAGRANGE, "assessed")],
            item_id="validator-primary",
        )
        second = validator_events(
            course="calc-bc",
            ap_oriented=True,
            citations=[(self.TAYLOR, "assessed")],
            item_id="validator-supporting",
        )
        observation = rbe.extract_validator_evidence([*first, *second])
        failures = "\n".join(
            rbe.evaluate_case(self.json_case(), self.json_message(), observation)
        )
        self.assertIn("one successful grouped run", failures)

    def test_validator_forbidden_case_rejects_even_a_started_attempt(self):
        case = self.text_case()
        expect = dict(case.expect)
        expect["validator_call"] = False
        forbidden_case = rbe.EvalCase(
            id=case.id,
            category=case.category,
            invocation=case.invocation,
            prompt=case.prompt,
            expect=expect,
            manual_checks=case.manual_checks,
        )
        started = validator_events(
            course="calc-ab", citations=[(self.CHAIN_RULE, "assessed")]
        )[:1]
        observation = rbe.extract_validator_evidence(started)
        failures = "\n".join(
            rbe.evaluate_case(forbidden_case, "ordinary response", observation)
        )
        self.assertIn("expected false, observed true", failures)

    def test_completion_can_reuse_started_command_and_camel_case_fields(self):
        events = validator_events(
            course="calc-ab", citations=[(self.CHAIN_RULE, "assessed")]
        )
        completed = events[1]["item"]
        completed.pop("command")
        completed["exitCode"] = completed.pop("exit_code")
        completed["aggregatedOutput"] = completed.pop("aggregated_output")
        observation = rbe.extract_validator_evidence(events)
        self.assertEqual(len(observation.accepted_runs), 1)

    def test_single_known_shell_wrapper_can_supply_evidence(self):
        posix_inner = shlex.join(
            [
                "python3",
                "/repo/.agents/skills/ap-advisor/scripts/validate_topic_code.py",
                "--course",
                "calc-ab",
                "--evidence-json",
                self.CHAIN_RULE,
            ]
        )
        commands = (
            (
                "& 'C:\\Python313\\python.exe' "
                "'C:\\repo\\.agents\\skills\\ap-advisor\\scripts\\validate_topic_code.py' "
                f"--course calc-ab --evidence-json '{self.CHAIN_RULE}'"
            ),
            f"bash -lc {shlex.quote(posix_inner)}",
            f"/bin/bash -lc {shlex.quote(posix_inner)}",
            f"bash -c {shlex.quote(posix_inner)}",
            f"sh -cl {shlex.quote(posix_inner)}",
            f"zsh -l -c {shlex.quote(posix_inner)}",
            (
                "powershell -Command & 'C:\\Python313\\python.exe' "
                "'C:\\repo\\.agents\\skills\\ap-advisor\\scripts\\validate_topic_code.py' --course calc-ab "
                f"--evidence-json '{self.CHAIN_RULE}'"
            ),
            (
                "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe "
                "-NoProfile -NonInteractive -Command & 'C:\\Python313\\python.exe' "
                "'C:\\repo\\.agents\\skills\\ap-advisor\\scripts\\validate_topic_code.py' "
                f"--course calc-ab --evidence-json '{self.CHAIN_RULE}'"
            ),
            (
                "/usr/bin/env python3 /repo/.agents/skills/ap-advisor/scripts/"
                "validate_topic_code.py --course calc-ab --evidence-json "
                f'"{self.CHAIN_RULE}"'
            ),
            (
                "env PYTHONUTF8=1 python3 /repo/.agents/skills/ap-advisor/scripts/"
                "validate_topic_code.py --course calc-ab --evidence-json "
                f'"{self.CHAIN_RULE}"'
            ),
        )
        for command in commands:
            with self.subTest(command=command):
                observation = validator_observation(
                    course="calc-ab",
                    citations=[(self.CHAIN_RULE, "assessed")],
                    command=command,
                )
                self.assertEqual(observation.fatal_failures, ())
                self.assertEqual(len(observation.accepted_runs), 1)

    def test_powershell_doubled_apostrophe_is_one_citation_argument(self):
        euler = "Unit 7, Topic 7.5 — Approximating Solutions Using Euler's Method"
        powershell_argument = euler.replace("'", "''")
        command = (
            "powershell -NoProfile -Command python3 "
            "C:\\repo\\.agents\\skills\\ap-advisor\\scripts\\validate_topic_code.py "
            "--course calc-bc --evidence-json "
            f"'{powershell_argument}'"
        )
        observation = validator_observation(
            course="calc-bc",
            citations=[(euler, "assessed")],
            command=command,
        )
        self.assertEqual(observation.fatal_failures, ())
        self.assertEqual(len(observation.accepted_runs), 1)

    def test_posix_shell_quoting_preserves_apostrophes_in_citations(self):
        citations = (
            "Unit 7, Topic 7.5 鈥?Approximating Solutions Using Euler's Method",
            "Unit 4, Topic 4.7 鈥?Using L'Hospital's Rule for Indeterminate Forms",
        )
        inner = shlex.join(
            [
                "python3",
                "/repo/.agents/skills/ap-advisor/scripts/validate_topic_code.py",
                "--course",
                "calc-bc",
                "--evidence-json",
                *citations,
            ]
        )
        candidate, invocation, failures = rbe._parse_validator_invocation(
            f"bash -lc {shlex.quote(inner)}"
        )
        self.assertTrue(candidate)
        self.assertEqual(failures, ())
        self.assertIsNotNone(invocation)
        self.assertEqual(invocation.citations, citations)

        with mock.patch.object(rbe.sys, "platform", "linux"):
            candidate, invocation, failures = rbe._parse_validator_invocation(inner)
        self.assertTrue(candidate)
        self.assertEqual(failures, ())
        self.assertIsNotNone(invocation)
        self.assertEqual(invocation.citations, citations)

    def test_unquoted_posix_shell_payload_cannot_supply_evidence(self):
        command = (
            "bash -lc python3 /repo/.agents/skills/ap-advisor/scripts/"
            "validate_topic_code.py --course calc-ab --evidence-json "
            f'"{self.CHAIN_RULE}"'
        )
        observation = validator_observation(
            course="calc-ab",
            citations=[(self.CHAIN_RULE, "assessed")],
            command=command,
        )
        self.assertTrue(
            any(
                "exactly one command-string argument" in failure
                for failure in observation.fatal_failures
            )
        )
        self.assertFalse(observation.accepted_runs)

        unsupported = validator_observation(
            course="calc-ab",
            citations=[(self.CHAIN_RULE, "assessed")],
            command=f"bash -x -c {shlex.quote(command)}",
        )
        self.assertTrue(unsupported.observed)
        self.assertTrue(unsupported.fatal_failures)

        unknown_shell = validator_observation(
            course="calc-ab",
            citations=[(self.CHAIN_RULE, "assessed")],
            command=f"dash -c {shlex.quote(command)}",
        )
        self.assertTrue(unknown_shell.observed)
        self.assertTrue(unknown_shell.fatal_failures)

    def test_powershell_mixed_quote_citations_preserve_apostrophes(self):
        euler = "Unit 7, Topic 7.5 — Approximating Solutions Using Euler's Method"
        lhopital = (
            "Unit 4, Topic 4.7 — Using L'Hospital's Rule for Indeterminate Forms"
        )
        escaped_lhopital = lhopital.replace("'", "''")
        command = (
            "powershell -NoProfile -Command python3 "
            "C:\\repo\\.agents\\skills\\ap-advisor\\scripts\\validate_topic_code.py "
            "--course calc-bc --evidence-json "
            f'"{euler}" \'{escaped_lhopital}\''
        )
        observation = validator_observation(
            course="calc-bc",
            citations=[(euler, "assessed"), (lhopital, "assessed")],
            command=command,
        )
        self.assertEqual(observation.fatal_failures, ())
        self.assertEqual(len(observation.accepted_runs), 1)

    def test_unsafe_environment_or_direct_shebang_invocation_fails_closed(self):
        commands = {
            "unsafe-environment": (
                "env PYTHONPATH=/tmp python3 /repo/.agents/skills/ap-advisor/scripts/"
                "validate_topic_code.py --course calc-ab --evidence-json "
                f'"{self.CHAIN_RULE}"'
            ),
            "direct-shebang": (
                "/repo/.agents/skills/ap-advisor/scripts/validate_topic_code.py "
                f'--course calc-ab --evidence-json "{self.CHAIN_RULE}"'
            ),
        }
        for label, command in commands.items():
            with self.subTest(label=label):
                observation = validator_observation(
                    course="calc-ab",
                    citations=[(self.CHAIN_RULE, "assessed")],
                    command=command,
                )
                self.assertTrue(observation.observed)
                self.assertTrue(observation.fatal_failures)
                self.assertFalse(observation.accepted_runs)

    def test_indirect_python_with_exact_staged_path_fails_closed(self):
        expected = Path(
            "C:/safe/.agents/skills/ap-advisor/scripts/validate_topic_code.py"
        )
        command = (
            'python -c "exec(open(\'C:/safe/.agents/skills/ap-advisor/scripts/'
            "validate_topic_code.py\').read())\""
        )
        observation = validator_observation(
            course="calc-ab",
            citations=[(self.CHAIN_RULE, "assessed")],
            command=command,
            expected_validator_path=expected,
        )
        self.assertTrue(observation.observed)
        self.assertTrue(
            any(
                "indirect Python execution" in failure
                for failure in observation.fatal_failures
            )
        )
        self.assertFalse(observation.accepted_runs)

        relative = (
            'python -c "import runpy; runpy.run_path('
            "'.agents/skills/ap-advisor/scripts/validate_topic_code.py', "
            "run_name='__main__')\""
        )
        relative_observation = validator_observation(
            course="calc-ab",
            citations=[(self.CHAIN_RULE, "assessed")],
            command=relative,
            expected_validator_path=expected,
        )
        self.assertTrue(relative_observation.observed)
        self.assertTrue(relative_observation.fatal_failures)
        self.assertFalse(relative_observation.accepted_runs)

    def test_read_command_prefix_cannot_hide_compound_validator_execution(self):
        commands = (
            (
                "rg needle README.md ; python3 "
                "/repo/.agents/skills/ap-advisor/scripts/validate_topic_code.py "
                f'--course calc-ab --evidence-json "{self.CHAIN_RULE}"'
            ),
            (
                "cat README.md && python3 "
                "/repo/.agents/skills/ap-advisor/scripts/validate_topic_code.py "
                f'--course calc-ab --evidence-json "{self.CHAIN_RULE}"'
            ),
        )
        for command in commands:
            with self.subTest(command=command):
                observation = validator_observation(
                    course="calc-ab",
                    citations=[(self.CHAIN_RULE, "assessed")],
                    command=command,
                )
                self.assertTrue(observation.observed)
                self.assertTrue(observation.fatal_failures)
                self.assertFalse(observation.accepted_runs)

    def test_real_validator_json_is_consumed_end_to_end(self):
        arguments = [
            "python",
            str(Path("scripts") / "validate_topic_code.py"),
            "--course",
            "calc-bc",
            "--ap-oriented",
            "--evidence-json",
            self.LAGRANGE,
            self.TAYLOR,
        ]
        completed = rbe.subprocess.run(
            arguments,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        command = rbe.subprocess.list2cmdline(arguments)
        events = [
            {
                "type": "item.completed",
                "item": {
                    "id": "real-validator",
                    "type": "command_execution",
                    "command": command,
                    "status": "completed",
                    "exit_code": completed.returncode,
                    "aggregated_output": completed.stdout,
                },
            }
        ]
        observation = rbe.extract_validator_evidence(events)
        self.assertEqual(observation.fatal_failures, ())
        self.assertEqual(
            rbe.evaluate_case(self.json_case(), self.json_message(), observation), []
        )


class AutomatedAssertionTests(unittest.TestCase):
    def make_case(self, **expect_overrides):
        expect = {
            "output_kind": "text",
            "validator_call": True,
            "validator_course": "calc-ab",
            "validator_ap_oriented": False,
            "must_contain": ["The Chain Rule"],
            "must_not_contain": ["official question"],
        }
        expect.update(expect_overrides)
        return rbe.EvalCase(
            id="test-case",
            category="scope",
            invocation="explicit",
            prompt="prompt",
            expect=expect,
            manual_checks=(),
        )

    def test_text_and_validator_assertions_pass(self):
        case = self.make_case()
        citation = "Unit 3, Topic 3.1 — The Chain Rule"
        observation = validator_observation(
            course="calc-ab", citations=[(citation, "assessed")]
        )
        self.assertEqual(
            rbe.evaluate_case(
                case,
                f"Catalog Topic: {citation}\nThe Chain Rule original practice",
                observation,
            ),
            [],
        )

    def test_text_and_validator_failures_are_reported_together(self):
        case = self.make_case()
        failures = rbe.evaluate_case(
            case, "This is an official question", NO_VALIDATOR
        )
        self.assertTrue(any("missing required text" in item for item in failures))
        self.assertTrue(any("forbidden text" in item for item in failures))
        self.assertTrue(any("validator_call expected" in item for item in failures))

    def test_valid_machine_error_object_passes(self):
        case = self.make_case(
            output_kind="json_error",
            validator_call=False,
            must_contain=[],
            must_not_contain=[],
        )
        message = json.dumps(
            {
                "status": "cannot_fulfill",
                "reason": "Unit 4 is not assessed on the AP Exam.",
                "conflicts": ["ap-oriented style conflicts with not-assessed scope"],
                "allowed_alternatives": ["Use instructional style"],
            }
        )
        self.assertEqual(rbe.evaluate_case(case, message, NO_VALIDATOR), [])

    def test_machine_error_rejects_extra_fields(self):
        case = self.make_case(
            output_kind="json_error",
            validator_call=None,
            must_contain=[],
            must_not_contain=[],
        )
        message = json.dumps(
            {
                "status": "cannot_fulfill",
                "reason": "conflict",
                "conflicts": ["one"],
                "allowed_alternatives": ["two"],
                "extra": True,
            }
        )
        failures = rbe.evaluate_case(case, message, NO_VALIDATOR)
        self.assertTrue(any("not allowed" in item for item in failures))

    def test_machine_output_rejects_duplicate_json_keys(self):
        case = self.make_case(
            output_kind="json_error",
            validator_call=False,
            must_contain=[],
            must_not_contain=[],
        )
        message = (
            '{"status":"cannot_fulfill","status":"cannot_fulfill",'
            '"reason":"conflict","conflicts":["one"],'
            '"allowed_alternatives":["two"]}'
        )
        failures = "\n".join(rbe.evaluate_case(case, message, NO_VALIDATOR))
        self.assertIn("duplicate JSON key", failures)

    def test_text_kind_rejects_json(self):
        case = self.make_case(
            output_kind="text",
            validator_call=None,
            must_contain=[],
            must_not_contain=[],
        )
        failures = rbe.evaluate_case(case, '{"answer": 2}', NO_VALIDATOR)
        self.assertTrue(any("expected text" in item for item in failures))

    def test_minimal_success_json_shape(self):
        case = self.make_case(
            output_kind="json_success",
            validator_call=True,
            must_contain=[],
            must_not_contain=[],
        )
        message = json.dumps(
            {
                "course": "calc-bc",
                "unit": "Unit 7",
                "topic": "7.5 Approximating Solutions Using Euler's Method",
                "topic_exam_scope": "assessed",
                "type": "worked_example",
                "difficulty": "foundational",
                "style": "instructional",
                "citation_validation": {
                    "catalog_match": "exact",
                    "automated_status": "pass",
                },
                "content": {"problem_statement": "p", "solution": "s"},
            }
        )
        observation = validator_observation(
            course="calc-bc",
            citations=[
                (
                    "Unit 7, Topic 7.5 — Approximating Solutions Using Euler's Method",
                    "assessed",
                )
            ],
        )
        self.assertEqual(rbe.evaluate_case(case, message, observation), [])

    def test_success_json_enforces_type_specific_and_scope_rules(self):
        case = self.make_case(
            output_kind="json_success",
            validator_call=None,
            must_contain=[],
            must_not_contain=[],
        )
        message = json.dumps(
            {
                "course": "precalculus",
                "unit": "Unit 4",
                "topic": "4.10 Matrices",
                "topic_exam_scope": "not-assessed",
                "type": "worked_example",
                "difficulty": "standard",
                "style": "ap-oriented",
                "citation_validation": {
                    "catalog_match": "exact",
                    "automated_status": "pass",
                },
                "content": {"problem_statement": "p", "extra": "not allowed"},
                "extra": True,
            }
        )
        failures = rbe.evaluate_case(case, message, NO_VALIDATOR)
        joined = "\n".join(failures)
        self.assertIn("solution is required", joined)
        self.assertIn("style", joined)
        self.assertIn("not allowed", joined)

    def test_practice_problem_can_omit_answer_and_solution(self):
        case = self.make_case(
            output_kind="json_success",
            validator_call=True,
            forbidden_content_fields=["final_answer", "solution"],
            must_contain=[],
            must_not_contain=[],
        )
        message = json.dumps(
            {
                "course": "calc-ab",
                "unit": "Unit 3",
                "topic": "3.1 The Chain Rule",
                "topic_exam_scope": "assessed",
                "type": "practice_problem",
                "difficulty": "standard",
                "style": "instructional",
                "citation_validation": {
                    "catalog_match": "exact",
                    "automated_status": "pass",
                },
                "content": {
                    "problem_statement": (
                        "Find a solution by differentiating sin(x^2)."
                    )
                },
            }
        )
        observation = validator_observation(
            course="calc-ab",
            citations=[("Unit 3, Topic 3.1 — The Chain Rule", "assessed")],
        )
        self.assertEqual(rbe.evaluate_case(case, message, observation), [])

        with_solution = json.loads(message)
        with_solution["content"]["solution"] = "2x cos(x^2)"
        failures = "\n".join(
            rbe.evaluate_case(case, json.dumps(with_solution), observation)
        )
        self.assertIn("content field 'solution' is forbidden", failures)

    def test_not_assessed_topic_can_still_use_standard_difficulty(self):
        case = self.make_case(
            output_kind="json_success",
            validator_call=True,
            must_contain=[],
            must_not_contain=[],
        )
        message = json.dumps(
            {
                "course": "precalculus",
                "unit": "Unit 4",
                "topic": "4.10 Matrices",
                "topic_exam_scope": "not-assessed",
                "type": "worked_example",
                "difficulty": "standard",
                "style": "instructional",
                "citation_validation": {
                    "catalog_match": "exact",
                    "automated_status": "pass",
                },
                "content": {"problem_statement": "p", "solution": "s"},
            }
        )
        observation = validator_observation(
            course="precalculus",
            citations=[("Unit 4, Topic 4.10 — Matrices", "not-assessed")],
        )
        self.assertEqual(rbe.evaluate_case(case, message, observation), [])

    def test_supporting_topic_and_not_run_evidence_are_structured(self):
        case = self.make_case(
            output_kind="json_success",
            validator_call=False,
            must_contain=[],
            must_not_contain=[],
        )
        message = json.dumps(
            {
                "course": "calc-bc",
                "unit": "Unit 10",
                "topic": "10.12 Lagrange Error Bound",
                "topic_exam_scope": "assessed",
                "type": "worked_example",
                "difficulty": "challenge",
                "style": "ap-oriented",
                "citation_validation": {
                    "catalog_match": "exact",
                    "automated_status": "not_run",
                },
                "supporting_topics": [
                    {
                        "unit": "Unit 10",
                        "topic": "10.11 Finding Taylor Polynomial Approximations of Functions",
                        "topic_exam_scope": "assessed",
                    }
                ],
                "content": {"problem_statement": "p", "solution": "s"},
            }
        )
        self.assertEqual(rbe.evaluate_case(case, message, NO_VALIDATOR), [])

    def test_malformed_supporting_topic_is_rejected(self):
        case = self.make_case(
            output_kind="json_success",
            validator_call=True,
            must_contain=[],
            must_not_contain=[],
        )
        message = json.dumps(
            {
                "course": "calc-bc",
                "unit": "Unit 10",
                "topic": "10.12 Lagrange Error Bound",
                "topic_exam_scope": "assessed",
                "type": "worked_example",
                "difficulty": "challenge",
                "style": "ap-oriented",
                "citation_validation": {
                    "catalog_match": "exact",
                    "automated_status": "pass",
                },
                "supporting_topics": [
                    {
                        "unit": "Unit 10",
                        "topic": "10.11 Finding Taylor Polynomial Approximations of Functions",
                        "course": "calc-bc",
                    }
                ],
                "content": {"problem_statement": "p", "solution": "s"},
            }
        )
        failures = "\n".join(rbe.evaluate_case(case, message, NO_VALIDATOR))
        self.assertIn("topic_exam_scope is required", failures)
        self.assertIn("course is not allowed", failures)

    def test_ap_oriented_item_rejects_not_assessed_supporting_topic(self):
        case = self.make_case(
            output_kind="json_success",
            validator_call=True,
            must_contain=[],
            must_not_contain=[],
        )
        message = json.dumps(
            {
                "course": "precalculus",
                "unit": "Unit 2",
                "topic": "2.4 Exponential Function Manipulation",
                "topic_exam_scope": "assessed",
                "type": "worked_example",
                "difficulty": "challenge",
                "style": "ap-oriented",
                "citation_validation": {
                    "catalog_match": "exact",
                    "automated_status": "pass",
                },
                "supporting_topics": [
                    {
                        "unit": "Unit 4",
                        "topic": "4.10 Matrices",
                        "topic_exam_scope": "not-assessed",
                    }
                ],
                "content": {"problem_statement": "p", "solution": "s"},
            }
        )
        failures = "\n".join(rbe.evaluate_case(case, message, NO_VALIDATOR))
        self.assertIn("supporting_topics[0].topic_exam_scope", failures)
        self.assertIn("assessed", failures)

    def test_empty_content_and_invalid_citation_evidence_fail(self):
        case = self.make_case(
            output_kind="json_success",
            validator_call=None,
            must_contain=[],
            must_not_contain=[],
        )
        message = json.dumps(
            {
                "course": "precalculus",
                "unit": "Unit 2",
                "topic": "2.4 Exponential Function Manipulation",
                "topic_exam_scope": "assessed",
                "type": "explanation",
                "difficulty": "foundational",
                "style": "instructional",
                "citation_validation": {
                    "catalog_match": "approximate",
                    "automated_status": "failed",
                },
                "content": {"principle": ""},
            }
        )
        failures = "\n".join(rbe.evaluate_case(case, message, NO_VALIDATOR))
        self.assertIn("catalog_match", failures)
        self.assertIn("automated_status", failures)
        self.assertIn("principle", failures)

    def test_unknown_schema_keyword_fails_closed(self):
        with self.assertRaisesRegex(rbe.RunnerError, "unsupported JSON Schema"):
            rbe._schema_failures({}, {"oneOf": [{"type": "object"}]})


class BehaviorStatusSemanticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = {case.id: case for case in rbe.load_cases(CORPUS_PATH)}

    @staticmethod
    def statuses(case, failures):
        return rbe._evaluation_statuses(
            automated_passed=not failures,
            manual_review_required=bool(case.manual_checks),
        )

    def test_bc_only_generation_can_contract_pass_but_requires_manual_review(self):
        case = self.cases["explicit-ambiguous-bc-only-no-question"]
        message = (
            "Here is the requested Taylor-polynomial practice problem: "
            "find the third-degree polynomial and show your work."
        )

        failures = rbe.evaluate_case(case, message, NO_VALIDATOR)

        self.assertEqual(failures, [])
        contract_status, overall_status = self.statuses(case, failures)
        self.assertEqual(contract_status, rbe.CONTRACT_PASS)
        self.assertEqual(overall_status, rbe.MANUAL_REVIEW_REQUIRED)
        self.assertNotEqual(overall_status, "PASS")

    def test_wrong_math_with_valid_topic_receipt_requires_manual_review(self):
        case = self.cases["calc-ab-chain-rule-review"]
        citation = "Unit 3, Topic 3.1 — The Chain Rule"
        message = f"{citation}\nThe derivative is 2x sin(x^2)."
        observation = validator_observation(
            course="calc-ab",
            citations=[(citation, "assessed")],
        )

        failures = rbe.evaluate_case(case, message, observation)

        self.assertEqual(failures, [])
        contract_status, overall_status = self.statuses(case, failures)
        self.assertEqual(contract_status, rbe.CONTRACT_PASS)
        self.assertEqual(overall_status, rbe.MANUAL_REVIEW_REQUIRED)
        self.assertNotEqual(overall_status, "PASS")

    def test_automatic_failure_overrides_pending_manual_review(self):
        self.assertEqual(
            rbe._evaluation_statuses(
                automated_passed=False,
                manual_review_required=True,
            ),
            (rbe.FAIL, rbe.FAIL),
        )
        self.assertEqual(
            rbe._evaluation_statuses(
                automated_passed=True,
                manual_review_required=False,
            ),
            (rbe.CONTRACT_PASS, rbe.CONTRACT_PASS),
        )


class SafeDefaultModeTests(unittest.TestCase):
    def test_default_mode_never_invokes_codex_or_writes_results(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "must-not-exist"
            stdout = io.StringIO()
            with mock.patch.object(
                rbe, "run_codex_case", side_effect=AssertionError("model call")
            ), mock.patch.object(
                rbe, "write_results", side_effect=AssertionError("result write")
            ), redirect_stdout(stdout):
                exit_code = rbe.main(
                    [
                        "--corpus",
                        str(CORPUS_PATH),
                        "--case",
                        "implicit-precalc-generate",
                        "--output-dir",
                        str(output_dir),
                    ]
                )
        self.assertEqual(exit_code, 0)
        self.assertIn("VALID:", stdout.getvalue())
        self.assertIn("CORPUS CONTRACT ONLY", stdout.getvalue())
        self.assertIn("LIVE MODEL EVAL: NOT RUN", stdout.getvalue())
        self.assertIn("no model calls or result writes", stdout.getvalue())
        self.assertFalse(output_dir.exists())

    def test_invalid_corpus_returns_exit_two(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            corpus = Path(temp_dir) / "invalid.jsonl"
            corpus.write_text("not-json\n", encoding="utf-8")
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                exit_code = rbe.main(["--corpus", str(corpus)])
        self.assertEqual(exit_code, 2)
        self.assertIn("ERROR:", stderr.getvalue())

    def test_live_assertion_failure_returns_exit_one_without_real_model_call(self):
        stdout = io.StringIO()
        captured: dict = {}

        def capture_results(_output_dir, payload):
            captured.update(payload)
            return Path("result.json")

        with mock.patch.object(
            rbe, "_resolve_executable", return_value="codex"
        ), mock.patch.object(
            rbe,
            "run_codex_case",
            return_value=("incomplete response", NO_VALIDATOR, ""),
        ), mock.patch.object(
            rbe,
            "write_results",
            side_effect=capture_results,
        ), redirect_stdout(stdout):
            exit_code = rbe.main(
                [
                    "--corpus",
                    str(CORPUS_PATH),
                    "--case",
                    "implicit-precalc-generate",
                    "--run",
                ]
            )
        self.assertEqual(exit_code, 1)
        self.assertIn("FAIL: implicit-precalc-generate", stdout.getvalue())
        self.assertNotIn("AUTO-FAIL", stdout.getvalue())
        self.assertEqual(captured["contract_status"], rbe.FAIL)
        self.assertEqual(captured["overall_status"], rbe.FAIL)
        self.assertFalse(captured["automated_pass"])
        self.assertTrue(captured["manual_review_required"])
        result = captured["results"][0]
        self.assertEqual(result["contract_status"], rbe.FAIL)
        self.assertEqual(result["overall_status"], rbe.FAIL)
        self.assertFalse(result["automated_passed"])

    def test_live_success_saves_structured_validator_evidence_without_model_call(self):
        citation = "Unit 2, Topic 2.4 — Exponential Function Manipulation"
        message = f"AP Precalculus\nCatalog Topic: {citation}\nWorked example."
        fake_events = validator_events(
            course="precalculus", citations=[(citation, "assessed")]
        ) + [
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": message},
            }
        ]
        fake_observation = rbe.extract_validator_evidence(fake_events)
        captured: dict = {}

        def capture_results(_output_dir, payload):
            captured.update(payload)
            return Path("result.json")

        stdout = io.StringIO()
        with mock.patch.object(
            rbe, "_resolve_executable", return_value="codex"
        ), mock.patch.object(
            rbe,
            "run_codex_case",
            return_value=(message, fake_observation, ""),
        ), mock.patch.object(
            rbe,
            "write_results",
            side_effect=capture_results,
        ), redirect_stdout(stdout):
            exit_code = rbe.main(
                [
                    "--corpus",
                    str(CORPUS_PATH),
                    "--case",
                    "implicit-precalc-generate",
                    "--run",
                ]
            )
        self.assertEqual(exit_code, 0)
        self.assertIn("CONTRACT-PASS", stdout.getvalue())
        self.assertIn("MANUAL REVIEW REQUIRED", stdout.getvalue())
        self.assertEqual(captured["contract_status"], rbe.CONTRACT_PASS)
        self.assertEqual(
            captured["overall_status"], rbe.MANUAL_REVIEW_REQUIRED
        )
        self.assertTrue(captured["automated_pass"])
        self.assertTrue(captured["manual_review_required"])
        result = captured["results"][0]
        self.assertEqual(result["contract_status"], rbe.CONTRACT_PASS)
        self.assertEqual(
            result["overall_status"], rbe.MANUAL_REVIEW_REQUIRED
        )
        self.assertTrue(result["automated_passed"])
        self.assertTrue(result["validator_observed"])
        self.assertEqual(result["validator_evidence"]["accepted_run_count"], 1)
        self.assertNotIn("validator_called", result)

    def test_live_command_ignores_user_config_by_default(self):
        events = (
            '{"type":"item.completed","item":'
            '{"type":"agent_message","text":"done"}}\n'
        )
        completed_git = rbe.subprocess.CompletedProcess([], 0, "", "")
        completed_codex = rbe.subprocess.CompletedProcess([], 0, events, "")
        case = rbe.EvalCase(
            id="command-contract",
            category="scope",
            invocation="implicit",
            prompt="prompt",
            expect={},
            manual_checks=(),
        )
        with mock.patch.object(
            rbe.subprocess,
            "run",
            side_effect=[completed_git, completed_codex],
        ) as run:
            rbe.run_codex_case(case, "codex", 30)
        command = run.call_args_list[1].args[0]
        self.assertIn("--ignore-user-config", command)
        self.assertIn("--ephemeral", command)
        self.assertEqual(command[-1], "prompt")

        with mock.patch.object(
            rbe.subprocess,
            "run",
            side_effect=[completed_git, completed_codex],
        ) as run:
            rbe.run_codex_case(case, "codex", 30, use_user_config=True)
        configured_command = run.call_args_list[1].args[0]
        self.assertNotIn("--ignore-user-config", configured_command)

    def test_result_directory_error_is_runner_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "not-a-directory"
            output_dir.write_text("occupied", encoding="utf-8")
            with self.assertRaisesRegex(rbe.RunnerError, "cannot write result file"):
                rbe.write_results(output_dir, {"results": []})


class MachineErrorSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads(ERROR_SCHEMA_PATH.read_text(encoding="utf-8"))

    def test_schema_requires_exact_error_envelope(self):
        self.assertEqual(self.schema["type"], "object")
        self.assertEqual(
            set(self.schema["required"]),
            {"status", "reason", "conflicts", "allowed_alternatives"},
        )
        self.assertFalse(self.schema["additionalProperties"])

    def test_status_is_fixed_and_text_fields_are_nonempty(self):
        properties = self.schema["properties"]
        self.assertEqual(properties["status"]["const"], "cannot_fulfill")
        self.assertEqual(properties["reason"]["minLength"], 1)
        for field in ("conflicts", "allowed_alternatives"):
            self.assertEqual(properties[field]["type"], "array")
            self.assertEqual(properties[field]["minItems"], 1)
            self.assertEqual(properties[field]["items"]["minLength"], 1)


if __name__ == "__main__":
    unittest.main()
