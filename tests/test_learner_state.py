from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "ap-calculus-advisor"
SPEC = importlib.util.spec_from_file_location(
    "update_learner_state", SKILL_ROOT / "scripts" / "update_learner_state.py"
)
assert SPEC and SPEC.loader
state = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(state)


AS_OF = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)


def attempt(**changes):
    value = {
        "schema_version": 1,
        "attempt_id": "attempt-001",
        "profile_id": "test_profile",
        "course": "calc-ab",
        "topic": "3.1",
        "practice": "calc-1-implementing-processes",
        "correctness": "correct",
        "completion_time_seconds": None,
        "confidence": "unknown",
        "observed_error": None,
        "hypothesized_misconception": None,
        "diagnostic_confidence": "unknown",
        "independence": "unknown",
        "hint_level": None,
        "same_form_confirmation": "not_attempted",
        "transfer_result": "not_attempted",
        "transfer_item_unseen": None,
        "observed_at": "2026-08-31T10:00:00Z",
        "next_review_at": None,
        "source_attempt_id": None,
        "source_item_id": "U3-CHAIN-D1",
    }
    value.update(changes)
    return value


class LearnerStateTests(unittest.TestCase):
    def new_profile(
        self, parent: str, *, test_data: bool = True, course: str = "calc-ab"
    ) -> Path:
        data_dir = state.resolve_data_dir(str(Path(parent) / "learner data"), create=True)
        state.initialize(
            data_dir, "test_profile", as_of=AS_OF, test_data=test_data, course=course
        )
        return data_dir

    def test_initializes_all_supported_courses(self):
        for course in ("precalculus", "calc-ab", "calc-bc"):
            with self.subTest(course=course), tempfile.TemporaryDirectory() as temporary:
                data_dir = self.new_profile(temporary, course=course)
                profile = json.loads(
                    (data_dir / state.PROFILE_NAME).read_text(encoding="utf-8")
                )
                self.assertEqual(profile["course"], course)

    def test_course_topic_and_practice_boundaries(self):
        valid = (
            ("precalculus", "4.10", "precalc-3-communication-reasoning"),
            ("calc-ab", "8.12", "calc-4-communication-notation"),
            ("calc-bc", "10.12", "calc-2-connecting-representations"),
        )
        for course, topic, practice in valid:
            with self.subTest(course=course):
                self.assertEqual(
                    state.validate_attempt(
                        attempt(course=course, topic=topic, practice=practice), as_of=AS_OF
                    )["topic"],
                    topic,
                )
        invalid = (
            ("precalculus", "5.1", "precalc-1-procedural-symbolic-fluency"),
            ("calc-ab", "9.1", "calc-1-implementing-processes"),
            ("calc-bc", "11.1", "calc-1-implementing-processes"),
        )
        for course, topic, practice in invalid:
            with self.subTest(course=course), self.assertRaisesRegex(
                state.StateError, "valid Topic code"
            ):
                state.validate_attempt(
                    attempt(course=course, topic=topic, practice=practice), as_of=AS_OF
                )
        with self.assertRaisesRegex(state.StateError, "practice is invalid"):
            state.validate_attempt(
                attempt(course="precalculus", topic="1.1"), as_of=AS_OF
            )

    def test_attempt_course_must_match_profile_without_append(self):
        with tempfile.TemporaryDirectory() as temporary:
            data_dir = self.new_profile(temporary, course="precalculus")
            before = (data_dir / state.ATTEMPTS_NAME).read_bytes()
            with self.assertRaisesRegex(state.StateError, "does not match profile"):
                state.record_attempt(data_dir, attempt(), as_of=AS_OF)
            self.assertEqual(before, (data_dir / state.ATTEMPTS_NAME).read_bytes())

    def test_single_correct_attempt_is_not_mastery(self):
        with tempfile.TemporaryDirectory() as temporary:
            data_dir = self.new_profile(temporary)
            profile = state.record_attempt(data_dir, attempt(), as_of=AS_OF)
            self.assertEqual(profile["topic_states"]["3.1"]["status"], "provisional")
            self.assertEqual(profile["attempt_ids"], ["attempt-001"])
            self.assertEqual(profile["seen_item_ids"], ["U3-CHAIN-D1"])
            self.assertEqual(profile["review_queue"][0]["reason"], "evidence-needed")

    def test_only_independent_unseen_no_hint_transfer_passes(self):
        with tempfile.TemporaryDirectory() as temporary:
            data_dir = self.new_profile(temporary)
            profile = state.record_attempt(
                data_dir,
                attempt(
                    attempt_id="attempt-transfer",
                    independence="independent",
                    hint_level=0,
                    same_form_confirmation="pass",
                    transfer_result="pass",
                    transfer_item_unseen=True,
                ),
                as_of=AS_OF,
            )
            self.assertEqual(profile["topic_states"]["3.1"]["status"], "passed")
            self.assertEqual(profile["review_queue"], [])

    def test_passed_transfer_can_schedule_a_delayed_retest(self):
        with tempfile.TemporaryDirectory() as temporary:
            data_dir = self.new_profile(temporary)
            profile = state.record_attempt(
                data_dir,
                attempt(
                    attempt_id="attempt-transfer-review",
                    independence="independent",
                    hint_level=0,
                    same_form_confirmation="pass",
                    transfer_result="pass",
                    transfer_item_unseen=True,
                    next_review_at="2026-09-07T10:00:00Z",
                ),
                as_of=AS_OF,
            )
            self.assertEqual(profile["topic_states"]["3.1"]["status"], "passed")
            self.assertEqual(profile["review_queue"][0]["reason"], "delayed-retest")

    def test_pass_labels_require_independent_no_hint_evidence(self):
        with self.assertRaisesRegex(state.StateError, "same-form pass"):
            state.validate_attempt(
                attempt(same_form_confirmation="pass", independence="assisted", hint_level=1),
                as_of=AS_OF,
            )
        with self.assertRaisesRegex(state.StateError, "transfer pass"):
            state.validate_attempt(
                attempt(
                    transfer_result="pass",
                    transfer_item_unseen=False,
                    independence="independent",
                    hint_level=0,
                ),
                as_of=AS_OF,
            )

    def test_missing_values_remain_null_or_unknown(self):
        validated = state.validate_attempt(attempt(), as_of=AS_OF)
        self.assertIsNone(validated["completion_time_seconds"])
        self.assertIsNone(validated["observed_error"])
        self.assertEqual(validated["confidence"], "unknown")

    def test_duplicate_attempt_is_rejected_without_second_append(self):
        with tempfile.TemporaryDirectory() as temporary:
            data_dir = self.new_profile(temporary)
            state.record_attempt(data_dir, attempt(), as_of=AS_OF)
            before = (data_dir / state.ATTEMPTS_NAME).read_bytes()
            with self.assertRaisesRegex(state.StateError, "duplicate attempt_id"):
                state.record_attempt(data_dir, attempt(), as_of=AS_OF)
            self.assertEqual(before, (data_dir / state.ATTEMPTS_NAME).read_bytes())

    def test_atomic_profile_update_uses_replace_and_leaves_no_temp(self):
        with tempfile.TemporaryDirectory() as temporary:
            data_dir = self.new_profile(temporary)
            with mock.patch.object(state.os, "replace", wraps=state.os.replace) as replace:
                state.record_attempt(data_dir, attempt(), as_of=AS_OF)
            self.assertTrue(replace.called)
            self.assertEqual(list(data_dir.glob("*.tmp")), [])
            json.loads((data_dir / state.PROFILE_NAME).read_text(encoding="utf-8"))

    def test_future_and_incomplete_attempts_fail(self):
        with self.assertRaisesRegex(state.StateError, "future"):
            state.validate_attempt(
                attempt(observed_at="2026-09-01T00:00:00Z"), as_of=AS_OF
            )
        incomplete = attempt()
        incomplete.pop("source_item_id")
        with self.assertRaisesRegex(state.StateError, "missing: source_item_id"):
            state.validate_attempt(incomplete, as_of=AS_OF)

    def test_corrupt_attempt_log_fails_rebuild(self):
        with tempfile.TemporaryDirectory() as temporary:
            data_dir = self.new_profile(temporary)
            (data_dir / state.ATTEMPTS_NAME).write_text("{broken\n", encoding="utf-8")
            with self.assertRaisesRegex(state.StateError, "corrupt attempts.jsonl"):
                state.load_attempts(data_dir / state.ATTEMPTS_NAME, as_of=AS_OF)

    def test_structurally_corrupt_profile_fails_before_append(self):
        with tempfile.TemporaryDirectory() as temporary:
            data_dir = self.new_profile(temporary)
            profile_path = data_dir / state.PROFILE_NAME
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            profile.pop("review_queue")
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            before = (data_dir / state.ATTEMPTS_NAME).read_bytes()
            with self.assertRaisesRegex(state.StateError, "unsupported or incomplete"):
                state.record_attempt(data_dir, attempt(), as_of=AS_OF)
            self.assertEqual(before, (data_dir / state.ATTEMPTS_NAME).read_bytes())

    def test_profile_rejects_passed_status_without_passing_transfer_evidence(self):
        profile = state.rebuild_profile(
            "test_profile",
            [
                state.validate_attempt(
                    attempt(
                        independence="independent",
                        hint_level=0,
                        same_form_confirmation="pass",
                        transfer_result="pass",
                        transfer_item_unseen=True,
                    ),
                    as_of=AS_OF,
                )
            ],
            as_of=AS_OF,
        )
        profile["topic_states"]["3.1"]["transfer_result"] = "fail"
        with self.assertRaisesRegex(state.StateError, "status is inconsistent"):
            state.validate_profile(profile, as_of=AS_OF)

    def test_profile_rejects_confirmation_status_with_incorrect_or_assisted_evidence(self):
        profile = state.rebuild_profile(
            "test_profile",
            [
                state.validate_attempt(
                    attempt(
                        independence="independent",
                        hint_level=0,
                        same_form_confirmation="pass",
                    ),
                    as_of=AS_OF,
                )
            ],
            as_of=AS_OF,
        )
        for field, bad_value in (("correctness", "incorrect"), ("independence", "assisted"), ("hint_level", 3)):
            mutated = json.loads(json.dumps(profile))
            mutated["topic_states"]["3.1"][field] = bad_value
            with self.subTest(field=field), self.assertRaisesRegex(
                state.StateError, "status is inconsistent"
            ):
                state.validate_profile(mutated, as_of=AS_OF)

    def test_paths_inside_repository_and_file_paths_fail(self):
        with self.assertRaisesRegex(state.StateError, "outside the skill repository"):
            state.resolve_data_dir(str(SKILL_ROOT / "learner-data"), create=True)
        with tempfile.NamedTemporaryFile() as handle:
            with self.assertRaisesRegex(state.StateError, "not a directory"):
                state.resolve_data_dir(handle.name)

    def test_existing_symlink_into_repository_cannot_bypass_data_boundary(self):
        with tempfile.TemporaryDirectory() as temporary:
            link = Path(temporary) / "linked-data"
            if os.name == "nt":
                created = subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(link), str(SKILL_ROOT / "references")],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(created.returncode, 0, created.stderr or created.stdout)
            else:
                link.symlink_to(SKILL_ROOT / "references", target_is_directory=True)
            try:
                with self.assertRaisesRegex(state.StateError, "outside the skill repository"):
                    state.resolve_data_dir(str(link), create=True)
            finally:
                link.rmdir()

    def test_clear_removes_only_named_test_profile_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            data_dir = self.new_profile(temporary)
            extra = data_dir / "keep-me.txt"
            extra.write_text("safe", encoding="utf-8")
            removed = state.clear_test_profile(data_dir, "test_profile")
            self.assertEqual(
                set(removed),
                {state.PROFILE_NAME, state.ATTEMPTS_NAME, state.TEST_MARKER},
            )
            self.assertEqual(extra.read_text(encoding="utf-8"), "safe")

    def test_clear_requires_matching_marker(self):
        with tempfile.TemporaryDirectory() as temporary:
            data_dir = self.new_profile(temporary, test_data=False)
            with self.assertRaisesRegex(state.StateError, "missing file"):
                state.clear_test_profile(data_dir, "test_profile")

    def test_calibration_summary_reports_insufficient_data(self):
        summary = state.calibration_summary([attempt()], minimum_sample=5)
        self.assertEqual(summary["status"], "insufficient_data")
        self.assertNotIn("p_value", json.dumps(summary))

    def test_calibration_summary_checks_all_requested_descriptive_metrics(self):
        metadata = {
            "I-EASY": {
                "topic": "3.1",
                "difficulty": "foundational",
                "target_misconceptions": ["M-A"],
            },
            "I-HARD": {
                "topic": "3.1",
                "difficulty": "challenge",
                "target_misconceptions": ["M-B"],
            },
        }
        attempts = []
        for index in range(4):
            attempts.append(
                attempt(
                    attempt_id=f"easy-{index}",
                    source_item_id="I-EASY",
                    correctness="correct" if index == 0 else "incorrect",
                    hint_level=index % 2,
                    independence="independent" if index == 0 else "assisted",
                    same_form_confirmation="pass" if index == 0 else "fail",
                    transfer_result="pass" if index == 0 else "fail",
                    transfer_item_unseen=True if index == 0 else None,
                )
            )
            attempts.append(
                attempt(
                    attempt_id=f"hard-{index}",
                    source_item_id="I-HARD",
                    correctness="incorrect" if index == 0 else "correct",
                    hint_level=0,
                    independence="independent",
                    same_form_confirmation="pass" if index != 0 else "fail",
                    transfer_result="pass" if index != 0 else "fail",
                    transfer_item_unseen=True if index != 0 else None,
                )
            )
        summary = state.calibration_summary(attempts, minimum_sample=2, item_metadata=metadata)
        self.assertEqual(summary["status"], "ready_for_review")
        self.assertEqual(len(summary["item_metrics"]), 2)
        self.assertEqual(len(summary["misconception_discrimination"]), 2)
        self.assertEqual(summary["difficulty_ordering"]["comparable_pair_count"], 1)
        self.assertEqual(len(summary["difficulty_ordering"]["anomalies"]), 1)
        serialized = json.dumps(summary)
        self.assertNotIn("p_value", serialized)
        self.assertNotIn("irt", serialized.lower())


if __name__ == "__main__":
    unittest.main()
