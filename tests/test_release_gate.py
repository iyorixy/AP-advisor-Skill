from __future__ import annotations

import importlib.util
import hashlib
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("check_release", ROOT / "scripts" / "check_release.py")
assert SPEC and SPEC.loader
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


class ReleaseGateTests(unittest.TestCase):
    def test_blind_manifest_must_match_review_context_and_digest(self):
        records = []
        reviews = []
        for index in range(50):
            case_id = f"REV-{index + 1:03d}" if index < 40 else f"REV-{index - 39:03d}"
            round_id = "primary" if index < 40 else "repeat"
            record = {
                "case_id": case_id,
                "round_id": round_id,
                "forward_context_id": f"forward-{index}",
                "raw_output_sha256": hashlib.sha256(str(index).encode()).hexdigest(),
            }
            records.append(record)
            reviews.append(dict(record))
        manifest = {
            "schema_version": 1,
            "raw_output_directory_id": "ap-calculus-final-forward-fixture",
            "created_at": "2026-08-31T15:00:00Z",
            "source_manifest_sha256": "a" * 64,
            "aggregate_sha256": hashlib.sha256(
                json.dumps(records, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            "records": records,
        }
        evidence = gate._validate_blind_manifest(manifest, reviews)
        self.assertEqual(evidence["unique_forward_context_count"], 50)
        reviews[0]["raw_output_sha256"] = "b" * 64
        with self.assertRaisesRegex(gate.ReleaseError, "provenance does not match"):
            gate._validate_blind_manifest(manifest, reviews)

    def test_regression_summary_rejects_loss_of_a_baseline_pass(self):
        blind = {
            "source_manifest_sha256": "c" * 64,
            "records": [
                {"forward_context_id": f"blind-{index}"} for index in range(50)
            ],
        }
        entries = []
        for index in range(16):
            entries.append({
                "case_id": f"legacy-{index}",
                "forward_context_id": f"regression-{index}",
                "baseline_passed": index < 12,
                "final_passed": index < 12,
                "final_raw_output_sha256": hashlib.sha256(str(index).encode()).hexdigest(),
                "evidence": "Independent fixed-rubric regression evidence.",
            })
        summary = {
            "schema_version": 1,
            "baseline_snapshot_id": "ap-calculus-baseline-fixture",
            "baseline_review_sha256": "a" * 64,
            "final_forward_source_manifest_sha256": "c" * 64,
            "reviewer_context_id": "independent-regression-reviewer",
            "reviewer_independent": True,
            "case_count": 16,
            "baseline_passed": 12,
            "final_passed": 12,
            "retained_baseline_passes": 12,
            "regressed_case_ids": [],
            "improved_case_ids": [],
            "failed_case_ids": [f"legacy-{index}" for index in range(12, 16)],
            "overall_status": "pass",
            "cases": entries,
        }
        evidence = gate._validate_regression_summary(summary, blind)
        self.assertEqual(evidence["retained_baseline_passes"], 12)
        summary["cases"][0]["final_passed"] = False
        summary["final_passed"] = 11
        summary["retained_baseline_passes"] = 11
        summary["regressed_case_ids"] = ["legacy-0"]
        summary["failed_case_ids"] = ["legacy-0", *summary["failed_case_ids"]]
        summary["overall_status"] = "fail"
        with self.assertRaisesRegex(gate.ReleaseError, "did not pass"):
            gate._validate_regression_summary(summary, blind)

    def test_math_audit_digest_rejects_wrong_main_answer_with_unrelated_true_check(self):
        item = {
            "item_id": "ITEM",
            "answer": "The primary answer is 2.",
            "verification": {"independent_checks": [{"check_id": "sum-check"}]},
        }
        raw = json.dumps(item, separators=(",", ":"))
        artifact = (raw + "\n").encode("utf-8")
        manifest = {
            "schema_version": 1,
            "artifact": "references/diagnostic-items.jsonl",
            "artifact_sha256": hashlib.sha256(artifact).hexdigest(),
            "hash_algorithm": "sha256",
            "author_context_id": "bank-author",
            "reviewer_context_id": "independent-math-reviewer",
            "independent_from_authoring": True,
            "reviewed_at": "2026-08-31T12:00:00Z",
            "entries": [{
                "item_id": "ITEM",
                "line_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                "verdict": "pass",
                "checked_answer": "The primary answer is 2.",
                "checked_check_ids": ["sum-check"],
                "math_notes": "The independent computation supports the complete primary answer.",
            }],
        }
        mutated = json.loads(raw)
        mutated["answer"] = "The primary answer is 999; an unrelated fact is 1+1=2."
        mutated_raw = json.dumps(mutated, separators=(",", ":"))
        mutated_artifact = (mutated_raw + "\n").encode("utf-8")
        with self.assertRaisesRegex(gate.ReleaseError, "artifact digest"):
            gate._validate_math_audit(
                manifest,
                {"ITEM": mutated},
                [mutated_raw],
                mutated_artifact,
            )

    def test_verification_evaluator_supports_only_bounded_math(self):
        self.assertAlmostEqual(gate._evaluate("sqrt(9) + sin(pi / 2)"), 4.0)
        self.assertIs(gate._evaluate("(3 < 4) and (2**3 == 8)"), True)
        with self.assertRaisesRegex(gate.ReleaseError, "forbidden syntax"):
            gate._evaluate("__import__('os').getcwd()")
        with self.assertRaisesRegex(gate.ReleaseError, "exponent"):
            gate._evaluate("2**100")
        with self.assertRaisesRegex(gate.ReleaseError, "could not be evaluated"):
            gate._evaluate("1/0")
        with self.assertRaisesRegex(gate.ReleaseError, "could not be evaluated"):
            gate._evaluate("sqrt(-1)")

    def test_incorrect_machine_math_check_is_rejected(self):
        verification = {
            "method": "exact-arithmetic",
            "independent_checks": [
                {
                    "check_id": "wrong-sum",
                    "expression": "2 + 3",
                    "expected": 6,
                    "tolerance": 0,
                    "answer_claim": "answer is 6",
                }
            ],
            "human_checkpoints": [
                "The exact arithmetic was derived independently.",
                "The problem domain and units were checked separately.",
            ],
        }
        with self.assertRaisesRegex(gate.ReleaseError, "evaluated to"):
            gate._validate_verification(
                verification,
                "ITEM",
                "The exact answer is 6.",
                "The answer is 6 after the stated computation.",
            )

    def test_machine_check_must_bind_to_the_answer_or_solution(self):
        verification = {
            "method": "exact-arithmetic",
            "independent_checks": [
                {
                    "check_id": "unbound",
                    "expression": "2 + 3",
                    "expected": 5,
                    "tolerance": 0,
                    "answer_claim": "the checked result is 5",
                }
            ],
            "human_checkpoints": [
                "The exact arithmetic was derived independently.",
                "The problem domain and units were checked separately.",
            ],
        }
        with self.assertRaisesRegex(gate.ReleaseError, "not bound"):
            gate._validate_verification(
                verification,
                "ITEM",
                "The answer claims a different result.",
                "This solution omits the checked claim.",
            )

    def test_compile_check_uses_only_standard_library(self):
        receipt = gate.compile_and_check_imports()
        self.assertTrue(receipt["stdlib_only"])
        self.assertGreater(receipt["compiled_file_count"], 0)

    def test_json_command_with_empty_stdout_cannot_pass(self):
        receipt = gate._command_receipt(
            "empty-json",
            [sys.executable, "-c", "pass"],
            json_receipt=True,
        )
        self.assertEqual(receipt["exit_code"], 0)
        self.assertEqual(receipt["status"], "fail")
        self.assertIn("no JSON", receipt["error"])

    def test_unittest_receipt_rejects_skipped_tests(self):
        receipt = gate._command_receipt(
            "unittest",
            [
                sys.executable,
                "-c",
                "import sys; sys.stderr.write('Ran 68 tests in 0.5s\\n\\nOK (skipped=1)\\n')",
            ],
        )
        self.assertEqual(receipt["status"], "fail")
        self.assertEqual(receipt["skipped_test_count"], 1)
        self.assertIn("skipped", receipt["error"])

    def test_json_command_with_array_stdout_cannot_crash_or_pass(self):
        receipt = gate._command_receipt(
            "array-json",
            [sys.executable, "-c", "print('[]')"],
            json_receipt=True,
        )
        self.assertEqual(receipt["exit_code"], 0)
        self.assertEqual(receipt["status"], "fail")
        self.assertIn("one object", receipt["error"])

    def test_command_receipt_uses_utf8_for_non_ascii_child_output(self):
        receipt = gate._command_receipt(
            "utf8-output",
            [sys.executable, "-c", "print('路径安全')"],
        )
        self.assertEqual(receipt["exit_code"], 0)
        self.assertEqual(receipt["status"], "pass")


if __name__ == "__main__":
    unittest.main()
