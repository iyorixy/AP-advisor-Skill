#!/usr/bin/env python3
"""Run every required local release check for AP Advisor Skills."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import os
import py_compile
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
CALC_SKILL_ROOT = ROOT / "ap-calculus-advisor"
SKILL_ROOTS = {
    "calculus": CALC_SKILL_ROOT,
    "psychology": ROOT / "ap-psychology-advisor",
    "biology": ROOT / "ap-biology-advisor",
}
COURSES = {"precalculus", "calc-ab", "calc-bc"}
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
COURSE_UNITS = {
    "precalculus": range(1, 5),
    "calc-ab": range(1, 9),
    "calc-bc": range(1, 11),
}
MIN_MISCONCEPTIONS_BY_UNIT = {
    "precalculus": {unit: 2 for unit in range(1, 5)},
    "calc-ab": {unit: 2 for unit in range(1, 9)},
    "calc-bc": {6: 1, 7: 1, 8: 1, 9: 2, 10: 2},
}
MIN_ITEMS_BY_UNIT = {
    "precalculus": {unit: 6 for unit in range(1, 5)},
    "calc-ab": {unit: 4 for unit in range(1, 9)},
    "calc-bc": {6: 3, 7: 3, 8: 3, 9: 6, 10: 6},
}
MIN_ITEMS_BY_COURSE = {"precalculus": 24, "calc-ab": 40, "calc-bc": 21}
ADAPTIVE_SCOPE = (
    "ap-precalculus-units-1-4-calculus-ab-units-1-8-calculus-bc-units-1-10"
)
REPRESENTATIONS = {"analytical", "graphical", "numerical", "tabular", "verbal"}
ITEM_FIELDS = {
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
MISCONCEPTION_FIELDS = {
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
ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class ReleaseError(ValueError):
    pass


def _json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseError(f"invalid JSON file {path.relative_to(ROOT)}: {exc}") from exc


def _jsonl(path: Path) -> list[Any]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ReleaseError(f"could not read {path.relative_to(ROOT)}: {exc}") from exc
    if not lines:
        raise ReleaseError(f"{path.relative_to(ROOT)} is empty")
    values = []
    for number, line in enumerate(lines, 1):
        if not line.strip():
            raise ReleaseError(f"{path.relative_to(ROOT)} has a blank line at {number}")
        try:
            values.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ReleaseError(f"{path.relative_to(ROOT)} line {number} is invalid JSON: {exc}") from exc
    return values


def _strings(value: Any, label: str, minimum: int = 1) -> list[str]:
    if (
        not isinstance(value, list)
        or len(value) < minimum
        or any(not isinstance(item, str) or not item for item in value)
    ):
        raise ReleaseError(f"{label} must be a unique nonempty string array")
    if len(value) != len(set(value)):
        raise ReleaseError(f"{label} must be a unique nonempty string array")
    return value


def _valid_unit(course: str, unit: Any) -> bool:
    return (
        course in COURSE_UNITS
        and isinstance(unit, int)
        and not isinstance(unit, bool)
        and unit in COURSE_UNITS[course]
    )


def _valid_topic(course: str, topic: Any, unit: int) -> bool:
    return (
        isinstance(topic, str)
        and re.fullmatch(r"(?:[1-9]|10)\.[0-9]+", topic) is not None
        and int(topic.split(".", 1)[0]) == unit
        and _valid_unit(course, unit)
    )


def _course_applies(record_course: str, learner_course: str) -> bool:
    return record_course == learner_course or (
        learner_course == "calc-bc" and record_course == "calc-ab"
    )


def _evaluate(expression: str) -> int | float | bool:
    if not isinstance(expression, str) or not expression or len(expression) > 240:
        raise ReleaseError("verification expression is empty or too long")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ReleaseError(f"invalid verification expression {expression!r}") from exc
    if sum(1 for _ in ast.walk(tree)) > 80:
        raise ReleaseError("verification expression is too complex")
    functions = {
        "sqrt": math.sqrt,
        "exp": math.exp,
        "log": math.log,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "asin": math.asin,
        "acos": math.acos,
        "atan": math.atan,
        "abs": abs,
    }
    names = {"pi": math.pi, "e": math.e, "True": True, "False": False}

    def visit(node: ast.AST) -> int | float | bool:
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float, bool)):
            return node.value
        if isinstance(node, ast.Name) and node.id in names:
            return names[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub, ast.Not)):
            value = visit(node.operand)
            return +value if isinstance(node.op, ast.UAdd) else -value if isinstance(node.op, ast.USub) else not value
        if isinstance(node, ast.BinOp) and isinstance(
            node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod)
        ):
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Pow) and isinstance(right, (int, float)) and abs(right) > 12:
                raise ReleaseError("verification exponent is too large")
            operations = {
                ast.Add: lambda: left + right,
                ast.Sub: lambda: left - right,
                ast.Mult: lambda: left * right,
                ast.Div: lambda: left / right,
                ast.Pow: lambda: left**right,
                ast.Mod: lambda: left % right,
            }
            return operations[type(node.op)]()
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in functions and not node.keywords:
            return functions[node.func.id](*(visit(argument) for argument in node.args))
        if isinstance(node, ast.Compare) and len(node.ops) == len(node.comparators):
            left = visit(node.left)
            for operator, comparator in zip(node.ops, node.comparators):
                right = visit(comparator)
                operations = {
                    ast.Eq: left == right,
                    ast.NotEq: left != right,
                    ast.Lt: left < right,
                    ast.LtE: left <= right,
                    ast.Gt: left > right,
                    ast.GtE: left >= right,
                }
                if type(operator) not in operations or not operations[type(operator)]:
                    return False
                left = right
            return True
        if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
            values = [bool(visit(value)) for value in node.values]
            return all(values) if isinstance(node.op, ast.And) else any(values)
        raise ReleaseError(f"verification expression uses forbidden syntax: {type(node).__name__}")

    try:
        result = visit(tree)
    except ReleaseError:
        raise
    except (ArithmeticError, ValueError, TypeError) as exc:
        raise ReleaseError(f"verification expression could not be evaluated: {exc}") from exc
    if isinstance(result, float) and not math.isfinite(result):
        raise ReleaseError("verification expression produced a non-finite value")
    return result


def _validate_verification(value: Any, item_id: str, answer: str, solution: str) -> int:
    if not isinstance(value, dict) or value.keys() != {
        "method",
        "independent_checks",
        "human_checkpoints",
    }:
        raise ReleaseError(f"{item_id} has invalid verification fields")
    if value["method"] not in {"exact-arithmetic", "sampled-equivalence", "logical-invariants"}:
        raise ReleaseError(f"{item_id} has an unsupported verification method")
    checkpoints = _strings(value["human_checkpoints"], f"{item_id} human_checkpoints", 2)
    if any(len(checkpoint) < 12 for checkpoint in checkpoints):
        raise ReleaseError(f"{item_id} human checkpoints are not substantive")
    checks = value["independent_checks"]
    if not isinstance(checks, list) or not checks:
        raise ReleaseError(f"{item_id} needs at least one machine-readable independent check")
    identifiers: set[str] = set()
    for check in checks:
        if not isinstance(check, dict) or check.keys() != {
            "check_id",
            "expression",
            "expected",
            "tolerance",
            "answer_claim",
        }:
            raise ReleaseError(f"{item_id} has invalid independent-check fields")
        check_id = check["check_id"]
        if not isinstance(check_id, str) or not ID_RE.fullmatch(check_id) or check_id in identifiers:
            raise ReleaseError(f"{item_id} has an invalid or duplicate check_id")
        identifiers.add(check_id)
        claim = check["answer_claim"]
        if (
            not isinstance(claim, str)
            or not claim.strip()
            or (
                claim.strip().casefold() not in answer.casefold()
                and claim.strip().casefold() not in solution.casefold()
            )
        ):
            raise ReleaseError(f"{item_id}/{check_id} is not bound to an answer/solution claim")
        expected, tolerance = check["expected"], check["tolerance"]
        if (
            not isinstance(expected, (int, float, bool))
            or (isinstance(expected, float) and not math.isfinite(expected))
            or isinstance(tolerance, bool)
            or not isinstance(tolerance, (int, float))
            or not math.isfinite(float(tolerance))
            or tolerance < 0
        ):
            raise ReleaseError(f"{item_id}/{check_id} has invalid expected value or tolerance")
        actual = _evaluate(check["expression"])
        if isinstance(expected, bool):
            passed = isinstance(actual, bool) and actual is expected
        else:
            passed = not isinstance(actual, bool) and math.isclose(float(actual), float(expected), rel_tol=0.0, abs_tol=float(tolerance))
        if not passed:
            raise ReleaseError(f"{item_id}/{check_id} evaluated to {actual!r}, expected {expected!r}")
    return len(checks)


def _validate_math_audit(
    value: Any,
    items: dict[str, dict[str, Any]],
    raw_lines: list[str],
    artifact_bytes: bytes,
) -> int:
    required = {
        "schema_version",
        "artifact",
        "artifact_sha256",
        "hash_algorithm",
        "author_context_id",
        "reviewer_context_id",
        "independent_from_authoring",
        "reviewed_at",
        "entries",
    }
    if not isinstance(value, dict) or value.keys() != required:
        raise ReleaseError("math audit manifest has missing or unexpected fields")
    if (
        value["schema_version"] != 1
        or value["artifact"] != "references/diagnostic-items.jsonl"
        or value["hash_algorithm"] != "sha256"
        or value["independent_from_authoring"] is not True
    ):
        raise ReleaseError("math audit manifest has invalid provenance metadata")
    for field in ("author_context_id", "reviewer_context_id"):
        if not isinstance(value[field], str) or not value[field].strip():
            raise ReleaseError(f"math audit {field} must be a nonempty string")
    if value["author_context_id"] == value["reviewer_context_id"]:
        raise ReleaseError("math audit reviewer context must be independent from authoring")
    if not isinstance(value["reviewed_at"], str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value["reviewed_at"]
    ):
        raise ReleaseError("math audit reviewed_at must be an explicit UTC timestamp")
    artifact_digest = hashlib.sha256(artifact_bytes).hexdigest()
    if value["artifact_sha256"] != artifact_digest:
        raise ReleaseError("math audit artifact digest does not match the diagnostic bank")
    entries = value["entries"]
    if not isinstance(entries, list) or len(entries) != len(items):
        raise ReleaseError("math audit must contain exactly one entry per diagnostic item")
    raw_by_id: dict[str, str] = {}
    for raw in raw_lines:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ReleaseError("math audit could not parse a diagnostic item line") from exc
        if not isinstance(parsed, dict) or not isinstance(parsed.get("item_id"), str):
            raise ReleaseError("math audit encountered an item without an item_id")
        raw_by_id[parsed["item_id"]] = raw
    audited: set[str] = set()
    entry_fields = {
        "item_id",
        "line_sha256",
        "verdict",
        "checked_answer",
        "checked_check_ids",
        "math_notes",
    }
    for entry in entries:
        if not isinstance(entry, dict) or entry.keys() != entry_fields:
            raise ReleaseError("math audit entry has missing or unexpected fields")
        item_id = entry["item_id"]
        if item_id not in items or item_id in audited:
            raise ReleaseError("math audit contains an unknown or duplicate item_id")
        audited.add(item_id)
        if entry["verdict"] != "pass":
            raise ReleaseError(f"math audit did not pass {item_id}")
        expected_line_digest = hashlib.sha256(raw_by_id[item_id].encode("utf-8")).hexdigest()
        if entry["line_sha256"] != expected_line_digest:
            raise ReleaseError(f"math audit line digest does not match {item_id}")
        answer = items[item_id]["answer"]
        if not isinstance(entry["checked_answer"], str) or " ".join(
            entry["checked_answer"].split()
        ) != " ".join(answer.split()):
            raise ReleaseError(f"math audit checked answer does not match {item_id}")
        check_ids = [
            check["check_id"] for check in items[item_id]["verification"]["independent_checks"]
        ]
        if (
            not isinstance(entry["checked_check_ids"], list)
            or entry["checked_check_ids"] != check_ids
        ):
            raise ReleaseError(f"math audit check IDs do not match {item_id}")
        if not isinstance(entry["math_notes"], str) or len(entry["math_notes"]) < 30:
            raise ReleaseError(f"math audit notes are not substantive for {item_id}")
    if audited != set(items):
        raise ReleaseError("math audit item coverage is incomplete")
    return len(audited)


def _check_cycle(graph: dict[str, dict[str, Any]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(identifier: str) -> None:
        if identifier in visiting:
            raise ReleaseError(f"misconception prerequisite cycle includes {identifier}")
        if identifier in visited:
            return
        visiting.add(identifier)
        for dependency in graph[identifier]["prerequisites"]:
            visit(dependency)
        visiting.remove(identifier)
        visited.add(identifier)

    for identifier in graph:
        visit(identifier)


def _validate_chain_design(
    misconception_id: str,
    diagnostic: dict[str, Any],
    confirmation: dict[str, Any],
    transfer: dict[str, Any],
    prerequisites: list[str],
) -> None:
    expected_prerequisites = set(prerequisites)
    if any(
        set(item["prerequisites"]) != expected_prerequisites
        for item in (diagnostic, confirmation, transfer)
    ):
        raise ReleaseError(
            f"{misconception_id} graph and diagnostic chain prerequisites do not match"
        )
    if any(
        diagnostic[field] != confirmation[field]
        for field in ("task_type", "representation")
    ) or any(
        diagnostic["selection"][field] != confirmation["selection"][field]
        for field in ("representation_family", "context_family")
    ):
        raise ReleaseError(
            f"{misconception_id} confirmation item is not the same form as its diagnostic"
        )
    if all(
        diagnostic["selection"][field] == transfer["selection"][field]
        for field in ("representation_family", "context_family")
    ):
        raise ReleaseError(
            f"{misconception_id} transfer item changes neither representation nor context family"
        )


def validate_adaptive_artifacts() -> dict[str, Any]:
    graph_path = CALC_SKILL_ROOT / "references" / "calculus-misconceptions.json"
    items_path = CALC_SKILL_ROOT / "references" / "diagnostic-items.jsonl"
    graph_value = _json_file(graph_path)
    if not isinstance(graph_value, dict) or graph_value.keys() != {"schema_version", "scope", "status", "misconceptions"}:
        raise ReleaseError("misconception graph has missing or unexpected top-level fields")
    if (
        graph_value["schema_version"] != 1
        or graph_value["scope"] != ADAPTIVE_SCOPE
        or graph_value["status"] != "internal-teaching-diagnostics-not-official"
        or not isinstance(graph_value["misconceptions"], list)
    ):
        raise ReleaseError("misconception graph has invalid scope/status metadata")
    graph: dict[str, dict[str, Any]] = {}
    for record in graph_value["misconceptions"]:
        if not isinstance(record, dict) or record.keys() != MISCONCEPTION_FIELDS:
            raise ReleaseError("misconception graph contains invalid record fields")
        identifier = record["misconception_id"]
        if not isinstance(identifier, str) or not ID_RE.fullmatch(identifier) or identifier in graph:
            raise ReleaseError("misconception graph contains an invalid or duplicate ID")
        if record["internal_diagnostic"] is not True:
            raise ReleaseError(f"{identifier} is not labeled as an internal teaching diagnostic")
        course = record["course"]
        if course not in COURSES:
            raise ReleaseError(f"{identifier} has invalid course metadata")
        if not _valid_unit(course, record["unit"]):
            raise ReleaseError(f"{identifier} has invalid Unit")
        if not _valid_topic(course, record["topic"], record["unit"]):
            raise ReleaseError(f"{identifier} has invalid Topic metadata")
        if record["practice"] not in PRACTICES[course]:
            raise ReleaseError(f"{identifier} has invalid Practice metadata")
        for field in ("observable_features", "evidence_required", "alternative_causes"):
            values = _strings(record[field], f"{identifier} {field}")
            if any(len(value) < 12 for value in values):
                raise ReleaseError(f"{identifier} {field} is not substantive")
        prerequisites = _strings(record["prerequisites"], f"{identifier} prerequisites", 0)
        if identifier in prerequisites:
            raise ReleaseError(f"{identifier} cannot depend on itself")
        rationale = record["prerequisite_rationale"]
        if not isinstance(rationale, dict) or set(rationale) != set(prerequisites) or any(
            not isinstance(reason, str) or len(reason) < 12 for reason in rationale.values()
        ):
            raise ReleaseError(f"{identifier} prerequisite rationale does not match its edges")
        for field in (
            "minimum_remediation",
            "exit_standard",
            "uncertain_action",
        ):
            if not isinstance(record[field], str) or len(record[field]) < 20:
                raise ReleaseError(f"{identifier} has incomplete {field}")
        for field in ("diagnostic_item_id", "confirmation_item_id", "transfer_item_id"):
            if not isinstance(record[field], str) or not ID_RE.fullmatch(record[field]):
                raise ReleaseError(f"{identifier} has invalid {field}")
        graph[identifier] = record
    course_patterns = Counter(record["course"] for record in graph.values())
    minimum_patterns = {course: sum(units.values()) for course, units in MIN_MISCONCEPTIONS_BY_UNIT.items()}
    if any(course_patterns[course] < minimum for course, minimum in minimum_patterns.items()):
        raise ReleaseError(
            f"misconception graph lacks per-course coverage: {dict(sorted(course_patterns.items()))}"
        )
    unit_patterns = Counter((record["course"], record["unit"]) for record in graph.values())
    for course, minimums in MIN_MISCONCEPTIONS_BY_UNIT.items():
        for unit, minimum in minimums.items():
            if unit_patterns[course, unit] < minimum:
                raise ReleaseError(
                    f"{course} Unit {unit} needs at least {minimum} diagnostic pattern(s)"
                )
    edge_count = sum(len(record["prerequisites"]) for record in graph.values())
    ab_edge_count = sum(
        len(record["prerequisites"])
        for record in graph.values()
        if record["course"] == "calc-ab"
    )
    if ab_edge_count < 4:
        raise ReleaseError("Calculus AB needs maintained, explained prerequisite edges")
    for record in graph.values():
        missing = set(record["prerequisites"]) - set(graph)
        if missing:
            raise ReleaseError(f"{record['misconception_id']} has dangling prerequisites: {sorted(missing)}")
        incompatible = [
            prerequisite
            for prerequisite in record["prerequisites"]
            if not _course_applies(graph[prerequisite]["course"], record["course"])
        ]
        if incompatible:
            raise ReleaseError(
                f"{record['misconception_id']} has cross-course prerequisites: {sorted(incompatible)}"
            )
    _check_cycle(graph)

    item_bytes = items_path.read_bytes()
    raw_item_lines = item_bytes.decode("utf-8").splitlines()
    item_records = _jsonl(items_path)
    items: dict[str, dict[str, Any]] = {}
    check_count = 0
    forbidden_source_markers = ("AP Classroom", "Progress Check", "Practice Exam", "College Board approved")
    for line_number, item in enumerate(item_records, 1):
        if not isinstance(item, dict) or item.keys() != ITEM_FIELDS:
            raise ReleaseError(f"diagnostic item line {line_number} has missing or unexpected fields")
        identifier = item["item_id"]
        if not isinstance(identifier, str) or not ID_RE.fullmatch(identifier) or identifier in items:
            raise ReleaseError(f"diagnostic item line {line_number} has an invalid or duplicate item_id")
        course = item["course"]
        if item["schema_version"] != 1 or course not in COURSES:
            raise ReleaseError(f"{identifier} has invalid schema/course metadata")
        if not _valid_unit(course, item["unit"]):
            raise ReleaseError(f"{identifier} has invalid Unit")
        if not _valid_topic(course, item["topic_code"], item["unit"]):
            raise ReleaseError(f"{identifier} has invalid Topic code")
        if not isinstance(item["topic_citation"], str) or not item["topic_citation"].startswith(
            f"Unit {item['unit']}, Topic {item['topic_code']} — "
        ):
            raise ReleaseError(f"{identifier} has invalid canonical Topic citation")
        if item["mathematical_practice"] not in PRACTICES[course]:
            raise ReleaseError(f"{identifier} has invalid Practice")
        if item["task_type"] not in {"multiple-choice", "free-response"}:
            raise ReleaseError(f"{identifier} has invalid task type")
        if item["representation"] not in REPRESENTATIONS:
            raise ReleaseError(f"{identifier} has invalid representation")
        if item["calculator_condition"] not in {"calculator-not-permitted", "calculator-required-section"}:
            raise ReleaseError(f"{identifier} has invalid calculator condition")
        if item["justification_requirement"] not in {"required", "not-required"}:
            raise ReleaseError(f"{identifier} has invalid justification requirement")
        difficulty = item["difficulty"]
        if (
            not isinstance(difficulty, dict)
            or difficulty.keys() != {"label", "status", "observable_basis"}
            or difficulty["label"] not in {"foundational", "standard", "challenge"}
            or difficulty["status"] != "provisional"
            or not isinstance(difficulty["observable_basis"], str)
            or len(difficulty["observable_basis"]) < 20
        ):
            raise ReleaseError(f"{identifier} has invalid provisional difficulty metadata")
        prerequisites = _strings(item["prerequisites"], f"{identifier} prerequisites", 0)
        targets = _strings(item["target_misconceptions"], f"{identifier} target_misconceptions")
        if set(prerequisites) - set(graph) or set(targets) - set(graph):
            raise ReleaseError(f"{identifier} has dangling misconception references")
        if any(not _course_applies(graph[reference]["course"], course) for reference in prerequisites + targets):
            raise ReleaseError(f"{identifier} has cross-course misconception references")
        if any(graph[target]["unit"] != item["unit"] for target in targets):
            raise ReleaseError(f"{identifier} targets a misconception from another Unit")
        if not isinstance(item["prompt"], str) or len(item["prompt"]) < 30:
            raise ReleaseError(f"{identifier} has an incomplete prompt")
        if any(marker.casefold() in item["prompt"].casefold() for marker in forbidden_source_markers):
            raise ReleaseError(f"{identifier} prompt contains a prohibited source/approval marker")
        if not isinstance(item["answer"], str) or len(item["answer"]) < 2:
            raise ReleaseError(f"{identifier} has an incomplete exact answer")
        if not isinstance(item["solution"], str) or len(item["solution"]) < 40:
            raise ReleaseError(f"{identifier} has an incomplete solution/scoring explanation")
        check_count += _validate_verification(
            item["verification"], identifier, item["answer"], item["solution"]
        )
        hints = _strings(item["hint_ladder"], f"{identifier} hint_ladder", 2)
        direct_answer_leak = any(
            hint.strip().casefold() == item["answer"].strip().casefold()
            or (
                len(item["answer"].strip()) >= 12
                and item["answer"].strip().casefold() in hint.casefold()
            )
            for hint in hints
        )
        if any(len(hint) < 10 for hint in hints) or item["solution"] in hints or direct_answer_leak:
            raise ReleaseError(f"{identifier} has an invalid or directly answer-leaking hint ladder")
        distractors, errors = item["distractor_diagnoses"], item["error_response_diagnoses"]
        if not isinstance(distractors, dict) or not isinstance(errors, dict):
            raise ReleaseError(f"{identifier} diagnosis fields must be objects")
        if item["task_type"] == "multiple-choice":
            if len(distractors) < 3 or errors:
                raise ReleaseError(f"{identifier} MCQ needs at least three distractor diagnoses and no FRQ error map")
        elif len(errors) < 2 or distractors:
            raise ReleaseError(f"{identifier} FRQ needs at least two error-response diagnoses and no distractor map")
        for mapping in (distractors, errors):
            if any(not isinstance(key, str) or not key or not isinstance(value, str) or len(value) < 12 for key, value in mapping.items()):
                raise ReleaseError(f"{identifier} has incomplete response diagnoses")
        for field in ("same_form_confirmation_item_id", "transfer_item_id"):
            if not isinstance(item[field], str) or not ID_RE.fullmatch(item[field]):
                raise ReleaseError(f"{identifier} has invalid {field}")
        if item["answer_visibility"] != "hidden":
            raise ReleaseError(f"{identifier} must default to hidden")
        selection = item["selection"]
        if not isinstance(selection, dict) or selection.keys() != {
            "stage", "priority", "expected_time_seconds", "exit_eligible", "representation_family", "context_family"
        }:
            raise ReleaseError(f"{identifier} has invalid selection fields")
        if selection["stage"] not in {"diagnostic", "confirmation", "transfer", "retest"}:
            raise ReleaseError(f"{identifier} has invalid selection stage")
        if not isinstance(selection["priority"], int) or isinstance(selection["priority"], bool) or selection["priority"] < 0:
            raise ReleaseError(f"{identifier} has invalid selection priority")
        if not isinstance(selection["expected_time_seconds"], int) or isinstance(selection["expected_time_seconds"], bool) or selection["expected_time_seconds"] <= 0:
            raise ReleaseError(f"{identifier} has invalid expected time")
        if not isinstance(selection["exit_eligible"], bool):
            raise ReleaseError(f"{identifier} has invalid exit eligibility")
        if selection["exit_eligible"] is not (
            selection["stage"] in {"transfer", "retest"}
        ):
            raise ReleaseError(f"{identifier} exit eligibility contradicts its selection stage")
        if any(not isinstance(selection[field], str) or not selection[field] for field in ("representation_family", "context_family")):
            raise ReleaseError(f"{identifier} has invalid selection family metadata")
        items[identifier] = item
    course_items = Counter(item["course"] for item in items.values())
    if any(course_items[course] < minimum for course, minimum in MIN_ITEMS_BY_COURSE.items()):
        raise ReleaseError(
            f"diagnostic bank lacks per-course coverage: {dict(sorted(course_items.items()))}"
        )
    unit_items = Counter((item["course"], item["unit"]) for item in items.values())
    for course, minimums in MIN_ITEMS_BY_UNIT.items():
        for unit, minimum in minimums.items():
            if unit_items[course, unit] < minimum:
                raise ReleaseError(
                    f"{course} Unit {unit} needs at least {minimum} diagnostic item(s)"
                )
    course_representations = {
        course: {item["representation"] for item in items.values() if item["course"] == course}
        for course in COURSES
    }
    if course_representations["calc-ab"] != REPRESENTATIONS:
        raise ReleaseError("Calculus AB diagnostic items must cover all five representations")
    if any(len(course_representations[course]) < 3 for course in ("precalculus", "calc-bc")):
        raise ReleaseError("Precalculus and Calculus BC diagnostic items each need at least three representations")
    task_counts = Counter((item["course"], item["task_type"]) for item in items.values())
    if min(task_counts["calc-ab", "multiple-choice"], task_counts["calc-ab", "free-response"]) < 8:
        raise ReleaseError("Calculus AB needs meaningful MCQ and FRQ coverage")
    for course in ("precalculus", "calc-bc"):
        if min(task_counts[course, "multiple-choice"], task_counts[course, "free-response"]) < 3:
            raise ReleaseError(f"{course} needs meaningful MCQ and FRQ coverage")
    for course, units in MIN_ITEMS_BY_UNIT.items():
        for unit in units:
            records = [
                item
                for item in items.values()
                if item["course"] == course and item["unit"] == unit
            ]
            practices = {item["mathematical_practice"] for item in records}
            if course == "precalculus":
                if practices != PRACTICES[course]:
                    raise ReleaseError(f"{course} Unit {unit} lacks all three mathematical practices")
            elif not {"calc-1-implementing-processes", "calc-2-connecting-representations"} <= practices or not practices & {
                "calc-3-justification", "calc-4-communication-notation"
            }:
                raise ReleaseError(
                    f"{course} Unit {unit} lacks process, representation, and justification/communication coverage"
                )
            if {item["difficulty"]["label"] for item in records} != {"foundational", "standard", "challenge"}:
                raise ReleaseError(f"{course} Unit {unit} lacks all three provisional difficulty labels")
            if not {"diagnostic", "confirmation", "transfer"} <= {item["selection"]["stage"] for item in records}:
                raise ReleaseError(f"{course} Unit {unit} lacks diagnostic, confirmation, and transfer stages")
    for identifier, item in items.items():
        if item["same_form_confirmation_item_id"] not in items or item["transfer_item_id"] not in items:
            raise ReleaseError(f"{identifier} has dangling confirmation/transfer item links")
        if any(
            items[item[link]]["course"] != item["course"]
            for link in ("same_form_confirmation_item_id", "transfer_item_id")
        ):
            raise ReleaseError(f"{identifier} has cross-course confirmation/transfer item links")
    for identifier, record in graph.items():
        linked = {
            "diagnostic": record["diagnostic_item_id"],
            "confirmation": record["confirmation_item_id"],
            "transfer": record["transfer_item_id"],
        }
        for stage, item_id in linked.items():
            if item_id not in items:
                raise ReleaseError(f"{identifier} has dangling {stage} item {item_id}")
            item = items[item_id]
            if (
                item["course"] != record["course"]
                or item["selection"]["stage"] != stage
                or identifier not in item["target_misconceptions"]
            ):
                raise ReleaseError(f"{identifier} {stage} item has inconsistent stage/target metadata")
        _validate_chain_design(
            identifier,
            items[linked["diagnostic"]],
            items[linked["confirmation"]],
            items[linked["transfer"]],
            record["prerequisites"],
        )
        if items[linked["diagnostic"]]["same_form_confirmation_item_id"] != linked["confirmation"]:
            raise ReleaseError(f"{identifier} diagnostic-to-confirmation link is inconsistent")
        if items[linked["diagnostic"]]["transfer_item_id"] != linked["transfer"]:
            raise ReleaseError(f"{identifier} diagnostic-to-transfer link is inconsistent")
    audited_item_count = _validate_math_audit(
        _json_file(ROOT / "evals" / "math-audit.json"),
        items,
        raw_item_lines,
        item_bytes,
    )
    return {
        "misconception_count": len(graph),
        "course_misconception_counts": dict(sorted(course_patterns.items())),
        "unit_misconception_counts": {
            course: {
                unit: unit_patterns[course, unit]
                for unit in MIN_MISCONCEPTIONS_BY_UNIT[course]
            }
            for course in sorted(COURSES)
        },
        "prerequisite_edge_count": edge_count,
        "calculus_ab_prerequisite_edge_count": ab_edge_count,
        "item_count": len(items),
        "course_item_counts": dict(sorted(course_items.items())),
        "unit_item_counts": {
            course: {unit: unit_items[course, unit] for unit in MIN_ITEMS_BY_UNIT[course]}
            for course in sorted(COURSES)
        },
        "task_type_counts": {
            course: {
                task_type: task_counts[course, task_type]
                for task_type in ("multiple-choice", "free-response")
            }
            for course in sorted(COURSES)
        },
        "representation_counts": {
            course: len(course_representations[course]) for course in sorted(COURSES)
        },
        "machine_math_check_count": check_count,
        "independently_audited_item_count": audited_item_count,
        "topic_citations": sorted({item["topic_citation"] for item in items.values()}),
        "topic_citations_by_course": {
            course: sorted(
                {
                    item["topic_citation"]
                    for item in items.values()
                    if item["course"] == course
                }
            )
            for course in sorted(COURSES)
        },
        "precalculus_instructional_topic_citations": sorted(
            {
                item["topic_citation"]
                for item in items.values()
                if item["course"] == "precalculus" and item["unit"] == 4
            }
        ),
    }


def validate_repository_files() -> dict[str, Any]:
    required = [
        "ap-calculus-advisor/SKILL.md",
        "ap-calculus-advisor/LICENSE",
        "ap-calculus-advisor/agents/openai.yaml",
        "ap-calculus-advisor/assets/ap-advisor-icon.png",
        "ap-calculus-advisor/references/assessment-tasks.md",
        "ap-calculus-advisor/references/evidence-review.md",
        "ap-calculus-advisor/references/session-protocol.md",
        "ap-calculus-advisor/references/learner-state.schema.json",
        "ap-calculus-advisor/references/calculus-misconceptions.json",
        "ap-calculus-advisor/references/diagnostic-items.jsonl",
        "ap-calculus-advisor/scripts/validate_topic_code.py",
        "ap-calculus-advisor/scripts/update_learner_state.py",
        "ap-calculus-advisor/scripts/select_next_task.py",
        "ap-psychology-advisor/SKILL.md",
        "ap-psychology-advisor/LICENSE",
        "ap-psychology-advisor/agents/openai.yaml",
        "ap-psychology-advisor/assets/ap-advisor-icon.png",
        "ap-psychology-advisor/references/session-protocol.md",
        "ap-psychology-advisor/references/evidence-review.md",
        "ap-psychology-advisor/scripts/validate_topic_code.py",
        "ap-biology-advisor/SKILL.md",
        "ap-biology-advisor/LICENSE",
        "ap-biology-advisor/agents/openai.yaml",
        "ap-biology-advisor/assets/ap-advisor-icon.png",
        "ap-biology-advisor/references/session-protocol.md",
        "ap-biology-advisor/references/evidence-review.md",
        "ap-biology-advisor/scripts/validate_topic_code.py",
        "evals/case-schema.json",
        "evals/review-schema.json",
        "evals/cases.jsonl",
        "evals/math-audit.json",
        "evals/blind-run-manifest.json",
        "evals/regression-summary.json",
        "evals/release-reviews.jsonl",
        "scripts/run_evals.py",
        "scripts/check_release.py",
        "tests/test_evals.py",
        "tests/test_learner_state.py",
        "tests/test_output_contract.py",
        "tests/test_release_gate.py",
        "tests/test_selector.py",
        "tests/test_validator.py",
        "README.md",
        "README.zh-CN.md",
        "README.zh-TW.md",
    ]
    missing = [path for path in required if not (ROOT / path).is_file()]
    if missing:
        raise ReleaseError(f"required release artifacts are missing: {missing}")
    json_count = 0
    jsonl_count = 0
    for path in ROOT.rglob("*.json"):
        if ".git" not in path.parts:
            _json_file(path)
            json_count += 1
    for path in ROOT.rglob("*.jsonl"):
        if ".git" not in path.parts:
            _jsonl(path)
            jsonl_count += 1
    cache_paths = [
        str(path.relative_to(ROOT))
        for path in ROOT.rglob("*")
        if path.name == "__pycache__" or path.suffix == ".pyc"
    ]
    if cache_paths:
        raise ReleaseError(f"generated Python cache artifacts are present: {cache_paths}")
    learner_data = [
        str(path.relative_to(ROOT))
        for name in ("profile.json", "attempts.jsonl", ".ap-calculus-test-data")
        for path in ROOT.rglob(name)
    ]
    if learner_data:
        raise ReleaseError(f"learner/test profile data is present in the repository: {learner_data}")
    broken_links = []
    link_re = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    for markdown in ROOT.rglob("*.md"):
        if ".git" in markdown.parts:
            continue
        for target in link_re.findall(markdown.read_text(encoding="utf-8")):
            target = target.strip().strip("<>")
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            local = target.split("#", 1)[0]
            if local and not (markdown.parent / local).resolve().exists():
                broken_links.append(f"{markdown.relative_to(ROOT)} -> {target}")
    if broken_links:
        raise ReleaseError(f"broken relative Markdown links: {broken_links}")
    broken_icons = []
    nested_skills = []
    for label, skill_root in SKILL_ROOTS.items():
        if list(skill_root.rglob("SKILL.md")) != [skill_root / "SKILL.md"]:
            nested_skills.append(label)
        yaml = (skill_root / "agents" / "openai.yaml").read_text(encoding="utf-8")
        icons = re.findall(r"^\s*icon_(?:small|large):\s*[\"']?([^\"'\r\n]+)", yaml, re.MULTILINE)
        if len(icons) != 2 or any(not (skill_root / icon.strip()).resolve().is_file() for icon in icons):
            broken_icons.append(label)
    if broken_icons:
        raise ReleaseError(f"skills have missing or broken icon paths: {broken_icons}")
    if nested_skills:
        raise ReleaseError(f"skill packages contain nested or missing SKILL.md files: {nested_skills}")
    return {
        "required_artifact_count": len(required),
        "json_file_count": json_count,
        "jsonl_file_count": jsonl_count,
        "skill_icon_count": len(SKILL_ROOTS),
    }


def _validate_blind_manifest(value: Any, reviews: list[Any]) -> dict[str, Any]:
    required = {
        "schema_version",
        "raw_output_directory_id",
        "created_at",
        "source_manifest_sha256",
        "aggregate_sha256",
        "records",
    }
    if not isinstance(value, dict) or value.keys() != required or value["schema_version"] != 1:
        raise ReleaseError("blind-run manifest has missing or unexpected fields")
    directory_id = value["raw_output_directory_id"]
    if (
        not isinstance(directory_id, str)
        or not re.fullmatch(r"[A-Za-z0-9._-]{8,128}", directory_id)
        or "/" in directory_id
        or "\\" in directory_id
    ):
        raise ReleaseError("blind-run manifest must use a safe temporary-directory identifier")
    if not isinstance(value["created_at"], str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value["created_at"]
    ):
        raise ReleaseError("blind-run manifest created_at must be an explicit UTC timestamp")
    for field in ("source_manifest_sha256", "aggregate_sha256"):
        if not isinstance(value[field], str) or not re.fullmatch(r"[0-9a-f]{64}", value[field]):
            raise ReleaseError(f"blind-run manifest has invalid {field}")
    records = value["records"]
    if not isinstance(records, list) or len(records) < 50:
        raise ReleaseError("blind-run manifest needs all 40 primary and at least 10 repeat records")
    expected_digest = hashlib.sha256(
        json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if value["aggregate_sha256"] != expected_digest:
        raise ReleaseError("blind-run manifest aggregate digest does not match its records")
    record_fields = {"case_id", "round_id", "forward_context_id", "raw_output_sha256"}
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    contexts: set[str] = set()
    for record in records:
        if not isinstance(record, dict) or record.keys() != record_fields:
            raise ReleaseError("blind-run manifest record has missing or unexpected fields")
        key = (record["case_id"], record["round_id"])
        if (
            not isinstance(record["case_id"], str)
            or not re.fullmatch(r"(?:REV|ADV|COA|GEN|BND)-[0-9]{3}", record["case_id"])
            or record["round_id"] not in {"primary", "repeat"}
            or key in by_key
        ):
            raise ReleaseError("blind-run manifest has an invalid or duplicate case round")
        context = record["forward_context_id"]
        if not isinstance(context, str) or len(context) < 3 or context in contexts:
            raise ReleaseError("blind-run manifest reused or omitted a forward context")
        contexts.add(context)
        if not isinstance(record["raw_output_sha256"], str) or not re.fullmatch(
            r"[0-9a-f]{64}", record["raw_output_sha256"]
        ):
            raise ReleaseError("blind-run manifest has an invalid raw-output digest")
        by_key[key] = record
    primary_count = sum(key[1] == "primary" for key in by_key)
    repeat_count = sum(key[1] == "repeat" for key in by_key)
    if primary_count != 40 or repeat_count < 10:
        raise ReleaseError("blind-run manifest has incomplete primary/repeat coverage")
    review_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for review in reviews:
        if not isinstance(review, dict):
            raise ReleaseError("release review must be a JSON object")
        key = (review.get("case_id"), review.get("round_id"))
        if key in review_by_key:
            raise ReleaseError("release reviews contain a duplicate case round")
        review_by_key[key] = review
    if set(review_by_key) != set(by_key):
        raise ReleaseError("blind-run manifest and release reviews cover different case rounds")
    for key, record in by_key.items():
        review = review_by_key[key]
        if (
            review.get("forward_context_id") != record["forward_context_id"]
            or review.get("raw_output_sha256") != record["raw_output_sha256"]
        ):
            raise ReleaseError(f"blind-run provenance does not match review {key[0]}/{key[1]}")
    return {
        "primary_record_count": primary_count,
        "repeat_record_count": repeat_count,
        "unique_forward_context_count": len(contexts),
        "source_manifest_sha256": value["source_manifest_sha256"],
    }


def validate_blind_run_provenance() -> dict[str, Any]:
    return _validate_blind_manifest(
        _json_file(ROOT / "evals" / "blind-run-manifest.json"),
        _jsonl(ROOT / "evals" / "release-reviews.jsonl"),
    )


def _validate_regression_summary(
    value: Any,
    blind_manifest: dict[str, Any],
) -> dict[str, Any]:
    fields = {
        "schema_version",
        "baseline_snapshot_id",
        "baseline_review_sha256",
        "final_forward_source_manifest_sha256",
        "reviewer_context_id",
        "reviewer_independent",
        "case_count",
        "baseline_passed",
        "final_passed",
        "retained_baseline_passes",
        "regressed_case_ids",
        "improved_case_ids",
        "failed_case_ids",
        "overall_status",
        "cases",
    }
    if not isinstance(value, dict) or value.keys() != fields or value["schema_version"] != 1:
        raise ReleaseError("regression summary has missing or unexpected fields")
    if (
        not isinstance(value["baseline_snapshot_id"], str)
        or not re.fullmatch(r"[A-Za-z0-9._-]{8,128}", value["baseline_snapshot_id"])
    ):
        raise ReleaseError("regression summary has an invalid baseline snapshot ID")
    for field in ("baseline_review_sha256", "final_forward_source_manifest_sha256"):
        if not isinstance(value[field], str) or not re.fullmatch(r"[0-9a-f]{64}", value[field]):
            raise ReleaseError(f"regression summary has invalid {field}")
    if value["final_forward_source_manifest_sha256"] != blind_manifest.get("source_manifest_sha256"):
        raise ReleaseError("regression summary and blind manifest reference different forward runs")
    reviewer = value["reviewer_context_id"]
    if not isinstance(reviewer, str) or len(reviewer) < 3 or value["reviewer_independent"] is not True:
        raise ReleaseError("regression summary lacks an independent reviewer context")
    blind_contexts = {
        record["forward_context_id"] for record in blind_manifest.get("records", [])
        if isinstance(record, dict) and isinstance(record.get("forward_context_id"), str)
    }
    if reviewer in blind_contexts:
        raise ReleaseError("regression reviewer context overlaps a blind forward context")
    entries = value["cases"]
    entry_fields = {
        "case_id",
        "forward_context_id",
        "baseline_passed",
        "final_passed",
        "final_raw_output_sha256",
        "evidence",
    }
    if not isinstance(entries, list) or len(entries) != 16:
        raise ReleaseError("regression summary must contain exactly 16 fixed cases")
    ids: set[str] = set()
    regression_contexts: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or entry.keys() != entry_fields:
            raise ReleaseError("regression case has missing or unexpected fields")
        case_id = entry["case_id"]
        context = entry["forward_context_id"]
        if not isinstance(case_id, str) or not case_id or case_id in ids:
            raise ReleaseError("regression summary has an invalid or duplicate case ID")
        ids.add(case_id)
        if (
            not isinstance(context, str)
            or len(context) < 3
            or context in regression_contexts
            or context in blind_contexts
            or context == reviewer
        ):
            raise ReleaseError("regression summary reused or omitted an independent forward context")
        regression_contexts.add(context)
        if not isinstance(entry["baseline_passed"], bool) or not isinstance(entry["final_passed"], bool):
            raise ReleaseError(f"regression case {case_id} lacks boolean judgments")
        if not isinstance(entry["final_raw_output_sha256"], str) or not re.fullmatch(
            r"[0-9a-f]{64}", entry["final_raw_output_sha256"]
        ):
            raise ReleaseError(f"regression case {case_id} has an invalid output digest")
        if not isinstance(entry["evidence"], str) or len(entry["evidence"]) < 12:
            raise ReleaseError(f"regression case {case_id} lacks substantive evidence")
    baseline_passed = sum(entry["baseline_passed"] for entry in entries)
    final_passed = sum(entry["final_passed"] for entry in entries)
    retained = sum(entry["baseline_passed"] and entry["final_passed"] for entry in entries)
    regressed = sorted(entry["case_id"] for entry in entries if entry["baseline_passed"] and not entry["final_passed"])
    improved = sorted(entry["case_id"] for entry in entries if not entry["baseline_passed"] and entry["final_passed"])
    failed = sorted(entry["case_id"] for entry in entries if not entry["final_passed"])
    declared_lists = {
        "regressed_case_ids": regressed,
        "improved_case_ids": improved,
        "failed_case_ids": failed,
    }
    if any(value[field] != expected for field, expected in declared_lists.items()):
        raise ReleaseError("regression summary derived case lists are inconsistent")
    if (
        value["case_count"] != 16
        or value["baseline_passed"] != baseline_passed
        or value["final_passed"] != final_passed
        or value["retained_baseline_passes"] != retained
        or baseline_passed != 12
    ):
        raise ReleaseError("regression summary counts are inconsistent with the fixed baseline")
    passed = not regressed and retained == baseline_passed and final_passed >= baseline_passed
    if value["overall_status"] != ("pass" if passed else "fail") or not passed:
        raise ReleaseError("fixed-set regression acceptance did not pass")
    return {
        "case_count": 16,
        "baseline_passed": baseline_passed,
        "final_passed": final_passed,
        "retained_baseline_passes": retained,
        "improved_case_count": len(improved),
        "regressed_case_ids": regressed,
    }


def validate_fixed_set_regression() -> dict[str, Any]:
    return _validate_regression_summary(
        _json_file(ROOT / "evals" / "regression-summary.json"),
        _json_file(ROOT / "evals" / "blind-run-manifest.json"),
    )


def compile_and_check_imports() -> dict[str, Any]:
    python_files = sorted((ROOT / "scripts").glob("*.py")) + sorted((ROOT / "tests").glob("*.py"))
    for skill_root in SKILL_ROOTS.values():
        python_files.extend(sorted((skill_root / "scripts").glob("*.py")))
    external_imports: dict[str, list[str]] = {}
    with tempfile.TemporaryDirectory(prefix="ap-calculus-release-compile-") as temporary:
        target = Path(temporary)
        for index, path in enumerate(python_files):
            py_compile.compile(str(path), cfile=str(target / f"{index}.pyc"), doraise=True)
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path), feature_version=(3, 10))
            roots = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    roots.update(alias.name.split(".", 1)[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    roots.add(node.module.split(".", 1)[0])
            invalid = sorted(root for root in roots if root != "__future__" and root not in sys.stdlib_module_names)
            if invalid:
                external_imports[str(path.relative_to(ROOT))] = invalid
    if external_imports:
        raise ReleaseError(f"runtime/test code imports non-stdlib modules: {external_imports}")
    return {"compiled_file_count": len(python_files), "minimum_python_syntax": "3.10", "stdlib_only": True}


def _command_receipt(name: str, command: list[str], *, json_receipt: bool = False, extra_env: dict[str, str] | None = None) -> dict[str, Any]:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONUTF8"] = "1"
    if extra_env:
        environment.update(extra_env)
    process = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=environment,
    )
    stdout = process.stdout or ""
    stderr = process.stderr or ""
    combined = (stdout + "\n" + stderr).strip()
    receipt: dict[str, Any] = {
        "name": name,
        "status": "pass" if process.returncode == 0 else "fail",
        "exit_code": process.returncode,
        "command": command,
        "output_sha256": hashlib.sha256(combined.encode("utf-8")).hexdigest(),
    }
    if json_receipt:
        if not stdout.strip():
            receipt["status"] = "fail"
            receipt["error"] = "command emitted no JSON receipt"
        else:
            try:
                payload = json.loads(stdout)
                if not isinstance(payload, dict):
                    raise ReleaseError("command JSON receipt must be one object")
                receipt["reported_overall_status"] = payload.get("overall_status")
                if payload.get("overall_status") != "pass":
                    receipt["status"] = "fail"
                for field in (
                    "case_count",
                    "primary_passed",
                    "overall_case_pass_rate",
                    "category_scores",
                    "repeat_case_count",
                    "failed_case_ids",
                    "failed_invariants",
                    "critical_lane_failures",
                    "thresholds",
                    "self_check",
                ):
                    if field in payload:
                        receipt[field] = payload[field]
            except (json.JSONDecodeError, ReleaseError) as exc:
                receipt["status"] = "fail"
                receipt["error"] = str(exc) or "command did not emit one valid JSON object"
    if process.returncode != 0:
        receipt["output_tail"] = combined[-1000:]
    if name == "unittest":
        match = re.search(r"Ran (\d+) tests?", combined)
        skipped = re.search(r"skipped=(\d+)", combined)
        receipt["skipped_test_count"] = int(skipped.group(1)) if skipped else 0
        if match:
            receipt["test_count"] = int(match.group(1))
        if not match or int(match.group(1)) < 50:
            receipt["status"] = "fail"
            receipt["error"] = "unittest receipt must report at least 50 tests"
        elif receipt["skipped_test_count"]:
            receipt["status"] = "fail"
            receipt["error"] = "unittest receipt must not contain skipped tests"
    return receipt


def _quick_validate_path() -> Path | None:
    candidates = []
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        candidates.append(Path(codex_home) / "skills" / ".system" / "skill-creator" / "scripts" / "quick_validate.py")
    candidates.append(Path("D:/OpenAI/Codex/skills/.system/skill-creator/scripts/quick_validate.py"))
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--evidence-json", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    parser().parse_args(argv)
    checks: list[dict[str, Any]] = []
    citations_by_course: dict[str, list[str]] = {}
    precalculus_instructional: list[str] = []
    for name, function in (
        ("repository_artifacts", validate_repository_files),
        ("adaptive_artifacts", validate_adaptive_artifacts),
        ("blind_forward_provenance", validate_blind_run_provenance),
        ("fixed_set_regression", validate_fixed_set_regression),
        ("python_compile_and_stdlib", compile_and_check_imports),
    ):
        try:
            evidence = function()
            checks.append({"name": name, "status": "pass", "evidence": evidence})
            if name == "adaptive_artifacts":
                citations_by_course = evidence["topic_citations_by_course"]
                precalculus_instructional = evidence[
                    "precalculus_instructional_topic_citations"
                ]
        except (ReleaseError, OSError, UnicodeError, py_compile.PyCompileError, SyntaxError) as exc:
            checks.append({"name": name, "status": "fail", "error": str(exc)})

    python = sys.executable
    checks.append(
        _command_receipt(
            "validator_self_check",
            [python, str(CALC_SKILL_ROOT / "scripts" / "validate_topic_code.py"), "--self-check", "--evidence-json"],
            json_receipt=True,
        )
    )
    for label in ("psychology", "biology"):
        checks.append(
            _command_receipt(
                f"{label}_validator_self_check",
                [python, str(SKILL_ROOTS[label] / "scripts" / "validate_topic_code.py"), "--self-check", "--evidence-json"],
                json_receipt=True,
            )
        )
    for course in ("precalculus", "calc-ab", "calc-bc"):
        citations = citations_by_course.get(course, [])
        if course == "precalculus":
            citations = [citation for citation in citations if citation not in precalculus_instructional]
        name = f"diagnostic_topic_mappings_{course.replace('-', '_')}"
        if not citations:
            checks.append(
                {
                    "name": name,
                    "status": "fail",
                    "error": "adaptive artifact validation did not yield assessed citations",
                }
            )
            continue
        checks.append(
            _command_receipt(
                name,
                [
                    python,
                    str(CALC_SKILL_ROOT / "scripts" / "validate_topic_code.py"),
                    "--course",
                    course,
                    "--assessed-topic",
                    "--evidence-json",
                    *citations,
                ],
                json_receipt=True,
            )
        )
    if precalculus_instructional:
        checks.append(
            _command_receipt(
                "diagnostic_topic_mappings_precalculus_instructional",
                [
                    python,
                    str(CALC_SKILL_ROOT / "scripts" / "validate_topic_code.py"),
                    "--course",
                    "precalculus",
                    "--evidence-json",
                    *precalculus_instructional,
                ],
                json_receipt=True,
            )
        )
    else:
        checks.append(
            {
                "name": "diagnostic_topic_mappings_precalculus_instructional",
                "status": "fail",
                "error": "adaptive artifact validation did not yield Unit 4 instructional citations",
            }
        )
    checks.append(
        _command_receipt(
            "eval_scorer_self_check",
            [python, str(ROOT / "scripts" / "run_evals.py"), "--self-check", "--evidence-json"],
            json_receipt=True,
        )
    )
    checks.append(
        _command_receipt(
            "behavior_release_thresholds",
            [python, str(ROOT / "scripts" / "run_evals.py"), "--evidence-json"],
            json_receipt=True,
        )
    )
    unit = _command_receipt(
        "unittest",
        [python, "-m", "unittest", "discover", "-s", "tests", "-v"],
    )
    checks.append(unit)
    quick = _quick_validate_path()
    if quick is None:
        checks.append({"name": "skill_creator_quick_validate", "status": "fail", "error": "installed quick_validate.py was not found"})
    else:
        for label, skill_root in SKILL_ROOTS.items():
            checks.append(
                _command_receipt(
                    f"skill_creator_quick_validate_{label}",
                    [python, str(quick), str(skill_root)],
                    extra_env={"PYTHONUTF8": "1"},
                )
            )
    overall = "pass" if checks and all(check["status"] == "pass" for check in checks) else "fail"
    payload = {
        "schema_version": 1,
        "release_gate": "ap-advisor-adaptive-v2",
        "overall_status": overall,
        "check_count": len(checks),
        "checks": checks,
    }
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return 0 if overall == "pass" else 1


def _configure_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="strict")


if __name__ == "__main__":
    _configure_utf8()
    raise SystemExit(main())
