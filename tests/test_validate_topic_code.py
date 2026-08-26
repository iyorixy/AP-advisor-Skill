#!/usr/bin/env python3
"""
Regression tests for scripts/validate_topic_code.py.

Requires Python 3.10 or newer. Standard-library only (unittest). Run with:
    python3 -m unittest discover -s tests
or directly:
    python3 tests/test_validate_topic_code.py
"""

import importlib.util
import io
import json
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "validate_topic_code.py"
FRAMEWORK_PATH = REPO_ROOT / "references" / "ap-calc-framework.md"
SCHEMA_PATH = REPO_ROOT / "references" / "output-schema.json"

spec = importlib.util.spec_from_file_location("validate_topic_code", SCRIPT_PATH)
vtc = importlib.util.module_from_spec(spec)
sys.modules["validate_topic_code"] = vtc
spec.loader.exec_module(vtc)


def run_main(*args: str) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = vtc.main(list(args))
    return exit_code, stdout.getvalue(), stderr.getvalue()


class ParseFrameworkTests(unittest.TestCase):
    def setUp(self):
        self.topics = vtc.parse_framework(FRAMEWORK_PATH)

    def test_parses_topics(self):
        self.assertEqual(len(self.topics), 169)

    def test_topic_codes_are_unique_within_each_course(self):
        keys = [(topic.course, topic.topic_num) for topic in self.topics]
        self.assertEqual(len(keys), len(set(keys)))

    def test_topic_code_prefix_matches_containing_unit(self):
        mismatches = [
            topic
            for topic in self.topics
            if topic.topic_num.partition(".")[0] != topic.unit_num
        ]
        self.assertEqual(mismatches, [])

    def test_finds_known_topic(self):
        match = [
            t
            for t in self.topics
            if t.unit_num == "2" and t.topic_num == "2.4" and t.course.startswith("AP Precalculus")
        ]
        self.assertEqual(len(match), 1)
        self.assertEqual(match[0].topic_title, "Exponential Function Manipulation")

    def test_topic_numbers_repeat_across_courses(self):
        # "1.1" exists in both AP Precalculus (Unit 1) and AP Calculus AB/BC
        # (Unit 1) — this ambiguity is exactly what find_match must resolve
        # using the unit number and/or title.
        matches = [t for t in self.topics if t.topic_num == "1.1"]
        self.assertGreaterEqual(len(matches), 2)

    def test_every_catalog_topic_round_trips_as_an_exact_citation(self):
        for topic in self.topics:
            course_key = (
                "precalculus"
                if topic.course.startswith("AP Precalculus")
                else "calc-bc"
            )
            pool = vtc.filter_by_course(self.topics, course_key)
            with self.subTest(course=topic.course, citation=topic.citation):
                self.assertEqual(vtc.find_match(pool, topic.citation), topic)


class NormalizeTests(unittest.TestCase):
    def test_lowercases_and_strips_punctuation(self):
        self.assertEqual(vtc.normalize("Exponential Function Manipulation!"), "exponential function manipulation")

    def test_normalizes_curly_apostrophe(self):
        self.assertEqual(vtc.normalize("L’Hospital's Rule"), "l hospital s rule")

    def test_nfkc_normalizes_compatible_unicode_forms(self):
        self.assertEqual(vtc.normalize("ＦＵＬＬＷＩＤＴＨ ＴＥＸＴ"), "fullwidth text")

    def test_preserves_unicode_letters_while_normalizing_punctuation(self):
        self.assertEqual(
            vtc.normalize("中文、日本語・КИРИЛЛИЦА"),
            "中文 日本語 кириллица",
        )

    def test_preserves_non_punctuation_symbols(self):
        self.assertEqual(vtc.normalize("e^x ✓"), "e^x ✓")


class ExtractQueryFieldsTests(unittest.TestCase):
    def test_full_citation(self):
        unit, topic, title = vtc.extract_query_fields("Unit 2, Topic 2.4 — Exponential Function Manipulation")
        self.assertEqual(unit, "2")
        self.assertEqual(topic, "2.4")
        self.assertEqual(title, "Exponential Function Manipulation")

    def test_no_unit_given(self):
        unit, topic, title = vtc.extract_query_fields("Topic 2.4 — Exponential Function Manipulation")
        self.assertIsNone(unit)
        self.assertEqual(topic, "2.4")
        self.assertEqual(title, "Exponential Function Manipulation")

    def test_no_title_given(self):
        unit, topic, title = vtc.extract_query_fields("Unit 2, Topic 2.4")
        self.assertEqual(unit, "2")
        self.assertEqual(topic, "2.4")
        self.assertIsNone(title)


class BcOnlyParsingTests(unittest.TestCase):
    def setUp(self):
        self.topics = vtc.parse_framework(FRAMEWORK_PATH)

    def test_topic_level_bc_marker_is_flagged(self):
        match = [t for t in self.topics if t.topic_num == "6.11"]
        self.assertEqual(len(match), 1)
        self.assertTrue(match[0].bc_only)
        self.assertEqual(
            match[0].topic_title, "Integrating Using Integration by Parts"
        )

    def test_unit_level_bc_marker_propagates_to_topics(self):
        # Unit 10 (Infinite Sequences and Series) is BC-only as a whole;
        # its topics aren't individually marked, so the flag must come
        # from the unit title instead.
        match = [t for t in self.topics if t.unit_num == "10" and t.topic_num == "10.1"]
        self.assertEqual(len(match), 1)
        self.assertTrue(match[0].bc_only)

    def test_ab_eligible_topic_is_not_flagged(self):
        match = [t for t in self.topics if t.topic_num == "2.4" and t.course.startswith("AP Calculus")]
        self.assertEqual(len(match), 1)
        self.assertFalse(match[0].bc_only)


class ExamAssessmentParsingTests(unittest.TestCase):
    def setUp(self):
        self.topics = vtc.parse_framework(FRAMEWORK_PATH)

    def test_precalculus_unit_four_is_not_exam_assessed(self):
        unit_four = [
            topic
            for topic in self.topics
            if topic.course.startswith("AP Precalculus") and topic.unit_num == "4"
        ]
        self.assertGreater(len(unit_four), 0)
        self.assertTrue(all(not topic.exam_assessed for topic in unit_four))
        self.assertTrue(
            all("not assessed" not in topic.unit_title.lower() for topic in unit_four)
        )

    def test_all_other_current_topics_are_exam_assessed(self):
        other_topics = [
            topic
            for topic in self.topics
            if not (topic.course.startswith("AP Precalculus") and topic.unit_num == "4")
        ]
        self.assertTrue(all(topic.exam_assessed for topic in other_topics))

    def test_exam_scope_is_driven_by_framework_marker(self):
        framework_text = """## AP Precalculus
- Unit 4 — Alternate Assessed Unit
  - 4.1 Assessed Topic
- Unit 5 — Alternate Unassessed Unit (not assessed on AP Exam)
  - 5.1 Unassessed Topic
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            framework = Path(temp_dir) / "framework.md"
            framework.write_text(framework_text, encoding="utf-8")
            topics = vtc.parse_framework(framework)

        by_code = {topic.topic_num: topic for topic in topics}
        self.assertTrue(by_code["4.1"].exam_assessed)
        self.assertFalse(by_code["5.1"].exam_assessed)
        self.assertEqual(by_code["5.1"].unit_title, "Alternate Unassessed Unit")


class CourseFilterTests(unittest.TestCase):
    def setUp(self):
        self.topics = vtc.parse_framework(FRAMEWORK_PATH)

    def test_calc_ab_excludes_bc_only_topics(self):
        filtered = vtc.filter_by_course(self.topics, "calc-ab")
        self.assertTrue(all(not t.bc_only for t in filtered))
        self.assertTrue(any(t.course.startswith("AP Calculus") for t in filtered))

    def test_calc_bc_includes_bc_only_topics(self):
        filtered = vtc.filter_by_course(self.topics, "calc-bc")
        self.assertTrue(any(t.bc_only for t in filtered))

    def test_precalculus_excludes_calc_topics(self):
        filtered = vtc.filter_by_course(self.topics, "precalculus")
        self.assertTrue(all(t.course.startswith("AP Precalculus") for t in filtered))

    def test_no_filter_is_identity(self):
        self.assertEqual(vtc.filter_by_course(self.topics, None), self.topics)

    def test_find_match_rejects_bc_only_topic_under_calc_ab_filter(self):
        ab_pool = vtc.filter_by_course(self.topics, "calc-ab")
        match = vtc.find_match(
            ab_pool, "Unit 6, Topic 6.11 — Integrating Using Integration by Parts"
        )
        self.assertIsNone(match)

    def test_find_match_accepts_bc_only_topic_under_calc_bc_filter(self):
        bc_pool = vtc.filter_by_course(self.topics, "calc-bc")
        match = vtc.find_match(
            bc_pool, "Unit 6, Topic 6.11 — Integrating Using Integration by Parts"
        )
        self.assertIsNotNone(match)
        self.assertTrue(match.bc_only)

    def test_find_match_still_works_for_ab_eligible_topic_under_calc_ab_filter(self):
        ab_pool = vtc.filter_by_course(self.topics, "calc-ab")
        match = vtc.find_match(ab_pool, "Unit 2, Topic 2.8 — The Product Rule")
        self.assertIsNotNone(match)


class FindMatchTests(unittest.TestCase):
    def setUp(self):
        self.topics = vtc.parse_framework(FRAMEWORK_PATH)

    def test_exact_citation_matches(self):
        match = vtc.find_match(self.topics, "Unit 2, Topic 2.4 — Exponential Function Manipulation")
        self.assertIsNotNone(match)
        self.assertEqual(match.topic_num, "2.4")

    def test_normalized_exact_title_matches(self):
        match = vtc.find_match(
            self.topics,
            "unit 2, topic 2.4 - EXPONENTIAL-function manipulation!",
        )
        self.assertIsNotNone(match)

    def test_curly_apostrophes_and_trailing_punctuation_match(self):
        match = vtc.find_match(
            self.topics,
            "unit 4, topic 4.7 - Using L’Hospital’s Rule for Indeterminate Forms!",
        )
        self.assertIsNotNone(match)

    def test_non_ascii_suffixes_do_not_match(self):
        suffixes = (
            "完全错误的附加文本",
            "完全に誤った追加テキスト",
            "совершенно неверный добавочный текст",
        )
        for suffix in suffixes:
            with self.subTest(suffix=suffix):
                match = vtc.find_match(
                    self.topics,
                    f"Unit 3, Topic 3.1 — The Chain Rule {suffix}",
                )
                self.assertIsNone(match)

    def test_nonexistent_topic_number_fails(self):
        match = vtc.find_match(self.topics, "Unit 5, Topic 5.99 — Made Up Topic")
        self.assertIsNone(match)

    def test_wrong_title_for_real_number_fails(self):
        # 2.4 is real, but paired with a title that belongs to a different
        # topic entirely — must not be accepted as "close enough".
        match = vtc.find_match(self.topics, "Unit 2, Topic 2.4 — Completely Unrelated Topic Name")
        self.assertIsNone(match)

    def test_close_but_not_exact_title_fails(self):
        match = vtc.find_match(
            self.topics,
            "Unit 2, Topic 2.4 — Exponential Functions Manipulation",
        )
        self.assertIsNone(match)

    def test_wrong_unit_for_real_topic_fails(self):
        match = vtc.find_match(
            self.topics,
            "Unit 99, Topic 2.4 — Exponential Function Manipulation",
        )
        self.assertIsNone(match)

    def test_ambiguous_without_unit_or_title_fails(self):
        # "1.1" alone exists in more than one course/unit; with no unit and
        # no title to disambiguate, this must not silently guess one.
        match = vtc.find_match(self.topics, "Topic 1.1")
        self.assertIsNone(match)

    def test_missing_unit_fails_even_when_topic_and_title_are_unique(self):
        match = vtc.find_match(
            self.topics, "Topic 2.4 — Exponential Function Manipulation"
        )
        self.assertIsNone(match)

    def test_missing_title_fails_even_when_unit_and_topic_are_unique(self):
        match = vtc.find_match(self.topics, "Unit 2, Topic 2.8")
        self.assertIsNone(match)

    def test_unit_disambiguates_shared_topic_number(self):
        match = vtc.find_match(self.topics, "Unit 1, Topic 1.1 — Change in Tandem")
        self.assertIsNotNone(match)
        self.assertEqual(match.course, "AP Precalculus")

    def test_missing_topic_number_fails(self):
        match = vtc.find_match(self.topics, "Unit 2 — Exponential and Logarithmic Functions")
        self.assertIsNone(match)


class ClosestCandidatesTests(unittest.TestCase):
    def test_returns_candidates_on_no_match(self):
        topics = vtc.parse_framework(FRAMEWORK_PATH)
        candidates = vtc.closest_candidates(topics, "Unit 5, Topic 5.99 — Made Up Topic")
        self.assertGreater(len(candidates), 0)
        self.assertLessEqual(len(candidates), 5)

    def test_preserves_identical_citations_from_different_courses(self):
        shared_fields = {
            "unit_num": "1",
            "unit_title": "Shared Unit",
            "topic_num": "1.1",
            "topic_title": "Shared Topic",
            "bc_only": False,
            "exam_assessed": True,
        }
        topics = [
            vtc.Topic(course="Course A", **shared_fields),
            vtc.Topic(course="Course B", **shared_fields),
        ]
        candidates = vtc.closest_candidates(
            topics, "Unit 1, Topic 1.1 — Shared Topik", n=5
        )
        self.assertEqual(len(candidates), 2)
        self.assertTrue(any(candidate.startswith("Course A") for candidate in candidates))
        self.assertTrue(any(candidate.startswith("Course B") for candidate in candidates))


class FrameworkDataValidationTests(unittest.TestCase):
    def make_topic(self, **overrides):
        fields = {
            "course": "Course A",
            "unit_num": "1",
            "unit_title": "Unit Title",
            "topic_num": "1.1",
            "topic_title": "Topic Title",
            "bc_only": False,
            "exam_assessed": True,
        }
        fields.update(overrides)
        return vtc.Topic(**fields)

    def test_reports_duplicate_topic_code_within_course(self):
        errors = vtc.framework_data_errors(
            [self.make_topic(), self.make_topic(topic_title="Different Title")]
        )
        self.assertTrue(any("duplicate topic code" in error for error in errors))

    def test_allows_same_topic_code_in_different_courses(self):
        errors = vtc.framework_data_errors(
            [self.make_topic(), self.make_topic(course="Course B")]
        )
        self.assertEqual(errors, [])

    def test_reports_topic_prefix_that_does_not_match_unit(self):
        errors = vtc.framework_data_errors(
            [self.make_topic(unit_num="2", topic_num="1.1")]
        )
        self.assertTrue(any("listed under Unit 2" in error for error in errors))


class OutputSchemaContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    def test_requires_validator_backed_metadata(self):
        required = set(self.schema["required"])
        self.assertTrue(
            {
                "course",
                "unit",
                "topic",
                "topic_exam_scope",
                "difficulty",
                "style",
                "citation_validation",
            }
            <= required
        )
        self.assertNotIn("exam_scope", self.schema["properties"])

    def test_unit_and_topic_patterns_match_catalog_fields(self):
        unit_pattern = self.schema["properties"]["unit"]["pattern"]
        topic_pattern = self.schema["properties"]["topic"]["pattern"]
        self.assertIsNotNone(re.fullmatch(unit_pattern, "Unit 10"))
        self.assertIsNone(re.fullmatch(unit_pattern, "Unit 2 — Wrong Title"))
        self.assertIsNotNone(
            re.fullmatch(topic_pattern, "2.4 Exponential Function Manipulation")
        )
        self.assertIsNone(re.fullmatch(topic_pattern, "Topic 2.4"))

    def test_schema_uses_correct_topic_example(self):
        description = self.schema["properties"]["topic"]["description"]
        self.assertIn("2.4 Exponential Function Manipulation", description)

    def test_not_assessed_scope_requires_instructional_style(self):
        scope_rules = [
            rule
            for rule in self.schema["allOf"]
            if rule.get("if", {})
            .get("properties", {})
            .get("topic_exam_scope", {})
            .get("const")
            == "not-assessed"
        ]
        self.assertEqual(len(scope_rules), 1)
        required_style = scope_rules[0]["then"]["properties"]["style"]["const"]
        self.assertEqual(required_style, "instructional")

    def test_ap_oriented_style_requires_assessed_supporting_topics(self):
        style_rules = [
            rule
            for rule in self.schema["allOf"]
            if rule.get("if", {})
            .get("properties", {})
            .get("style", {})
            .get("const")
            == "ap-oriented"
        ]
        self.assertEqual(len(style_rules), 1)
        required_scope = style_rules[0]["then"]["properties"][
            "supporting_topics"
        ]["items"]["properties"]["topic_exam_scope"]["const"]
        self.assertEqual(required_scope, "assessed")

    def test_difficulty_and_style_are_independent_axes(self):
        properties = self.schema["properties"]
        self.assertEqual(
            properties["difficulty"]["enum"],
            ["foundational", "standard", "challenge"],
        )
        self.assertEqual(
            properties["style"]["enum"],
            ["instructional", "ap-oriented"],
        )

    def test_practice_and_worked_example_requirements_differ(self):
        branches = {
            branch["if"]["properties"]["type"]["const"]: branch
            for branch in self.schema["allOf"]
            if "type" in branch.get("if", {}).get("properties", {})
        }
        practice_required = branches["practice_problem"]["then"]["properties"][
            "content"
        ]["required"]
        worked_required = branches["worked_example"]["then"]["properties"][
            "content"
        ]["required"]
        self.assertEqual(practice_required, ["problem_statement"])
        self.assertEqual(worked_required, ["problem_statement", "solution"])

    def test_citation_evidence_and_supporting_topics_are_structured(self):
        properties = self.schema["properties"]
        validation = properties["citation_validation"]
        self.assertEqual(
            set(validation["required"]), {"catalog_match", "automated_status"}
        )
        self.assertEqual(
            validation["properties"]["automated_status"]["enum"],
            ["pass", "not_run"],
        )
        supporting = properties["supporting_topics"]
        self.assertEqual(supporting["minItems"], 1)
        self.assertEqual(
            set(supporting["items"]["required"]),
            {"unit", "topic", "topic_exam_scope"},
        )


class CliTests(unittest.TestCase):
    def test_single_exact_citation_exits_zero(self):
        exit_code, stdout, stderr = run_main(
            "--course",
            "precalculus",
            "Unit 2, Topic 2.4 — Exponential Function Manipulation",
        )
        self.assertEqual(exit_code, 0)
        self.assertIn(
            "OK — matched: Unit 2, Topic 2.4 — Exponential Function Manipulation",
            stdout,
        )
        self.assertIn("META — topic_exam_scope: assessed", stdout)
        self.assertEqual(stderr, "")

    def test_evidence_json_rejects_non_ascii_suffix(self):
        query = "Unit 3, Topic 3.1 — The Chain Rule 完全错误的附加文本"
        exit_code, stdout, stderr = run_main(
            "--course",
            "calc-ab",
            "--evidence-json",
            query,
        )
        self.assertEqual(exit_code, 1)
        self.assertEqual(stderr, "")
        evidence = json.loads(stdout)
        self.assertEqual(evidence["overall_status"], "fail")
        self.assertEqual(evidence["results"][0]["status"], "fail")
        self.assertEqual(evidence["results"][0]["input"], query)
        self.assertIn("no exact match", evidence["results"][0]["message"])

    def test_multiple_citations_all_pass(self):
        exit_code, stdout, stderr = run_main(
            "--course",
            "precalculus",
            "Unit 1, Topic 1.1 — Change in Tandem",
            "Unit 2, Topic 2.4 — Exponential Function Manipulation",
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.count("OK — matched"), 2)
        self.assertEqual(stderr, "")

    def test_batch_checks_every_citation_and_exits_one_if_any_fail(self):
        exit_code, stdout, stderr = run_main(
            "--course",
            "precalculus",
            "Unit 99, Topic 2.4 — Exponential Function Manipulation",
            "Unit 1, Topic 1.1 — Change in Tandem",
        )
        self.assertEqual(exit_code, 1)
        self.assertIn("FAIL — no exact match", stdout)
        self.assertIn("OK — matched", stdout)
        self.assertEqual(stderr, "")

    def test_ap_oriented_rejects_precalculus_unit_four(self):
        exit_code, stdout, _ = run_main(
            "--course",
            "precalculus",
            "--ap-oriented",
            "Unit 4, Topic 4.1 — Parametric Functions",
        )
        self.assertEqual(exit_code, 1)
        self.assertIn("not assessed on the AP exam", stdout)

    def test_instructional_accepts_precalculus_unit_four(self):
        exit_code, stdout, _ = run_main(
            "--course",
            "precalculus",
            "Unit 4, Topic 4.1 — Parametric Functions",
        )
        self.assertEqual(exit_code, 0)
        self.assertIn("OK — matched", stdout)
        self.assertIn("META — topic_exam_scope: not-assessed", stdout)

    def test_exam_style_alias_accepts_exam_assessed_topic(self):
        exit_code, stdout, _ = run_main(
            "--course",
            "precalculus",
            "--exam-style",
            "Unit 3, Topic 3.1 — Periodic Phenomena",
        )
        self.assertEqual(exit_code, 0)
        self.assertIn("OK — matched", stdout)

    def test_calc_ab_rejects_bc_only_topic(self):
        exit_code, stdout, _ = run_main(
            "--course",
            "calc-ab",
            "Unit 6, Topic 6.11 — Integrating Using Integration by Parts",
        )
        self.assertEqual(exit_code, 1)
        self.assertIn("BC-only", stdout)

    def test_missing_framework_exits_two(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing.md"
            exit_code, stdout, stderr = run_main(
                "--framework",
                str(missing),
                "Unit 1, Topic 1.1 — Change in Tandem",
            )
        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("framework file not found", stderr)

    def test_empty_framework_data_exits_two(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            empty_framework = Path(temp_dir) / "empty.md"
            empty_framework.write_text("# Empty\n", encoding="utf-8")
            exit_code, stdout, stderr = run_main(
                "--framework",
                str(empty_framework),
                "Unit 1, Topic 1.1 — Change in Tandem",
            )
        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("no topics parsed", stderr)

    def test_partially_malformed_framework_exits_two(self):
        framework_text = """## Test Course
- Unit 1 — Valid Unit
  - 1.1 Valid Topic
  - malformed topic without a code
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            framework = Path(temp_dir) / "malformed.md"
            framework.write_text(framework_text, encoding="utf-8")
            exit_code, stdout, stderr = run_main(
                "--framework",
                str(framework),
                "Unit 1, Topic 1.1 — Valid Topic",
            )
        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("invalid framework data", stderr)
        self.assertIn("malformed topic entry", stderr)

    def test_evidence_json_reports_exact_batch_success(self):
        citations = (
            "Unit 10, Topic 10.12 — Lagrange Error Bound",
            "Unit 10, Topic 10.11 — Finding Taylor Polynomial Approximations of Functions",
        )
        exit_code, stdout, stderr = run_main(
            "--course",
            "calc-bc",
            "--ap-oriented",
            "--evidence-json",
            *citations,
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        evidence = json.loads(stdout)
        self.assertEqual(
            set(evidence),
            {
                "schema_version",
                "validator",
                "course",
                "ap_oriented",
                "overall_status",
                "results",
            },
        )
        self.assertEqual(evidence["schema_version"], 1)
        self.assertEqual(evidence["validator"], "ap-advisor-topic-code")
        self.assertEqual(evidence["course"], "calc-bc")
        self.assertIs(evidence["ap_oriented"], True)
        self.assertEqual(evidence["overall_status"], "pass")
        self.assertEqual(
            [result["citation"] for result in evidence["results"]],
            list(citations),
        )
        self.assertTrue(
            all(result["topic_exam_scope"] == "assessed" for result in evidence["results"])
        )

    def test_evidence_json_batch_failure_never_claims_overall_pass(self):
        exit_code, stdout, stderr = run_main(
            "--course",
            "precalculus",
            "--evidence-json",
            "Unit 1, Topic 1.1 — Change in Tandem",
            "Unit 99, Topic 2.4 — Exponential Function Manipulation",
        )
        self.assertEqual(exit_code, 1)
        self.assertEqual(stderr, "")
        evidence = json.loads(stdout)
        self.assertEqual(evidence["overall_status"], "fail")
        self.assertEqual(
            [result["status"] for result in evidence["results"]],
            ["pass", "fail"],
        )
        self.assertNotIn("OK — matched", stdout)

    def test_evidence_json_configuration_error_is_one_json_object(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing.md"
            exit_code, stdout, stderr = run_main(
                "--framework",
                str(missing),
                "--course",
                "calc-ab",
                "--evidence-json",
                "Unit 1, Topic 1.1 — Introducing Calculus: Can Change Occur at an Instant?",
            )
        self.assertEqual(exit_code, 2)
        self.assertEqual(stderr, "")
        evidence = json.loads(stdout)
        self.assertEqual(evidence["overall_status"], "error")
        self.assertEqual(evidence["results"], [])
        self.assertIn("framework file not found", evidence["error"])


if __name__ == "__main__":
    unittest.main()
