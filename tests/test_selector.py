from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "ap-calculus-advisor"
SPEC = importlib.util.spec_from_file_location(
    "select_next_task", SKILL_ROOT / "scripts" / "select_next_task.py"
)
assert SPEC and SPEC.loader
selector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(selector)

AS_OF = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)


def item(
    item_id,
    topic,
    misconception,
    stage,
    *,
    unit,
    representation,
    priority,
    difficulty="standard",
    course="calc-ab",
):
    return {
        "schema_version": 1,
        "item_id": item_id,
        "course": course,
        "unit": unit,
        "topic_code": topic,
        "topic_citation": f"Unit {unit}, Topic {topic} — Test fixture",
        "mathematical_practice": (
            "precalc-1-procedural-symbolic-fluency"
            if course == "precalculus"
            else "calc-1-implementing-processes"
        ),
        "task_type": "free-response",
        "representation": representation,
        "calculator_condition": "calculator-not-permitted",
        "justification_requirement": "not-required",
        "difficulty": {
            "label": difficulty,
            "status": "provisional",
            "observable_basis": "Fixture path length and representation demand.",
        },
        "prerequisites": [],
        "target_misconceptions": [misconception],
        "prompt": "Original fixture prompt whose answer is intentionally hidden.",
        "answer": "SECRET-ANSWER",
        "solution": "SECRET-SOLUTION",
        "hint_ladder": ["SECRET-HINT"],
        "distractor_diagnoses": {},
        "error_response_diagnoses": {"fixture": "diagnosis"},
        "same_form_confirmation_item_id": f"{item_id}-CONFIRM",
        "transfer_item_id": f"{item_id}-TRANSFER",
        "answer_visibility": "hidden",
        "selection": {
            "stage": stage,
            "priority": priority,
            "expected_time_seconds": 120,
            "exit_eligible": stage in {"transfer", "retest"},
            "representation_family": representation,
            "context_family": f"context-{misconception}",
        },
    }


def misconception(
    identifier,
    topic,
    diagnostic,
    confirmation,
    transfer,
    *,
    unit,
    prerequisites=None,
    course="calc-ab",
):
    return {
        "misconception_id": identifier,
        "course": course,
        "internal_diagnostic": True,
        "unit": unit,
        "topic": topic,
        "practice": (
            "precalc-1-procedural-symbolic-fluency"
            if course == "precalculus"
            else "calc-1-implementing-processes"
        ),
        "observable_features": ["Observable fixture error."],
        "evidence_required": ["One complete worked response."],
        "alternative_causes": ["A transcription error."],
        "prerequisites": prerequisites or [],
        "prerequisite_rationale": {
            prerequisite: "This maintained prerequisite is needed before the target process."
            for prerequisite in (prerequisites or [])
        },
        "minimum_remediation": "One bounded correction and explanation.",
        "diagnostic_item_id": diagnostic,
        "confirmation_item_id": confirmation,
        "transfer_item_id": transfer,
        "exit_standard": "Pass one unseen transfer independently at hint level 0.",
        "uncertain_action": "Collect one discriminating worked response.",
    }


def topic_state(topic, *, misconception_id=None, confidence="unknown", status="provisional", correctness="incorrect", source="I-B-D", hint=0, independence="independent", completion=60, learner_confidence="medium"):
    return {
        "topic": topic,
        "practice": "calc-1-implementing-processes",
        "evidence_count": 1,
        "correctness": correctness,
        "completion_time_seconds": completion,
        "confidence": learner_confidence,
        "source_item_id": source,
        "status": status,
        "last_observed_at": "2026-08-31T10:00:00Z",
        "next_review_at": None,
        "observed_error": "fixture observation",
        "hypothesized_misconception": misconception_id,
        "diagnostic_confidence": confidence,
        "independence": independence,
        "hint_level": hint,
        "same_form_confirmation": "pass" if status == "needs-confirmation" else "not_attempted",
        "transfer_result": "not_attempted",
        "transfer_item_unseen": None,
    }


def state(*, seen=None, topics=None, queue=None, course="calc-ab"):
    return {
        "schema_version": 1,
        "profile_id": "fixture",
        "course": course,
        "attempt_ids": [],
        "seen_item_ids": seen or [],
        "topic_states": topics or {},
        "review_queue": queue or [],
        "updated_at": "2026-08-31T12:00:00Z",
    }


class SelectorTests(unittest.TestCase):
    def setUp(self):
        records = [
            item("I-A-D", "1.6", "M-A", "diagnostic", unit=1, representation="analytical", priority=20, difficulty="foundational"),
            item("I-A-C", "1.6", "M-A", "confirmation", unit=1, representation="analytical", priority=10),
            item("I-A-T", "1.6", "M-A", "transfer", unit=1, representation="tabular", priority=10),
            item("I-A-R", "1.6", "M-A", "retest", unit=1, representation="graphical", priority=10),
            item("I-B-D", "2.8", "M-B", "diagnostic", unit=2, representation="analytical", priority=10, difficulty="foundational"),
            item("I-B-C", "2.8", "M-B", "confirmation", unit=2, representation="analytical", priority=10),
            item("I-B-T", "2.8", "M-B", "transfer", unit=2, representation="verbal", priority=10),
        ]
        self.items = {record["item_id"]: record for record in records}
        self.misconceptions = {
            "M-A": misconception("M-A", "1.6", "I-A-D", "I-A-C", "I-A-T", unit=1),
            "M-B": misconception("M-B", "2.8", "I-B-D", "I-B-C", "I-B-T", unit=2, prerequisites=["M-A"]),
        }

    def select(self, profile):
        return selector.select_next(profile, self.items, self.misconceptions, as_of=AS_OF)

    def test_same_input_and_as_of_are_deterministic(self):
        profile = state()
        self.assertEqual(self.select(profile), self.select(json.loads(json.dumps(profile))))

    def test_unknown_state_uses_foundational_stable_order(self):
        receipt = self.select(state())
        self.assertEqual(receipt["item_id"], "I-A-D")
        self.assertEqual(receipt["uncertainty"], "high")

    def test_precalculus_profile_selects_only_precalculus_items(self):
        record = item(
            "PC-I-D",
            "1.1",
            "PC-M",
            "diagnostic",
            unit=1,
            representation="analytical",
            priority=1,
            difficulty="foundational",
            course="precalculus",
        )
        self.items[record["item_id"]] = record
        self.misconceptions["PC-M"] = misconception(
            "PC-M", "1.1", "PC-I-D", "PC-I-C", "PC-I-T", unit=1, course="precalculus"
        )
        receipt = self.select(state(course="precalculus"))
        self.assertEqual(receipt["item_id"], "PC-I-D")
        self.assertNotIn("I-A-D", json.dumps(receipt))

    def test_calc_bc_inherits_ab_and_selects_bc_only_after_ab_is_seen(self):
        ab_ids = sorted(self.items)
        record = item(
            "BC-I-D",
            "9.2",
            "BC-M",
            "diagnostic",
            unit=9,
            representation="numerical",
            priority=1,
            difficulty="foundational",
            course="calc-bc",
        )
        self.items[record["item_id"]] = record
        self.misconceptions["BC-M"] = misconception(
            "BC-M", "9.2", "BC-I-D", "BC-I-C", "BC-I-T", unit=9, course="calc-bc"
        )
        self.assertEqual(self.select(state(course="calc-bc"))["item_id"], "I-A-D")
        self.assertEqual(
            self.select(state(course="calc-bc", seen=ab_ids))["item_id"], "BC-I-D"
        )
        self.assertIsNone(self.select(state(course="calc-ab", seen=ab_ids))["item_id"])

    def test_shipped_bank_routes_precalculus_and_bc_only_items(self):
        items = selector.load_items(
            SKILL_ROOT / "references" / "diagnostic-items.jsonl"
        )
        misconceptions = selector.load_misconceptions(
            SKILL_ROOT / "references" / "calculus-misconceptions.json"
        )
        precalculus = selector.select_next(
            state(course="precalculus"), items, misconceptions, as_of=AS_OF
        )
        self.assertEqual(items[precalculus["item_id"]]["course"], "precalculus")
        inherited_ab = [
            item_id for item_id, record in items.items() if record["course"] == "calc-ab"
        ]
        bc_only = selector.select_next(
            state(course="calc-bc", seen=inherited_ab),
            items,
            misconceptions,
            as_of=AS_OF,
        )
        self.assertEqual(items[bc_only["item_id"]]["course"], "calc-bc")

    def test_equal_priority_tie_break_uses_item_id(self):
        extra = item(
            "I-A-E",
            "1.6",
            "M-A",
            "diagnostic",
            unit=1,
            representation="analytical",
            priority=20,
            difficulty="foundational",
        )
        self.items[extra["item_id"]] = extra
        self.assertEqual(self.select(state())["item_id"], "I-A-D")

    def test_due_retest_has_priority(self):
        profile = state(
            queue=[{
                "review_id": "review-1",
                "topic": "1.6",
                "misconception_id": "M-A",
                "item_id": "I-A-R",
                "reason": "delayed-retest",
                "due_at": "2026-08-31T11:00:00Z",
                "status": "pending",
            }]
        )
        self.assertEqual(self.select(profile)["item_id"], "I-A-R")

    def test_due_queue_item_must_match_its_topic_and_misconception(self):
        profile = state(
            queue=[{
                "review_id": "review-corrupt",
                "topic": "1.6",
                "misconception_id": "M-A",
                "item_id": "I-B-T",
                "reason": "delayed-retest",
                "due_at": "2026-08-31T11:00:00Z",
                "status": "pending",
            }]
        )
        with self.assertRaisesRegex(selector.SelectionError, "does not match"):
            self.select(profile)

    def test_due_queue_reason_selects_the_correct_stage(self):
        base = {
            "review_id": "review-stage",
            "topic": "1.6",
            "misconception_id": "M-A",
            "item_id": None,
            "due_at": "2026-08-31T11:00:00Z",
            "status": "pending",
        }
        confirm = self.select(state(seen=["I-A-D"], queue=[{**base, "reason": "same-form-confirmation"}]))
        self.assertEqual(confirm["item_id"], "I-A-C")
        transfer = self.select(
            state(
                seen=["I-A-D", "I-A-C"],
                queue=[{**base, "review_id": "review-transfer", "reason": "transfer"}],
            )
        )
        self.assertEqual(transfer["item_id"], "I-A-T")

    def test_due_evidence_needed_without_misconception_stays_on_due_topic(self):
        profile = state(
            topics={"2.8": topic_state("2.8", source="I-B-D")},
            queue=[{
                "review_id": "review-topic-only",
                "topic": "2.8",
                "misconception_id": None,
                "item_id": None,
                "reason": "evidence-needed",
                "due_at": "2026-08-31T11:00:00Z",
                "status": "pending",
            }],
        )
        receipt = self.select(profile)
        self.assertEqual(receipt["item_id"], "I-B-D")
        self.assertIn("takes priority", receipt["selection_reason"])

    def test_exhausted_topic_only_due_review_does_not_substitute_global_item(self):
        profile = state(
            seen=["I-B-D"],
            topics={"2.8": topic_state("2.8", source="I-B-D")},
            queue=[{
                "review_id": "review-topic-only-exhausted",
                "topic": "2.8",
                "misconception_id": None,
                "item_id": None,
                "reason": "evidence-needed",
                "due_at": "2026-08-31T11:00:00Z",
                "status": "pending",
            }],
        )
        receipt = self.select(profile)
        self.assertIsNone(receipt["item_id"])
        self.assertIn("no unseen maintained item", receipt["selection_reason"])
        self.assertNotIn("I-A-D", json.dumps(receipt))

    def test_explicit_due_item_stage_must_match_queue_reason(self):
        profile = state(
            queue=[{
                "review_id": "review-wrong-stage",
                "topic": "1.6",
                "misconception_id": "M-A",
                "item_id": "I-A-D",
                "reason": "transfer",
                "due_at": "2026-08-31T11:00:00Z",
                "status": "pending",
            }]
        )
        with self.assertRaisesRegex(selector.SelectionError, "stage contradicts"):
            self.select(profile)

    def test_future_retest_does_not_preempt_current_diagnostic(self):
        profile = state(
            queue=[{
                "review_id": "review-future",
                "topic": "1.6",
                "misconception_id": "M-A",
                "item_id": "I-A-R",
                "reason": "delayed-retest",
                "due_at": "2026-09-01T11:00:00Z",
                "status": "pending",
            }]
        )
        self.assertEqual(self.select(profile)["item_id"], "I-A-D")

    def test_due_known_misconception_without_unseen_item_does_not_substitute_global_item(self):
        profile = state(
            seen=["I-A-D", "I-A-C", "I-A-T", "I-A-R"],
            topics={"1.6": topic_state("1.6", misconception_id="M-A", confidence="high")},
            queue=[{
                "review_id": "review-exhausted",
                "topic": "1.6",
                "misconception_id": "M-A",
                "item_id": None,
                "reason": "delayed-retest",
                "due_at": "2026-08-31T11:00:00Z",
                "status": "pending",
            }],
        )
        receipt = self.select(profile)
        self.assertIsNone(receipt["item_id"])
        self.assertIn("no unseen maintained item", receipt["selection_reason"])
        self.assertNotIn("I-B-D", json.dumps(receipt))

    def test_explicit_unmet_prerequisite_is_selected_first(self):
        profile = state(
            seen=["I-B-D"],
            topics={"2.8": topic_state("2.8", misconception_id="M-B", confidence="high")},
        )
        receipt = self.select(profile)
        self.assertEqual(receipt["item_id"], "I-A-D")
        self.assertIn("prerequisite", receipt["selection_reason"])

    def test_high_confidence_hypothesis_gets_same_form_confirmation(self):
        profile = state(
            seen=["I-A-D"],
            topics={"1.6": topic_state("1.6", misconception_id="M-A", confidence="high", source="I-A-D")},
        )
        self.assertEqual(self.select(profile)["item_id"], "I-A-C")

    def test_same_form_pass_moves_to_transfer(self):
        profile = state(
            seen=["I-A-D", "I-A-C"],
            topics={
                "1.6": topic_state(
                    "1.6",
                    misconception_id="M-A",
                    confidence="high",
                    status="needs-confirmation",
                    correctness="correct",
                    source="I-A-C",
                )
            },
        )
        self.assertEqual(self.select(profile)["item_id"], "I-A-T")

    def test_hinted_correct_response_gets_unseen_same_form_confirmation(self):
        profile = state(
            seen=["I-A-D"],
            topics={
                "1.6": topic_state(
                    "1.6",
                    correctness="correct",
                    source="I-A-D",
                    hint=2,
                    independence="assisted",
                )
            },
        )
        receipt = self.select(profile)
        self.assertEqual(receipt["item_id"], "I-A-C")
        self.assertIn("assistance", receipt["current_evidence"][0])

    def test_slow_correct_response_gets_changed_representation_without_pacing_claim(self):
        profile = state(
            seen=["I-A-D"],
            topics={
                "1.6": topic_state(
                    "1.6",
                    correctness="correct",
                    source="I-A-D",
                    hint=0,
                    independence="independent",
                    completion=180,
                )
            },
        )
        receipt = self.select(profile)
        self.assertEqual(receipt["item_id"], "I-A-R")
        self.assertEqual(receipt["uncertainty"], "high")
        self.assertNotIn("pacing", json.dumps(receipt).lower())

    def test_all_seen_returns_explicit_no_candidate(self):
        receipt = self.select(state(seen=sorted(self.items)))
        self.assertIsNone(receipt["item_id"])
        self.assertIn("unavailable", receipt["selection_reason"])

    def test_receipt_never_contains_answer_solution_or_hint_content(self):
        serialized = json.dumps(self.select(state()))
        self.assertNotIn("SECRET-ANSWER", serialized)
        self.assertNotIn("SECRET-SOLUTION", serialized)
        self.assertNotIn("SECRET-HINT", serialized)

    def test_loader_rejects_a_fabricated_passed_status(self):
        profile = state(
            topics={"1.6": topic_state("1.6", status="passed", correctness="incorrect")}
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "profile.json"
            path.write_text(json.dumps(profile), encoding="utf-8")
            with self.assertRaisesRegex(selector.SelectionError, "contradicts"):
                selector.load_state(path)

    def test_loader_rejects_fabricated_same_form_confirmation_status(self):
        profile = state(
            topics={
                "1.6": topic_state(
                    "1.6",
                    status="needs-confirmation",
                    correctness="incorrect",
                    independence="assisted",
                    hint=3,
                )
            }
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "profile.json"
            path.write_text(json.dumps(profile), encoding="utf-8")
            with self.assertRaisesRegex(selector.SelectionError, "contradicts"):
                selector.load_state(path)

    def test_loader_rejects_topic_and_practice_outside_profile_course(self):
        profiles = (
            (
                state(
                    course="precalculus",
                    topics={"10.1": topic_state("10.1")},
                ),
                "invalid for precalculus",
            ),
            (
                state(
                    course="precalculus",
                    topics={"1.1": topic_state("1.1")},
                ),
                "invalid practice for precalculus",
            ),
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "profile.json"
            for profile, error in profiles:
                with self.subTest(error=error):
                    path.write_text(json.dumps(profile), encoding="utf-8")
                    with self.assertRaisesRegex(selector.SelectionError, error):
                        selector.load_state(path)


if __name__ == "__main__":
    unittest.main()
