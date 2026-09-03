#!/usr/bin/env python3
"""Select one AP Precalculus or Calculus Coach item deterministically."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ITEMS = SKILL_ROOT / "references" / "diagnostic-items.jsonl"
DEFAULT_MISCONCEPTIONS = SKILL_ROOT / "references" / "calculus-misconceptions.json"
COURSES = {"precalculus", "calc-ab", "calc-bc"}
TOPIC_RES = {
    "precalculus": re.compile(r"^[1-4]\.[0-9]+$"),
    "calc-ab": re.compile(r"^[1-8]\.[0-9]+$"),
    "calc-bc": re.compile(r"^(?:[1-9]|10)\.[0-9]+$"),
}
PRACTICES = {
    "precalculus": {
        "precalc-1-procedural-symbolic-fluency",
        "precalc-2-multiple-representations",
        "precalc-3-communication-reasoning",
    },
    "calc-ab": {
        "calc-1-implementing-processes",
        "calc-2-connecting-representations",
        "calc-3-justification",
        "calc-4-communication-notation",
    },
}
PRACTICES["calc-bc"] = PRACTICES["calc-ab"]


class SelectionError(ValueError):
    pass


def timestamp(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise SelectionError(f"{field} must be an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise SelectionError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SelectionError(f"could not load {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise SelectionError(f"{label} must contain one JSON object")
    return value


def load_state(path: Path) -> dict[str, Any]:
    value = load_json(path, "learner state")
    required = {
        "schema_version",
        "profile_id",
        "course",
        "attempt_ids",
        "seen_item_ids",
        "topic_states",
        "review_queue",
        "updated_at",
    }
    if (
        value.keys() != required
        or value["schema_version"] != 1
        or value["course"] not in COURSES
    ):
        raise SelectionError("learner state has an unsupported or incomplete schema")
    if (
        not isinstance(value["attempt_ids"], list)
        or not isinstance(value["seen_item_ids"], list)
        or any(not isinstance(item_id, str) or not item_id for item_id in value["seen_item_ids"])
        or not isinstance(value["topic_states"], dict)
    ):
        raise SelectionError("learner state collections are invalid")
    if len(value["seen_item_ids"]) != len(set(value["seen_item_ids"])):
        raise SelectionError("learner state seen_item_ids contains duplicates")
    if (
        any(not isinstance(attempt_id, str) or not attempt_id for attempt_id in value["attempt_ids"])
        or len(value["attempt_ids"]) != len(set(value["attempt_ids"]))
    ):
        raise SelectionError("learner state attempt_ids is invalid")
    if not isinstance(value["review_queue"], list):
        raise SelectionError("review_queue must be an array")
    course = value["course"]
    timestamp(value["updated_at"], "updated_at")
    state_fields = {
        "topic",
        "practice",
        "evidence_count",
        "correctness",
        "completion_time_seconds",
        "confidence",
        "source_item_id",
        "status",
        "last_observed_at",
        "next_review_at",
        "observed_error",
        "hypothesized_misconception",
        "diagnostic_confidence",
        "independence",
        "hint_level",
        "same_form_confirmation",
        "transfer_result",
        "transfer_item_unseen",
    }
    for topic, state in value["topic_states"].items():
        if not isinstance(topic, str) or not TOPIC_RES[course].fullmatch(topic):
            raise SelectionError(f"topic state {topic!r} is invalid for {course}")
        if not isinstance(state, dict) or state.keys() != state_fields or state.get("topic") != topic:
            raise SelectionError(f"topic state {topic!r} has invalid fields")
        if state["practice"] is not None and state["practice"] not in PRACTICES[course]:
            raise SelectionError(f"topic state {topic!r} has an invalid practice for {course}")
        timestamp(state["last_observed_at"], f"topic state {topic} last_observed_at")
        if state["next_review_at"] is not None:
            timestamp(state["next_review_at"], f"topic state {topic} next_review_at")
        passed = (
            state["correctness"] == "correct"
            and state["transfer_result"] == "pass"
            and state["transfer_item_unseen"] is True
            and state["independence"] == "independent"
            and state["hint_level"] == 0
        )
        confirmed = (
            state["correctness"] == "correct"
            and state["same_form_confirmation"] == "pass"
            and state["independence"] == "independent"
            and state["hint_level"] == 0
        )
        expected_status = (
            "passed"
            if passed
            else "scheduled-retest"
            if state["next_review_at"] is not None
            else "needs-confirmation"
            if confirmed
            else "provisional"
        )
        if state["status"] != expected_status:
            raise SelectionError(f"topic state {topic} status contradicts its evidence")
    queue_fields = {
        "review_id", "topic", "misconception_id", "item_id", "reason", "due_at", "status"
    }
    review_ids: set[str] = set()
    for entry in value["review_queue"]:
        if not isinstance(entry, dict) or entry.keys() != queue_fields:
            raise SelectionError("review_queue contains invalid fields")
        if (
            not isinstance(entry["review_id"], str)
            or not entry["review_id"]
            or entry["review_id"] in review_ids
        ):
            raise SelectionError("review_queue contains an invalid or duplicate review_id")
        review_ids.add(entry["review_id"])
        if entry["topic"] not in value["topic_states"]:
            raise SelectionError(f"review {entry['review_id']} references an unknown topic state")
        if entry["reason"] not in {
            "same-form-confirmation", "transfer", "delayed-retest", "evidence-needed"
        } or entry["status"] not in {"pending", "completed"}:
            raise SelectionError(f"review {entry['review_id']} has invalid reason/status")
        for field in ("misconception_id", "item_id"):
            if entry[field] is not None and (
                not isinstance(entry[field], str) or not entry[field]
            ):
                raise SelectionError(f"review {entry['review_id']} has invalid {field}")
        timestamp(entry["due_at"], f"review {entry['review_id']} due_at")
    return value


def load_items(path: Path) -> dict[str, dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise SelectionError(f"could not load diagnostic items: {exc}") from exc
    items: dict[str, dict[str, Any]] = {}
    required = {
        "schema_version",
        "item_id",
        "course",
        "unit",
        "topic_code",
        "topic_citation",
        "mathematical_practice",
        "task_type",
        "representation",
        "calculator_condition",
        "justification_requirement",
        "difficulty",
        "prerequisites",
        "target_misconceptions",
        "prompt",
        "answer",
        "solution",
        "verification",
        "hint_ladder",
        "distractor_diagnoses",
        "error_response_diagnoses",
        "same_form_confirmation_item_id",
        "transfer_item_id",
        "answer_visibility",
        "selection",
    }
    for line_number, line in enumerate(lines, 1):
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SelectionError(f"invalid item JSON at line {line_number}: {exc}") from exc
        if not isinstance(item, dict) or item.keys() != required:
            raise SelectionError(f"diagnostic item line {line_number} has invalid fields")
        item_id = item.get("item_id")
        if not isinstance(item_id, str) or not item_id or item_id in items:
            raise SelectionError(f"diagnostic item line {line_number} has a duplicate or invalid item_id")
        if item.get("schema_version") != 1 or item.get("course") not in COURSES:
            raise SelectionError(f"diagnostic item {item_id} has invalid course/schema metadata")
        if item.get("answer_visibility") != "hidden":
            raise SelectionError(f"diagnostic item {item_id} must default to hidden")
        selection = item.get("selection")
        if (
            not isinstance(selection, dict)
            or selection.keys()
            != {"stage", "priority", "expected_time_seconds", "exit_eligible", "representation_family", "context_family"}
            or not isinstance(selection.get("priority"), int)
        ):
            raise SelectionError(f"diagnostic item {item_id} has invalid selection metadata")
        items[item_id] = item
    if not items:
        raise SelectionError("diagnostic item bank is empty")
    return items


def load_misconceptions(path: Path) -> dict[str, dict[str, Any]]:
    value = load_json(path, "misconception graph")
    if value.get("schema_version") != 1 or not isinstance(value.get("misconceptions"), list):
        raise SelectionError("misconception graph has an unsupported schema")
    result: dict[str, dict[str, Any]] = {}
    required = {
        "misconception_id",
        "course",
        "internal_diagnostic",
        "unit",
        "topic",
        "practice",
        "observable_features",
        "evidence_required",
        "alternative_causes",
        "prerequisites",
        "prerequisite_rationale",
        "minimum_remediation",
        "diagnostic_item_id",
        "confirmation_item_id",
        "transfer_item_id",
        "exit_standard",
        "uncertain_action",
    }
    for record in value["misconceptions"]:
        if not isinstance(record, dict) or record.keys() != required:
            raise SelectionError("misconception record has invalid fields")
        identifier = record.get("misconception_id")
        if not isinstance(identifier, str) or not identifier or identifier in result:
            raise SelectionError("misconception_id is invalid or duplicated")
        if record.get("internal_diagnostic") is not True:
            raise SelectionError(f"{identifier} must be labeled as an internal diagnostic")
        if record.get("course") not in COURSES:
            raise SelectionError(f"{identifier} has invalid course metadata")
        result[identifier] = record
    return result


def _course_applies(record_course: str | None, learner_course: str) -> bool:
    return record_course == learner_course or (
        learner_course == "calc-bc" and record_course == "calc-ab"
    )


def _candidate(
    items: dict[str, dict[str, Any]],
    seen: set[str],
    item_id: str | None,
) -> dict[str, Any] | None:
    if item_id is None or item_id in seen:
        return None
    return items.get(item_id)


def _target_candidate(
    items: dict[str, dict[str, Any]],
    seen: set[str],
    misconception_id: str,
    stages: Iterable[str],
) -> dict[str, Any] | None:
    stage_order = {stage: index for index, stage in enumerate(stages)}
    candidates = [
        item
        for item in items.values()
        if item["item_id"] not in seen
        and misconception_id in item["target_misconceptions"]
        and item["selection"]["stage"] in stage_order
    ]
    candidates.sort(
        key=lambda item: (
            stage_order[item["selection"]["stage"]],
            item["selection"]["priority"],
            item["item_id"],
        )
    )
    return candidates[0] if candidates else None


def _receipt(
    item: dict[str, Any] | None,
    *,
    reason: str,
    evidence: list[str],
    uncertainty: str,
    exit_standard: dict[str, Any] | str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "item_id": item["item_id"] if item else None,
        "selection_reason": reason,
        "current_evidence": evidence,
        "uncertainty": uncertainty,
        "next_exit_standard": exit_standard,
    }


def select_next(
    state: dict[str, Any],
    items: dict[str, dict[str, Any]],
    misconceptions: dict[str, dict[str, Any]],
    *,
    as_of: datetime,
) -> dict[str, Any]:
    course = state["course"]
    items = {
        identifier: item
        for identifier, item in items.items()
        if _course_applies(item.get("course"), course)
    }
    misconceptions = {
        identifier: record
        for identifier, record in misconceptions.items()
        if _course_applies(record.get("course", "calc-ab"), course)
    }
    seen = set(state["seen_item_ids"])
    due_fallbacks: list[str] = []
    blocked_due_reviews: list[str] = []
    queue = sorted(
        (
            entry
            for entry in state["review_queue"]
            if entry.get("status") == "pending"
            and timestamp(entry.get("due_at"), "review_queue.due_at") <= as_of
        ),
        key=lambda entry: (timestamp(entry["due_at"], "review_queue.due_at"), entry.get("review_id", "")),
    )
    for entry in queue:
        misconception = misconceptions.get(entry.get("misconception_id"))
        desired = _candidate(items, seen, entry.get("item_id"))
        if desired is not None and (
            desired["topic_code"] != entry.get("topic")
            or (
                entry.get("misconception_id") is not None
                and entry["misconception_id"] not in desired["target_misconceptions"]
            )
        ):
            raise SelectionError(
                f"review {entry.get('review_id', '')} item does not match its Topic/misconception"
            )
        if desired is not None:
            allowed_stages = {
                "same-form-confirmation": {"confirmation"},
                "transfer": {"transfer"},
                "delayed-retest": {"retest", "transfer"},
                "evidence-needed": {"diagnostic"},
            }.get(entry.get("reason"), set())
            if desired["selection"]["stage"] not in allowed_stages:
                raise SelectionError(
                    f"review {entry.get('review_id', '')} item stage contradicts its reason"
                )
        if desired is None and misconception:
            reason = entry.get("reason")
            if reason == "same-form-confirmation":
                link = misconception["confirmation_item_id"]
                stages = ["confirmation", "diagnostic"]
            elif reason == "transfer":
                link = misconception["transfer_item_id"]
                stages = ["transfer", "retest"]
            elif reason == "delayed-retest":
                link = None
                stages = ["retest", "transfer", "confirmation", "diagnostic"]
            else:
                link = misconception["diagnostic_item_id"]
                stages = ["diagnostic", "confirmation"]
            desired = _candidate(items, seen, link)
            if desired is None:
                desired = _target_candidate(
                    items,
                    seen,
                    misconception["misconception_id"],
                    stages,
                )
        if desired is None and misconception is None:
            topic_diagnostics = [
                item
                for item in items.values()
                if item["item_id"] not in seen
                and item["topic_code"] == entry.get("topic")
                and item["selection"]["stage"] == "diagnostic"
            ]
            topic_diagnostics.sort(
                key=lambda item: (item["selection"]["priority"], item["item_id"])
            )
            desired = topic_diagnostics[0] if topic_diagnostics else None
            if desired is None:
                due_fallbacks.append(
                    f"due review {entry['review_id']} had no unseen diagnostic for topic {entry['topic']}"
                )
        elif desired is None:
            blocked_due_reviews.append(
                f"due review {entry['review_id']} had no unseen item for misconception {misconception['misconception_id']}"
            )
        if desired:
            standard = misconception["exit_standard"] if misconception else "Complete the scheduled unseen task independently."
            return _receipt(
                desired,
                reason=f"due {entry.get('reason')} review takes priority",
                evidence=[f"review {entry['review_id']} was due at {entry['due_at']}"],
                uncertainty={
                    "evidence-needed": "high",
                    "same-form-confirmation": "medium",
                    "transfer": "medium",
                    "delayed-retest": "medium",
                }.get(entry.get("reason"), "high" if misconception is None else "medium"),
                exit_standard=standard,
            )

    if blocked_due_reviews or due_fallbacks:
        return _receipt(
            None,
            reason="a due review has no unseen maintained item; do not substitute an unrelated task",
            evidence=blocked_due_reviews + due_fallbacks,
            uncertainty="high",
            exit_standard="Add an unseen item for the due intervention before retesting it.",
        )

    states = sorted(state["topic_states"].values(), key=lambda item: (item["topic"], item["last_observed_at"]))
    for topic_state in states:
        misconception_id = topic_state.get("hypothesized_misconception")
        misconception = misconceptions.get(misconception_id)
        confidence = topic_state.get("diagnostic_confidence")
        if not misconception or confidence != "high":
            continue
        unmet = []
        for prerequisite_id in misconception["prerequisites"]:
            prerequisite = misconceptions[prerequisite_id]
            prerequisite_state = state["topic_states"].get(prerequisite["topic"])
            if not prerequisite_state or prerequisite_state.get("status") != "passed":
                unmet.append(prerequisite)
        target = unmet[0] if unmet else misconception
        if unmet:
            stages = ["diagnostic", "confirmation", "transfer"]
            reason = "an explicit prerequisite lacks passing transfer evidence"
        elif topic_state.get("status") == "needs-confirmation":
            stages = ["transfer", "retest"]
            reason = "same-form evidence exists; an unseen transfer is next"
        elif topic_state.get("status") == "scheduled-retest":
            stages = ["retest", "transfer"]
            reason = "the intervention needs a retest"
        else:
            stages = ["confirmation", "diagnostic", "transfer"]
            reason = "a specific high-confidence misconception needs confirmation"
        desired = _target_candidate(items, seen, target["misconception_id"], stages)
        if desired:
            return _receipt(
                desired,
                reason=reason,
                evidence=[
                    f"topic {topic_state['topic']} status is {topic_state['status']}",
                    f"diagnostic confidence for {misconception_id} is high",
                ],
                uncertainty="low",
                exit_standard=target["exit_standard"],
            )

    for topic_state in states:
        if topic_state.get("correctness") != "correct":
            continue
        source = items.get(topic_state.get("source_item_id"))
        expected = source.get("selection", {}).get("expected_time_seconds") if source else None
        slow = (
            isinstance(expected, int)
            and isinstance(topic_state.get("completion_time_seconds"), int)
            and topic_state["completion_time_seconds"] > expected
        )
        assisted = topic_state.get("independence") == "assisted" or (topic_state.get("hint_level") or 0) > 0
        low_confidence = topic_state.get("confidence") == "low"
        if not (slow or assisted or low_confidence):
            continue
        candidates = [
            item
            for item in items.values()
            if item["item_id"] not in seen and item["topic_code"] == topic_state["topic"]
        ]
        if assisted:
            stage_order = {"confirmation": 0, "diagnostic": 1, "transfer": 2, "retest": 3}
            candidates.sort(
                key=lambda item: (
                    stage_order.get(item["selection"]["stage"], 4),
                    item["selection"]["priority"],
                    item["item_id"],
                )
            )
        else:
            candidates.sort(
                key=lambda item: (
                    item["representation"] == (source.get("representation") if source else None),
                    item["selection"]["priority"],
                    item["item_id"],
                )
            )
        if candidates:
            observations = []
            if assisted:
                observations.append("the correct response used assistance or a nonzero hint")
            if slow:
                observations.append("completion time exceeded the item's provisional observation threshold")
            if low_confidence:
                observations.append("reported confidence was low")
            return _receipt(
                candidates[0],
                reason="correctness is provisional because independence, time, or confidence needs checking",
                evidence=observations,
                uncertainty="high" if slow and not assisted else "medium",
                exit_standard="Complete an unseen cross-representation item independently with hint level 0.",
            )

    unknown = [
        item
        for item in items.values()
        if item["item_id"] not in seen and item["selection"]["stage"] == "diagnostic"
    ]
    unknown.sort(
        key=lambda item: (
            item["difficulty"]["label"] != "foundational",
            item["unit"],
            item["selection"]["priority"],
            item["item_id"],
        )
    )
    if unknown:
        target = misconceptions.get(unknown[0]["target_misconceptions"][0])
        return _receipt(
            unknown[0],
            reason=(
                "a due topic had no unseen diagnostic; use the stable global diagnostic fallback"
                if due_fallbacks
                else "learner evidence is insufficient; start with a foundational diagnostic"
            ),
            evidence=(
                due_fallbacks
                if due_fallbacks
                else ["no due review or actionable high-confidence diagnosis was available"]
            ),
            uncertainty="high",
            exit_standard=target["exit_standard"] if target else "Collect one independent response before diagnosing.",
        )
    return _receipt(
        None,
        reason="all applicable candidate items have already been seen or are unavailable",
        evidence=due_fallbacks + [f"{len(seen)} item(s) are marked seen"],
        uncertainty="high",
        exit_standard="Add an unseen applicable item before making another selection.",
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--state", type=Path, required=True)
    result.add_argument("--items", type=Path, default=DEFAULT_ITEMS)
    result.add_argument("--misconceptions", type=Path, default=DEFAULT_MISCONCEPTIONS)
    result.add_argument("--as-of", required=True)
    result.add_argument("--evidence-json", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        receipt = select_next(
            load_state(args.state),
            load_items(args.items),
            load_misconceptions(args.misconceptions),
            as_of=timestamp(args.as_of, "as_of"),
        )
        payload = {"overall_status": "pass", "selection": receipt}
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        return 0
    except (SelectionError, KeyError, TypeError, OSError) as exc:
        payload = {"overall_status": "error", "error": str(exc)}
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
        return 2


def _configure_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="strict")


if __name__ == "__main__":
    _configure_utf8()
    raise SystemExit(main())
