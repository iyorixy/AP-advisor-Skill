#!/usr/bin/env python3
"""Manage opt-in AP Calculus AB learner state using only local JSON files."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SKILL_ROOT = Path(__file__).resolve().parent.parent
PROFILE_NAME = "profile.json"
ATTEMPTS_NAME = "attempts.jsonl"
TEST_MARKER = ".ap-calculus-test-data"
DEFAULT_ITEMS = SKILL_ROOT / "references" / "diagnostic-items.jsonl"
SCHEMA_VERSION = 1
ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
PROFILE_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
TOPIC_RE = re.compile(r"^[1-8]\.[0-9]+$")
PRACTICES = {
    "calc-1-implementing-processes",
    "calc-2-connecting-representations",
    "calc-3-justification",
    "calc-4-communication-notation",
}
ATTEMPT_FIELDS = {
    "schema_version",
    "attempt_id",
    "profile_id",
    "course",
    "topic",
    "practice",
    "correctness",
    "completion_time_seconds",
    "confidence",
    "observed_error",
    "hypothesized_misconception",
    "diagnostic_confidence",
    "independence",
    "hint_level",
    "same_form_confirmation",
    "transfer_result",
    "transfer_item_unseen",
    "observed_at",
    "next_review_at",
    "source_attempt_id",
    "source_item_id",
}
PROFILE_FIELDS = {
    "schema_version",
    "profile_id",
    "course",
    "attempt_ids",
    "seen_item_ids",
    "topic_states",
    "review_queue",
    "updated_at",
}
TOPIC_STATE_FIELDS = {
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
REVIEW_FIELDS = {
    "review_id",
    "topic",
    "misconception_id",
    "item_id",
    "reason",
    "due_at",
    "status",
}


class StateError(ValueError):
    pass


def parse_timestamp(value: str, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise StateError(f"{field} must be an ISO 8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise StateError(f"{field} must be an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise StateError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def resolve_data_dir(raw: str, *, create: bool = False) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise StateError("data directory must be explicitly provided")
    candidate = Path(raw).expanduser()
    if candidate.exists():
        resolved = candidate.resolve(strict=True)
    elif create:
        parent = candidate.parent.resolve(strict=True)
        if not parent.is_dir():
            raise StateError("data-directory parent is not a directory")
        resolved = parent / candidate.name
    else:
        resolved = candidate.resolve(strict=True)
    skill_root = SKILL_ROOT.resolve()
    if resolved == skill_root or resolved.is_relative_to(skill_root):
        raise StateError("learner data directory must be outside the skill repository")
    if resolved.exists() and not resolved.is_dir():
        raise StateError("data directory path is not a directory")
    return resolved


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise StateError(f"missing file: {path.name}") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StateError(f"could not read valid JSON from {path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise StateError(f"{path.name} must contain one JSON object")
    return value


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    temporary = Path(handle.name)
    try:
        with handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def validate_profile_id(value: str) -> None:
    if not isinstance(value, str) or not PROFILE_RE.fullmatch(value):
        raise StateError("profile_id must use 1-64 letters, digits, underscores, or hyphens")


def _identifier_or_null(value: Any, field: str) -> None:
    if value is not None and (not isinstance(value, str) or not ID_RE.fullmatch(value)):
        raise StateError(f"{field} must be a stable identifier or null")


def validate_profile(value: dict[str, Any], *, as_of: datetime) -> dict[str, Any]:
    if not isinstance(value, dict) or value.keys() != PROFILE_FIELDS:
        raise StateError("profile.json has an unsupported or incomplete schema")
    if value["schema_version"] != SCHEMA_VERSION or value["course"] != "calc-ab":
        raise StateError("profile.json has unsupported schema or course metadata")
    validate_profile_id(value["profile_id"])
    updated_at = parse_timestamp(value["updated_at"], "updated_at")
    if updated_at > as_of:
        raise StateError("profile updated_at cannot be in the future")

    for field in ("attempt_ids", "seen_item_ids"):
        identifiers = value[field]
        if not isinstance(identifiers, list):
            raise StateError(f"profile {field} must be an array")
        for identifier in identifiers:
            _identifier_or_null(identifier, f"profile {field} entry")
            if identifier is None:
                raise StateError(f"profile {field} entries cannot be null")
        if len(identifiers) != len(set(identifiers)):
            raise StateError(f"profile {field} contains duplicates")

    topic_states = value["topic_states"]
    if not isinstance(topic_states, dict):
        raise StateError("profile topic_states must be an object")
    for topic, state in topic_states.items():
        if not isinstance(topic, str) or not TOPIC_RE.fullmatch(topic):
            raise StateError("profile contains an invalid Topic key")
        if not isinstance(state, dict) or state.keys() != TOPIC_STATE_FIELDS:
            raise StateError(f"topic state {topic} has invalid fields")
        if state["topic"] != topic:
            raise StateError(f"topic state {topic} does not match its key")
        if state["practice"] is not None and state["practice"] not in PRACTICES:
            raise StateError(f"topic state {topic} has invalid practice")
        count = state["evidence_count"]
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise StateError(f"topic state {topic} has invalid evidence_count")
        if state["correctness"] not in {"correct", "incorrect", "partial", "unknown"}:
            raise StateError(f"topic state {topic} has invalid correctness")
        duration = state["completion_time_seconds"]
        if duration is not None and (
            not isinstance(duration, int) or isinstance(duration, bool) or duration < 0
        ):
            raise StateError(f"topic state {topic} has invalid completion time")
        if state["confidence"] not in {"low", "medium", "high", "unknown", None}:
            raise StateError(f"topic state {topic} has invalid confidence")
        _identifier_or_null(state["source_item_id"], f"topic state {topic} source_item_id")
        if state["source_item_id"] is None:
            raise StateError(f"topic state {topic} source_item_id cannot be null")
        if state["status"] not in {
            "provisional",
            "needs-confirmation",
            "scheduled-retest",
            "passed",
        }:
            raise StateError(f"topic state {topic} has invalid status")
        observed = parse_timestamp(state["last_observed_at"], f"topic state {topic} last_observed_at")
        if observed > as_of:
            raise StateError(f"topic state {topic} last_observed_at cannot be in the future")
        if state["next_review_at"] is not None:
            review = parse_timestamp(state["next_review_at"], f"topic state {topic} next_review_at")
            if review < observed:
                raise StateError(f"topic state {topic} next_review_at precedes its observation")
        if state["observed_error"] is not None and (
            not isinstance(state["observed_error"], str) or not state["observed_error"]
        ):
            raise StateError(f"topic state {topic} has invalid observed_error")
        _identifier_or_null(
            state["hypothesized_misconception"],
            f"topic state {topic} hypothesized_misconception",
        )
        if state["diagnostic_confidence"] not in {"low", "medium", "high", "unknown", None}:
            raise StateError(f"topic state {topic} has invalid diagnostic confidence")
        if state["independence"] not in {"independent", "assisted", "unknown"}:
            raise StateError(f"topic state {topic} has invalid independence")
        hint = state["hint_level"]
        if hint is not None and (
            not isinstance(hint, int) or isinstance(hint, bool) or not 0 <= hint <= 3
        ):
            raise StateError(f"topic state {topic} has invalid hint level")
        result_values = {"pass", "fail", "not_attempted", "unknown", None}
        if state["same_form_confirmation"] not in result_values:
            raise StateError(f"topic state {topic} has invalid same-form result")
        if state["transfer_result"] not in result_values:
            raise StateError(f"topic state {topic} has invalid transfer result")
        if state["transfer_item_unseen"] is not None and not isinstance(
            state["transfer_item_unseen"], bool
        ):
            raise StateError(f"topic state {topic} has invalid transfer_item_unseen")
        expected_status = attempt_status(state)
        if state["status"] != expected_status:
            raise StateError(
                f"topic state {topic} status is inconsistent with transfer, review, and hint evidence"
            )

    queue = value["review_queue"]
    if not isinstance(queue, list):
        raise StateError("profile review_queue must be an array")
    review_ids: set[str] = set()
    for entry in queue:
        if not isinstance(entry, dict) or entry.keys() != REVIEW_FIELDS:
            raise StateError("profile review_queue contains invalid fields")
        review_id = entry["review_id"]
        if not isinstance(review_id, str) or not review_id or review_id in review_ids:
            raise StateError("profile review_queue contains an invalid or duplicate review_id")
        review_ids.add(review_id)
        if entry["topic"] not in topic_states:
            raise StateError(f"review {review_id} references an unknown topic state")
        _identifier_or_null(entry["misconception_id"], f"review {review_id} misconception_id")
        _identifier_or_null(entry["item_id"], f"review {review_id} item_id")
        if entry["reason"] not in {
            "same-form-confirmation",
            "transfer",
            "delayed-retest",
            "evidence-needed",
        }:
            raise StateError(f"review {review_id} has an invalid reason")
        parse_timestamp(entry["due_at"], f"review {review_id} due_at")
        if entry["status"] not in {"pending", "completed"}:
            raise StateError(f"review {review_id} has an invalid status")
    return value


def validate_attempt(value: dict[str, Any], *, as_of: datetime) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise StateError("attempt must be a JSON object")
    missing = ATTEMPT_FIELDS - value.keys()
    extra = value.keys() - ATTEMPT_FIELDS
    if missing or extra:
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(sorted(missing)))
        if extra:
            parts.append("unexpected: " + ", ".join(sorted(extra)))
        raise StateError("attempt fields are invalid (" + "; ".join(parts) + ")")
    if value["schema_version"] != SCHEMA_VERSION:
        raise StateError("unsupported attempt schema_version")
    if not isinstance(value["attempt_id"], str) or not ID_RE.fullmatch(value["attempt_id"]):
        raise StateError("attempt_id is invalid")
    validate_profile_id(value["profile_id"])
    if value["course"] != "calc-ab":
        raise StateError("course must be calc-ab")
    if value["topic"] is not None and (
        not isinstance(value["topic"], str) or not TOPIC_RE.fullmatch(value["topic"])
    ):
        raise StateError("topic must be an AP Calculus AB Topic code or null")
    if value["practice"] is not None and value["practice"] not in PRACTICES:
        raise StateError("practice is invalid")
    if value["correctness"] not in {"correct", "incorrect", "partial", "unknown"}:
        raise StateError("correctness is invalid")
    duration = value["completion_time_seconds"]
    if duration is not None and (not isinstance(duration, int) or isinstance(duration, bool) or duration < 0):
        raise StateError("completion_time_seconds must be a nonnegative integer or null")
    if value["confidence"] not in {"low", "medium", "high", "unknown", None}:
        raise StateError("confidence is invalid")
    if value["observed_error"] is not None and (
        not isinstance(value["observed_error"], str) or not value["observed_error"]
    ):
        raise StateError("observed_error must be a nonempty string or null")
    _identifier_or_null(value["hypothesized_misconception"], "hypothesized_misconception")
    _identifier_or_null(value["source_attempt_id"], "source_attempt_id")
    if value["diagnostic_confidence"] not in {"low", "medium", "high", "unknown", None}:
        raise StateError("diagnostic_confidence is invalid")
    if value["independence"] not in {"independent", "assisted", "unknown"}:
        raise StateError("independence is invalid")
    hint = value["hint_level"]
    if hint is not None and (not isinstance(hint, int) or isinstance(hint, bool) or not 0 <= hint <= 3):
        raise StateError("hint_level must be an integer from 0 through 3 or null")
    confirmation_values = {"pass", "fail", "not_attempted", "unknown", None}
    if value["same_form_confirmation"] not in confirmation_values:
        raise StateError("same_form_confirmation is invalid")
    if value["transfer_result"] not in confirmation_values:
        raise StateError("transfer_result is invalid")
    if value["transfer_item_unseen"] is not None and not isinstance(value["transfer_item_unseen"], bool):
        raise StateError("transfer_item_unseen must be boolean or null")
    observed_at = parse_timestamp(value["observed_at"], "observed_at")
    if observed_at > as_of:
        raise StateError("observed_at cannot be in the future")
    if value["next_review_at"] is not None:
        review_at = parse_timestamp(value["next_review_at"], "next_review_at")
        if review_at < observed_at:
            raise StateError("next_review_at cannot precede observed_at")
    _identifier_or_null(value["source_item_id"], "source_item_id")
    if value["source_item_id"] is None:
        raise StateError("source_item_id cannot be null")
    if value["same_form_confirmation"] == "pass" and not (
        value["correctness"] == "correct"
        and value["independence"] == "independent"
        and value["hint_level"] == 0
    ):
        raise StateError("same-form pass requires a correct independent hint-level-0 attempt")
    if value["transfer_result"] == "pass" and not (
        value["correctness"] == "correct"
        and value["transfer_item_unseen"] is True
        and value["independence"] == "independent"
        and value["hint_level"] == 0
    ):
        raise StateError("transfer pass requires a correct unseen independent hint-level-0 attempt")
    return value


def load_attempts(path: Path, *, as_of: datetime) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise StateError(f"missing file: {ATTEMPTS_NAME}") from exc
    except (OSError, UnicodeError) as exc:
        raise StateError(f"could not read {ATTEMPTS_NAME}: {exc}") from exc
    attempts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            raise StateError(f"{ATTEMPTS_NAME} contains a blank record at line {line_number}")
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise StateError(f"corrupt {ATTEMPTS_NAME} line {line_number}: {exc}") from exc
        attempt = validate_attempt(raw, as_of=as_of)
        if attempt["attempt_id"] in seen:
            raise StateError(f"duplicate attempt_id in log: {attempt['attempt_id']}")
        seen.add(attempt["attempt_id"])
        attempts.append(attempt)
    return attempts


def attempt_status(attempt: dict[str, Any]) -> str:
    if (
        attempt["correctness"] == "correct"
        and attempt["transfer_result"] == "pass"
        and attempt["transfer_item_unseen"] is True
        and attempt["independence"] == "independent"
        and attempt["hint_level"] == 0
    ):
        return "passed"
    if attempt["next_review_at"] is not None:
        return "scheduled-retest"
    if (
        attempt["same_form_confirmation"] == "pass"
        and attempt["correctness"] == "correct"
        and attempt["independence"] == "independent"
        and attempt["hint_level"] == 0
    ):
        return "needs-confirmation"
    return "provisional"


def rebuild_profile(profile_id: str, attempts: Iterable[dict[str, Any]], *, as_of: datetime) -> dict[str, Any]:
    attempts = list(attempts)
    topic_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for attempt in attempts:
        if attempt["profile_id"] != profile_id:
            raise StateError("attempt profile_id does not match the initialized profile")
        if attempt["topic"] is not None:
            topic_groups[attempt["topic"]].append(attempt)

    topic_states: dict[str, dict[str, Any]] = {}
    queue: list[dict[str, Any]] = []
    for topic, records in sorted(topic_groups.items()):
        records.sort(key=lambda item: (parse_timestamp(item["observed_at"], "observed_at"), item["attempt_id"]))
        latest = records[-1]
        status = attempt_status(latest)
        topic_states[topic] = {
            "topic": topic,
            "practice": latest["practice"],
            "evidence_count": len(records),
            "correctness": latest["correctness"],
            "completion_time_seconds": latest["completion_time_seconds"],
            "confidence": latest["confidence"],
            "source_item_id": latest["source_item_id"],
            "status": status,
            "last_observed_at": latest["observed_at"],
            "next_review_at": latest["next_review_at"],
            "observed_error": latest["observed_error"],
            "hypothesized_misconception": latest["hypothesized_misconception"],
            "diagnostic_confidence": latest["diagnostic_confidence"],
            "independence": latest["independence"],
            "hint_level": latest["hint_level"],
            "same_form_confirmation": latest["same_form_confirmation"],
            "transfer_result": latest["transfer_result"],
            "transfer_item_unseen": latest["transfer_item_unseen"],
        }
        if latest["next_review_at"] is not None:
            reason = "delayed-retest"
            due_at = latest["next_review_at"]
        elif status == "passed":
            continue
        elif latest["same_form_confirmation"] == "pass":
            reason = "transfer"
            due_at = latest["observed_at"]
        elif latest["diagnostic_confidence"] in {None, "unknown", "low"}:
            reason = "evidence-needed"
            due_at = latest["observed_at"]
        else:
            reason = "same-form-confirmation"
            due_at = latest["observed_at"]
        misconception = latest["hypothesized_misconception"]
        queue.append(
            {
                "review_id": f"{topic}:{reason}:{due_at}",
                "topic": topic,
                "misconception_id": misconception,
                "item_id": None,
                "reason": reason,
                "due_at": due_at,
                "status": "pending",
            }
        )
    queue.sort(key=lambda item: (parse_timestamp(item["due_at"], "due_at"), item["review_id"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "profile_id": profile_id,
        "course": "calc-ab",
        "attempt_ids": [attempt["attempt_id"] for attempt in attempts],
        "seen_item_ids": list(dict.fromkeys(attempt["source_item_id"] for attempt in attempts)),
        "topic_states": topic_states,
        "review_queue": queue,
        "updated_at": utc_text(as_of),
    }


def initialize(data_dir: Path, profile_id: str, *, as_of: datetime, test_data: bool) -> dict[str, Any]:
    validate_profile_id(profile_id)
    if data_dir.exists() and any(data_dir.iterdir()):
        raise StateError("data directory must be new or empty")
    data_dir.mkdir(exist_ok=True)
    (data_dir / ATTEMPTS_NAME).write_text("", encoding="utf-8", newline="\n")
    profile = rebuild_profile(profile_id, [], as_of=as_of)
    atomic_write_json(data_dir / PROFILE_NAME, profile)
    if test_data:
        atomic_write_json(
            data_dir / TEST_MARKER,
            {"schema_version": SCHEMA_VERSION, "profile_id": profile_id, "test_data": True},
        )
    return profile


def record_attempt(data_dir: Path, attempt: dict[str, Any], *, as_of: datetime) -> dict[str, Any]:
    profile = validate_profile(read_json(data_dir / PROFILE_NAME), as_of=as_of)
    attempt = validate_attempt(attempt, as_of=as_of)
    attempts = load_attempts(data_dir / ATTEMPTS_NAME, as_of=as_of)
    if profile["attempt_ids"] != [item["attempt_id"] for item in attempts]:
        raise StateError("profile attempt_ids do not match attempts.jsonl; rebuild is required")
    expected_seen = list(dict.fromkeys(item["source_item_id"] for item in attempts))
    if profile["seen_item_ids"] != expected_seen:
        raise StateError("profile seen_item_ids do not match attempts.jsonl; rebuild is required")
    if attempt["profile_id"] != profile["profile_id"]:
        raise StateError("attempt profile_id does not match profile.json")
    if attempt["attempt_id"] in {item["attempt_id"] for item in attempts}:
        raise StateError(f"duplicate attempt_id: {attempt['attempt_id']}")
    with (data_dir / ATTEMPTS_NAME).open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(attempt, ensure_ascii=False, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    attempts.append(attempt)
    rebuilt = rebuild_profile(profile["profile_id"], attempts, as_of=as_of)
    atomic_write_json(data_dir / PROFILE_NAME, rebuilt)
    return rebuilt


def load_calibration_items(path: Path) -> dict[str, dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise StateError(f"could not read diagnostic item metadata: {exc}") from exc
    if not lines:
        raise StateError("diagnostic item metadata is empty")
    result: dict[str, dict[str, Any]] = {}
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            raise StateError(f"diagnostic item metadata has a blank line at {line_number}")
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise StateError(f"invalid diagnostic item JSON at line {line_number}: {exc}") from exc
        if not isinstance(item, dict):
            raise StateError(f"diagnostic item line {line_number} is not an object")
        identifier = item.get("item_id")
        if not isinstance(identifier, str) or not ID_RE.fullmatch(identifier) or identifier in result:
            raise StateError(f"diagnostic item line {line_number} has an invalid or duplicate item_id")
        difficulty = item.get("difficulty")
        if (
            not isinstance(difficulty, dict)
            or difficulty.keys() != {"label", "status", "observable_basis"}
            or difficulty.get("label") not in {"foundational", "standard", "challenge"}
            or difficulty.get("status") != "provisional"
            or not isinstance(difficulty.get("observable_basis"), str)
            or not difficulty["observable_basis"]
        ):
            raise StateError(f"diagnostic item {identifier} has invalid provisional difficulty metadata")
        targets = item.get("target_misconceptions")
        if (
            not isinstance(targets, list)
            or not targets
            or len(targets) != len(set(targets))
            or any(not isinstance(target, str) or not ID_RE.fullmatch(target) for target in targets)
        ):
            raise StateError(f"diagnostic item {identifier} has invalid target misconceptions")
        topic = item.get("topic_code")
        if not isinstance(topic, str) or not TOPIC_RE.fullmatch(topic):
            raise StateError(f"diagnostic item {identifier} has invalid Topic metadata")
        result[identifier] = {
            "topic": topic,
            "difficulty": difficulty["label"],
            "target_misconceptions": targets,
        }
    return result


def calibration_summary(
    attempts: Iterable[dict[str, Any]],
    minimum_sample: int,
    item_metadata: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    attempts = list(attempts)
    if minimum_sample < 2:
        raise StateError("minimum_sample must be at least 2")
    if len(attempts) < minimum_sample:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "insufficient_data",
            "minimum_sample": minimum_sample,
            "attempt_count": len(attempts),
            "reason": "fewer total attempts than minimum_sample",
        }
    if item_metadata is None:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "insufficient_data",
            "minimum_sample": minimum_sample,
            "attempt_count": len(attempts),
            "reason": "maintained item metadata was not supplied",
        }
    by_item: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for attempt in attempts:
        by_item[attempt["source_item_id"]].append(attempt)
    item_metrics = []
    for item_id, records in sorted(by_item.items()):
        if len(records) < minimum_sample:
            continue
        known = [record for record in records if record["correctness"] in {"correct", "incorrect"}]
        durations = [record["completion_time_seconds"] for record in records if record["completion_time_seconds"] is not None]
        hinted = [record for record in records if record["hint_level"] is not None]
        item_metrics.append(
            {
                "item_id": item_id,
                "topic": item_metadata.get(item_id, {}).get("topic"),
                "provisional_difficulty": item_metadata.get(item_id, {}).get("difficulty"),
                "attempt_count": len(records),
                "completion_rate": len(known) / len(records),
                "correct_rate": (sum(record["correctness"] == "correct" for record in known) / len(known)) if known else None,
                "mean_completion_seconds": (sum(durations) / len(durations)) if durations else None,
                "hint_usage_rate": (sum((record["hint_level"] or 0) > 0 for record in hinted) / len(hinted)) if hinted else None,
            }
        )
    paired = [
        record
        for record in attempts
        if record["same_form_confirmation"] in {"pass", "fail"}
        and record["transfer_result"] in {"pass", "fail"}
    ]
    maintained = [record for record in attempts if record["source_item_id"] in item_metadata]
    misconception_ids = sorted(
        {
            misconception
            for metadata in item_metadata.values()
            for misconception in metadata["target_misconceptions"]
        }
    )
    discrimination = []
    for misconception in misconception_ids:
        target = [
            record
            for record in maintained
            if misconception in item_metadata[record["source_item_id"]]["target_misconceptions"]
        ]
        comparison = [
            record
            for record in maintained
            if misconception not in item_metadata[record["source_item_id"]]["target_misconceptions"]
        ]
        if len(target) < minimum_sample or len(comparison) < minimum_sample:
            continue
        target_known = [record for record in target if record["correctness"] in {"correct", "incorrect"}]
        comparison_known = [
            record for record in comparison if record["correctness"] in {"correct", "incorrect"}
        ]
        if len(target_known) < minimum_sample or len(comparison_known) < minimum_sample:
            continue
        target_rate = sum(record["correctness"] == "incorrect" for record in target_known) / len(target_known)
        comparison_rate = sum(
            record["correctness"] == "incorrect" for record in comparison_known
        ) / len(comparison_known)
        discrimination.append(
            {
                "misconception_id": misconception,
                "target_attempt_count": len(target_known),
                "target_incorrect_rate": target_rate,
                "comparison_attempt_count": len(comparison_known),
                "comparison_incorrect_rate": comparison_rate,
                "observed_incorrect_rate_difference": target_rate - comparison_rate,
            }
        )

    ranks = {"foundational": 0, "standard": 1, "challenge": 2}
    comparable_pairs = 0
    anomalies = []
    for left_index, left in enumerate(item_metrics):
        for right in item_metrics[left_index + 1 :]:
            if (
                left["topic"] is None
                or left["topic"] != right["topic"]
                or left["provisional_difficulty"] is None
                or right["provisional_difficulty"] is None
                or left["provisional_difficulty"] == right["provisional_difficulty"]
                or left["correct_rate"] is None
                or right["correct_rate"] is None
            ):
                continue
            easier, harder = (left, right)
            if ranks[easier["provisional_difficulty"]] > ranks[harder["provisional_difficulty"]]:
                easier, harder = harder, easier
            comparable_pairs += 1
            if harder["correct_rate"] > easier["correct_rate"]:
                anomalies.append(
                    {
                        "topic": easier["topic"],
                        "easier_item_id": easier["item_id"],
                        "easier_correct_rate": easier["correct_rate"],
                        "harder_item_id": harder["item_id"],
                        "harder_correct_rate": harder["correct_rate"],
                    }
                )
    ordering = {
        "status": "ready_for_review" if comparable_pairs else "insufficient_data",
        "comparison_rule": "Within one Topic, flag a higher provisional difficulty with a higher observed correct rate; this is descriptive, not a significance test.",
        "comparable_pair_count": comparable_pairs,
        "anomalies": anomalies,
    }

    if not item_metrics or len(paired) < minimum_sample or not discrimination or not comparable_pairs:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "insufficient_data",
            "minimum_sample": minimum_sample,
            "attempt_count": len(attempts),
            "item_metrics": item_metrics,
            "misconception_discrimination": discrimination,
            "difficulty_ordering": ordering,
            "reason": "item, paired confirmation/transfer, misconception comparison, or difficulty-pair samples are insufficient",
        }
    same_rate = sum(record["same_form_confirmation"] == "pass" for record in paired) / len(paired)
    transfer_rate = sum(record["transfer_result"] == "pass" for record in paired) / len(paired)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ready_for_review",
        "minimum_sample": minimum_sample,
        "attempt_count": len(attempts),
        "item_metrics": item_metrics,
        "misconception_discrimination": discrimination,
        "same_form_pass_rate": same_rate,
        "transfer_pass_rate": transfer_rate,
        "same_form_transfer_gap": same_rate - transfer_rate,
        "difficulty_ordering": ordering,
    }


def clear_test_profile(data_dir: Path, profile_id: str) -> list[str]:
    validate_profile_id(profile_id)
    marker = read_json(data_dir / TEST_MARKER)
    if marker != {"schema_version": SCHEMA_VERSION, "profile_id": profile_id, "test_data": True}:
        raise StateError("test-data marker does not match the requested profile")
    profile = read_json(data_dir / PROFILE_NAME)
    if profile.get("profile_id") != profile_id:
        raise StateError("profile.json does not match the requested test profile")
    removed = []
    for name in (PROFILE_NAME, ATTEMPTS_NAME, TEST_MARKER):
        path = data_dir / name
        if path.exists():
            path.unlink()
            removed.append(name)
    return removed


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--data-dir", required=True)
    result.add_argument("--as-of", help="fixed ISO 8601 time for deterministic operation")
    result.add_argument("--evidence-json", action="store_true")
    commands = result.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--profile-id", required=True)
    init.add_argument("--test-data", action="store_true")
    record = commands.add_parser("record")
    record.add_argument("--attempt-file", type=Path, required=True)
    commands.add_parser("rebuild")
    commands.add_parser("queue")
    summary = commands.add_parser("summarize")
    summary.add_argument("--minimum-sample", type=int, default=5)
    summary.add_argument("--items", type=Path, default=DEFAULT_ITEMS)
    summary.add_argument("--output", type=Path)
    clear = commands.add_parser("clear-test-profile")
    clear.add_argument("--profile-id", required=True)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        as_of = parse_timestamp(args.as_of, "as_of") if args.as_of else datetime.now(timezone.utc)
        data_dir = resolve_data_dir(args.data_dir, create=args.command == "init")
        if args.command == "init":
            result = initialize(data_dir, args.profile_id, as_of=as_of, test_data=args.test_data)
        elif args.command == "record":
            attempt = read_json(args.attempt_file.resolve(strict=True))
            result = record_attempt(data_dir, attempt, as_of=as_of)
        elif args.command == "rebuild":
            profile = validate_profile(read_json(data_dir / PROFILE_NAME), as_of=as_of)
            attempts = load_attempts(data_dir / ATTEMPTS_NAME, as_of=as_of)
            result = rebuild_profile(profile["profile_id"], attempts, as_of=as_of)
            atomic_write_json(data_dir / PROFILE_NAME, result)
        elif args.command == "queue":
            profile = validate_profile(read_json(data_dir / PROFILE_NAME), as_of=as_of)
            result = {"review_queue": profile["review_queue"]}
        elif args.command == "summarize":
            attempts = load_attempts(data_dir / ATTEMPTS_NAME, as_of=as_of)
            item_metadata = (
                load_calibration_items(args.items.resolve(strict=True))
                if len(attempts) >= args.minimum_sample
                else None
            )
            result = calibration_summary(
                attempts,
                args.minimum_sample,
                item_metadata,
            )
            if args.output:
                output = args.output.resolve()
                if output == SKILL_ROOT.resolve() or output.is_relative_to(SKILL_ROOT.resolve()):
                    raise StateError("de-identified export must be outside the skill repository")
                if not output.parent.exists():
                    raise StateError("export parent directory does not exist")
                atomic_write_json(output, result)
        else:
            result = {"removed": clear_test_profile(data_dir, args.profile_id)}
        payload = {"overall_status": "pass", "command": args.command, "result": result}
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        return 0
    except (StateError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        payload = {"overall_status": "error", "command": getattr(args, "command", None), "error": str(exc)}
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
