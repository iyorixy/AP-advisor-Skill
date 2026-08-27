"""Regression tests for the dependency-free AP Topic/content validator."""

import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
import unicodedata
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "validate_topic_code.py"
FRAMEWORK = REPO_ROOT / "references" / "ap-calc-framework.md"
BOUNDARIES = REPO_ROOT / "references" / "ap-content-boundaries.json"
SCHEMA = REPO_ROOT / "references" / "output-schema.json"

spec = importlib.util.spec_from_file_location("validate_topic_code", SCRIPT)
assert spec and spec.loader
validator = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = validator
spec.loader.exec_module(validator)


CHAIN_RULE = "Unit 3, Topic 3.1 — The Chain Rule"
INTEGRATION_BY_PARTS = (
    "Unit 6, Topic 6.11 — Integrating Using Integration by Parts"
)


def run_main(*arguments: str) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = validator.main(list(arguments))
    return code, stdout.getvalue(), stderr.getvalue()


def fullwidth_ascii(value: str) -> str:
    return "".join(
        chr(ord(character) + 0xFEE0)
        if "!" <= character <= "~"
        else "\u3000"
        if character == " "
        else character
        for character in value
    )


class ExactCitationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.topics = validator.parse_framework(FRAMEWORK)
        cls.calculus = validator.filter_by_course(cls.topics, "calc-bc")

    def test_catalog_round_trips_by_entire_citation(self):
        for topic in self.topics:
            with self.subTest(topic=topic.citation):
                pool = validator.filter_by_course(
                    self.topics,
                    "precalculus" if topic.course.startswith("AP Precalculus") else "calc-bc",
                )
                self.assertEqual(validator.find_match(pool, topic.citation), topic)

    def test_nfkc_accepts_fullwidth_input(self):
        query = fullwidth_ascii(CHAIN_RULE)
        self.assertEqual(unicodedata.normalize("NFKC", query), CHAIN_RULE)
        self.assertEqual(validator.find_match(self.calculus, query).citation, CHAIN_RULE)

    def test_rejects_letters_inserted_before_inside_or_after_citation(self):
        bad = (
            "夹" + CHAIN_RULE,
            CHAIN_RULE.replace("Chain", "Ch夹ain"),
            CHAIN_RULE + "夹",
        )
        for query in bad:
            with self.subTest(query=query):
                self.assertIsNone(validator.find_match(self.calculus, query))

    def test_rejects_wrong_suffix_even_when_catalog_text_is_a_prefix(self):
        for suffix in (".", " (BC)", " extra"):
            with self.subTest(suffix=suffix):
                self.assertIsNone(
                    validator.find_match(self.calculus, CHAIN_RULE + suffix)
                )

    def test_nfkc_is_the_only_normalization(self):
        self.assertIsNone(
            validator.find_match(self.calculus, CHAIN_RULE.lower())
        )
        self.assertIsNone(
            validator.find_match(
                self.calculus, CHAIN_RULE.replace(",", "").replace("—", "-")
            )
        )


class CourseAndScopeTests(unittest.TestCase):
    def test_calc_ab_rejects_bc_only_topic(self):
        code, evidence = validator.validate_citations(
            [INTEGRATION_BY_PARTS], course="calc-ab"
        )
        self.assertEqual(code, 1)
        self.assertIn("BC-only", evidence["results"][0]["message"])

    def test_precalculus_unit_4_rejected_as_assessed_topic(self):
        citation = "Unit 4, Topic 4.10 — Matrices"
        self.assertEqual(
            validator.validate_citations([citation], course="precalculus")[0], 0
        )
        self.assertEqual(
            validator.validate_citations(
                [citation], course="precalculus", assessed_topic=True
            )[0],
            1,
        )

    def test_ap_oriented_is_only_a_cli_alias(self):
        canonical = run_main(
            "--course", "calc-ab", "--assessed-topic", "--evidence-json", CHAIN_RULE
        )
        legacy = run_main(
            "--course", "calc-ab", "--ap-oriented", "--evidence-json", CHAIN_RULE
        )
        self.assertEqual(canonical[0], legacy[0])
        self.assertEqual(json.loads(canonical[1]), json.loads(legacy[1]))
        self.assertNotIn("ap_oriented", json.loads(legacy[1]))


class ContentBoundaryTests(unittest.TestCase):
    def test_boundary_data_has_traceable_official_sources(self):
        data = validator.load_boundaries(BOUNDARIES)
        self.assertEqual(data["source_checked_at"], "2026-08-27")
        self.assertTrue(data["sources"])
        self.assertTrue(
            all(source["url"].startswith("https://apcentral.collegeboard.org/") for source in data["sources"])
        )

    def test_ap_ab_cannot_use_integration_by_parts(self):
        failures = validator.validate_content_boundary(
            course="calc-ab",
            content_topic="6.9",
            methods=["integration-by-parts"],
            mathematical_practices=["calc-1-implementing-processes"],
        )
        self.assertTrue(any("BC-only" in failure for failure in failures))

    def test_bc_shell_method_cannot_map_to_disc_or_washer(self):
        for topic in ("8.9", "8.10", "8.11", "8.12"):
            with self.subTest(topic=topic):
                failures = validator.validate_content_boundary(
                    course="calc-bc",
                    content_topic=topic,
                    methods=["shell-method"],
                    mathematical_practices=["calc-2-connecting-representations"],
                )
                self.assertTrue(any("excluded" in item for item in failures))

    def test_content_topic_and_mathematical_practice_are_independent(self):
        failures = validator.validate_content_boundary(
            course="precalculus",
            content_topic="2.4",
            mathematical_practices=["calc-3-justification"],
        )
        self.assertIn("invalid for precalculus", failures[0])

    def test_lagrange_boundary_requires_taylor_support(self):
        self.assertTrue(
            validator.validate_content_boundary(
                course="calc-bc", content_topic="10.12"
            )
        )
        self.assertEqual(
            validator.validate_content_boundary(
                course="calc-bc",
                content_topic="10.12",
                supporting_topics=["10.11"],
            ),
            [],
        )


class JsonAndExitCodeTests(unittest.TestCase):
    def test_success_and_content_failure_exit_codes(self):
        self.assertEqual(run_main("--evidence-json", CHAIN_RULE)[0], 0)
        self.assertEqual(run_main("--evidence-json", CHAIN_RULE + "x")[0], 1)

    def test_configuration_error_is_json_and_exit_two(self):
        missing = REPO_ROOT / "references" / "missing-framework.md"
        code, stdout, stderr = run_main(
            "--framework", str(missing), "--evidence-json", CHAIN_RULE
        )
        self.assertEqual(code, 2)
        self.assertEqual(stderr, "")
        evidence = json.loads(stdout)
        self.assertEqual(evidence["overall_status"], "error")
        self.assertIn("could not load framework", evidence["error"])

    def test_unicode_json_survives_real_process_and_exit_code(self):
        query = CHAIN_RULE + "夹"
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "--evidence-json", query],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            check=False,
        )
        self.assertEqual(completed.returncode, 1)
        evidence = json.loads(completed.stdout)
        self.assertEqual(evidence["results"][0]["input"], query)
        self.assertEqual(completed.stderr, "")

    def test_malformed_utf8_framework_is_exit_two(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.md"
            path.write_bytes(b"\xff")
            code, evidence = validator.validate_citations(
                [CHAIN_RULE], framework_path=path
            )
        self.assertEqual(code, 2)
        self.assertEqual(evidence["overall_status"], "error")

    def test_output_schema_uses_canonical_style_and_practice_dimension(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        style = schema["properties"]["style"]["enum"]
        self.assertIn("assessed-topic", style)
        self.assertIn("exam-oriented", style)
        self.assertIn("ap-oriented", style)
        self.assertIn("mathematical_practices", schema["required"])
        self.assertIn("exam_features", schema["properties"])


if __name__ == "__main__":
    unittest.main()
