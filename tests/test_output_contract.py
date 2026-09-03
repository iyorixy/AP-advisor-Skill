from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "ap-calculus-advisor"


class OutputContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads(
            (SKILL_ROOT / "references" / "output-schema.json").read_text(encoding="utf-8")
        )

    def test_deprecated_style_is_not_emittable(self):
        styles = self.schema["properties"]["style"]["enum"]
        self.assertEqual(styles, ["instructional", "assessed-topic", "exam-oriented"])
        self.assertNotIn("ap-oriented", styles)

    def test_hidden_visibility_forbids_answer_and_solution_fields(self):
        branch = next(
            rule
            for rule in self.schema["allOf"]
            if rule.get("if", {}).get("properties", {}).get("answer_visibility", {}).get("const")
            == "hidden"
        )
        forbidden = {
            tuple(condition["required"])
            for condition in branch["then"]["properties"]["content"]["not"]["anyOf"]
        }
        self.assertEqual(forbidden, {("final_answer",), ("solution",)})

    def test_exam_oriented_requires_all_four_exam_features(self):
        exam_features = self.schema["properties"]["exam_features"]
        self.assertEqual(
            set(exam_features["required"]),
            {"question_type", "calculator", "representations", "justification"},
        )
        self.assertEqual(
            set(exam_features["properties"]["calculator"]["enum"]),
            {"calculator-required-section", "calculator-not-permitted"},
        )
        style_rule = next(
            rule
            for rule in self.schema["allOf"]
            if rule.get("if", {}).get("properties", {}).get("style", {}).get("const")
            == "exam-oriented"
        )
        self.assertEqual(style_rule["else"], {"not": {"required": ["exam_features"]}})

    def test_machine_error_contract_is_strict(self):
        error_schema = json.loads(
            (SKILL_ROOT / "references" / "machine-error-schema.json").read_text(encoding="utf-8")
        )
        self.assertIs(error_schema["additionalProperties"], False)
        self.assertEqual(error_schema["properties"]["status"]["const"], "cannot_fulfill")


if __name__ == "__main__":
    unittest.main()
