from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("run_evals", ROOT / "scripts" / "run_evals.py")
assert SPEC and SPEC.loader
evals = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evals)


class EvalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = evals.load_cases(ROOT / "evals" / "cases.jsonl")

    def reviews(self):
        result = []
        for index, (case_id, case) in enumerate(self.cases.items()):
            result.append(self.review(case_id, case, "primary", f"primary-{index}"))
        for index, case_id in enumerate(evals.repeat_case_ids(self.cases)):
            result.append(self.review(case_id, self.cases[case_id], "repeat", f"repeat-{index}"))
        return result

    @staticmethod
    def review(case_id, case, round_id, context_id):
        return {
            "schema_version": 1,
            "case_id": case_id,
            "round_id": round_id,
            "forward_context_id": context_id,
            "forward_context_independent": True,
            "rubric_hidden_from_forward_tester": True,
            "reviewer_context_id": "independent-reviewer",
            "reviewer_independent": True,
            "raw_output_sha256": hashlib.sha256(context_id.encode()).hexdigest(),
            "reviewed_at": "2026-08-31T12:00:00Z",
            "invariants": [
                {
                    "invariant_id": invariant["invariant_id"],
                    "passed": True,
                    "evidence": "A complete semantic review supports this judgment.",
                }
                for invariant in case["semantic_rubric_invariants"]
            ],
        }

    def write_reviews(self, values):
        temporary = tempfile.TemporaryDirectory()
        path = Path(temporary.name) / "reviews.jsonl"
        path.write_text(
            "".join(json.dumps(value) + "\n" for value in values),
            encoding="utf-8",
        )
        return temporary, path

    def test_case_contract_has_required_coverage(self):
        self.assertEqual(len(self.cases), 40)
        self.assertEqual(
            {case["unit"] for case in self.cases.values() if case["unit"] is not None},
            set(range(1, 9)),
        )

    def test_complete_reviews_pass_fixed_thresholds(self):
        temporary, path = self.write_reviews(self.reviews())
        self.addCleanup(temporary.cleanup)
        reviews = evals.load_reviews(path, self.cases)
        receipt = evals.score(self.cases, reviews)
        self.assertEqual(receipt["overall_status"], "pass")
        self.assertTrue(all(receipt["thresholds"].values()))

    def test_failed_critical_invariant_blocks_release(self):
        reviews = self.reviews()
        reviews[0]["invariants"][0]["passed"] = False
        receipt = evals.score(self.cases, reviews)
        self.assertEqual(receipt["overall_status"], "fail")
        self.assertTrue(receipt["failed_invariants"])
        self.assertFalse(receipt["thresholds"]["all_critical_invariants_pass"])

    def test_incomplete_review_is_rejected(self):
        reviews = self.reviews()
        reviews[0]["invariants"].pop()
        temporary, path = self.write_reviews(reviews)
        self.addCleanup(temporary.cleanup)
        with self.assertRaisesRegex(evals.EvalError, "exact case invariants"):
            evals.load_reviews(path, self.cases)

    def test_reused_forward_context_is_rejected(self):
        reviews = self.reviews()
        reviews[1]["forward_context_id"] = reviews[0]["forward_context_id"]
        temporary, path = self.write_reviews(reviews)
        self.addCleanup(temporary.cleanup)
        with self.assertRaisesRegex(evals.EvalError, "reused"):
            evals.load_reviews(path, self.cases)

    def test_reviewer_context_cannot_be_any_forward_context(self):
        reviews = self.reviews()
        reviews[0]["reviewer_context_id"] = reviews[1]["forward_context_id"]
        temporary, path = self.write_reviews(reviews)
        self.addCleanup(temporary.cleanup)
        with self.assertRaisesRegex(evals.EvalError, "sets overlap"):
            evals.load_reviews(path, self.cases)

    def test_model_self_claim_cannot_replace_invariant_judgments(self):
        reviews = self.reviews()
        reviews[0]["invariants"] = "overall_status: pass"
        temporary, path = self.write_reviews(reviews)
        self.addCleanup(temporary.cleanup)
        with self.assertRaisesRegex(evals.EvalError, "array"):
            evals.load_reviews(path, self.cases)


if __name__ == "__main__":
    unittest.main()
