#!/usr/bin/env python3
"""Validate or run AP Advisor behavior cases.

Default mode validates the corpus only. ``--responses`` evaluates saved final
outputs without a model call. ``--run`` is the only mode that invokes Codex and
may consume account usage. Topic validation always runs here, directly against
the final output; model command events are deliberately ignored.

Exit codes: 0 valid/no behavior failure, 1 behavior failure, 2 setup error.
"""

from __future__ import annotations

import argparse
import datetime as dt
import functools
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CORPUS = REPO_ROOT / "evals" / "cases.jsonl"
OUTPUT_SCHEMA = REPO_ROOT / "references" / "output-schema.json"
ERROR_SCHEMA = REPO_ROOT / "references" / "machine-error-schema.json"
VALIDATOR_PATH = REPO_ROOT / "scripts" / "validate_topic_code.py"
VALID_CATEGORIES = {"advisor", "machine-output", "negative-routing", "review", "scope"}
VALID_INVOCATIONS = {"explicit", "implicit"}
VALID_OUTPUT_KINDS = {"any", "text", "json_error", "json_success"}
VALID_COURSES = {"precalculus", "calc-ab", "calc-bc"}
VALID_STYLES = {"instructional", "assessed-topic", "exam-oriented"}
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
TOPIC_START = re.compile(
    r"(?<![A-Za-z0-9])Unit\s+\d+,\s+Topic\s+\d+\.\d+\s+—\s+",
    re.IGNORECASE,
)

CONTRACT_PASS = "CONTRACT-PASS"
MANUAL_REVIEW_REQUIRED = "MANUAL REVIEW REQUIRED"
PASS = "PASS"
NOT_RUN = "NOT RUN"
FAIL = "FAIL"


class RunnerError(RuntimeError):
    pass


class DuplicateJsonKeyError(ValueError):
    pass


def _strict_json_loads(source: str) -> Any:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise DuplicateJsonKeyError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    return json.loads(source, object_pairs_hook=reject_duplicates)


@dataclass(frozen=True)
class ManualCheck:
    id: str
    description: str


@dataclass(frozen=True)
class EvalCase:
    id: str
    category: str
    invocation: str
    prompt: str
    expect: dict[str, Any]
    manual_checks: tuple[ManualCheck, ...]


@dataclass(frozen=True)
class Adjudication:
    case_id: str
    reviewer: str
    reviewed_at: str
    checks: dict[str, dict[str, str]]


def _load_validator() -> Any:
    spec = importlib.util.spec_from_file_location("ap_advisor_validator", VALIDATOR_PATH)
    if spec is None or spec.loader is None:
        raise RunnerError(f"cannot import validator at {VALIDATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except (OSError, ImportError, SyntaxError) as exc:
        raise RunnerError(f"cannot import validator: {exc}") from exc
    return module


VALIDATOR = _load_validator()


def _string_list(value: Any, field: str, case_id: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise RunnerError(f"case {case_id!r}: {field} must be a string array")
    return value


def _canonical_style(style: Any) -> str | None:
    if style == "ap-oriented":
        return "assessed-topic"
    return style if isinstance(style, str) and style in VALID_STYLES else None


def _canonical_expect(raw: dict[str, Any], case_id: str) -> dict[str, Any]:
    """Accept the old eval field names only at this input boundary."""

    expect = dict(raw)
    if "topic_validation" not in expect and "validator_call" in expect:
        expect["topic_validation"] = expect.pop("validator_call")
    if "validation_course" not in expect and "validator_course" in expect:
        expect["validation_course"] = expect.pop("validator_course")
    if "validation_style" not in expect and "validator_ap_oriented" in expect:
        expect["validation_style"] = (
            "assessed-topic" if expect.pop("validator_ap_oriented") else "instructional"
        )

    required = {"output_kind", "topic_validation", "must_contain", "must_not_contain"}
    optional = {
        "validation_course",
        "validation_style",
        "json_contract",
        "forbidden_content_fields",
    }
    missing = required - expect.keys()
    extra = expect.keys() - required - optional
    if missing or extra:
        raise RunnerError(
            f"case {case_id!r}: invalid expect fields; "
            f"missing={sorted(missing)}, unknown={sorted(extra)}"
        )
    if expect["output_kind"] not in VALID_OUTPUT_KINDS:
        raise RunnerError(f"case {case_id!r}: invalid output_kind")
    if expect["topic_validation"] not in {True, False, None}:
        raise RunnerError(f"case {case_id!r}: topic_validation must be true, false, or null")
    _string_list(expect["must_contain"], "must_contain", case_id)
    _string_list(expect["must_not_contain"], "must_not_contain", case_id)
    forbidden = expect.get("forbidden_content_fields", [])
    _string_list(forbidden, "forbidden_content_fields", case_id)

    if expect["output_kind"] == "text" and expect["topic_validation"] is True:
        if expect.get("validation_course") not in VALID_COURSES:
            raise RunnerError(f"case {case_id!r}: validation_course is required")
        style = _canonical_style(expect.get("validation_style"))
        if style is None:
            raise RunnerError(f"case {case_id!r}: validation_style is required")
        expect["validation_style"] = style
    if expect["output_kind"] == "json_success":
        contract = expect.get("json_contract")
        if not isinstance(contract, dict):
            raise RunnerError(f"case {case_id!r}: json_contract is required")
        for field in (
            "course",
            "unit",
            "topic",
            "topic_exam_scope",
            "type",
            "difficulty",
            "style",
            "supporting_topics",
        ):
            if field not in contract:
                raise RunnerError(
                    f"case {case_id!r}: json_contract.{field} is required"
                )
        style = _canonical_style(contract["style"])
        if style is None:
            raise RunnerError(f"case {case_id!r}: invalid json_contract.style")
        contract = dict(contract)
        contract["style"] = style
        expect["json_contract"] = contract
    return expect


def validate_case(raw: Any, line_number: int) -> EvalCase:
    if not isinstance(raw, dict):
        raise RunnerError(f"line {line_number}: case must be an object")
    required = {"id", "category", "invocation", "prompt", "expect", "manual_checks"}
    if set(raw) != required:
        raise RunnerError(f"line {line_number}: case fields must be {sorted(required)}")
    case_id = raw["id"]
    if not isinstance(case_id, str) or ID_PATTERN.fullmatch(case_id) is None:
        raise RunnerError(f"line {line_number}: invalid case id")
    if raw["category"] not in VALID_CATEGORIES:
        raise RunnerError(f"case {case_id!r}: invalid category")
    if raw["invocation"] not in VALID_INVOCATIONS:
        raise RunnerError(f"case {case_id!r}: invalid invocation")
    if not isinstance(raw["prompt"], str) or not raw["prompt"].strip():
        raise RunnerError(f"case {case_id!r}: prompt must be non-empty")
    if not isinstance(raw["expect"], dict):
        raise RunnerError(f"case {case_id!r}: expect must be an object")

    raw_checks = raw["manual_checks"]
    if not isinstance(raw_checks, list) or not raw_checks:
        raise RunnerError(f"case {case_id!r}: manual_checks must be a non-empty array")
    checks: list[ManualCheck] = []
    for index, item in enumerate(raw_checks, start=1):
        if isinstance(item, str) and item.strip():
            checks.append(ManualCheck(f"manual-{index}", item))
        elif (
            isinstance(item, dict)
            and set(item) == {"id", "description"}
            and isinstance(item["id"], str)
            and ID_PATTERN.fullmatch(item["id"])
            and isinstance(item["description"], str)
            and item["description"].strip()
        ):
            checks.append(ManualCheck(item["id"], item["description"]))
        else:
            raise RunnerError(f"case {case_id!r}: invalid manual check {index}")
    if len({check.id for check in checks}) != len(checks):
        raise RunnerError(f"case {case_id!r}: duplicate manual check id")
    return EvalCase(
        case_id,
        raw["category"],
        raw["invocation"],
        raw["prompt"],
        _canonical_expect(raw["expect"], case_id),
        tuple(checks),
    )


def load_cases(path: Path = DEFAULT_CORPUS) -> list[EvalCase]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise RunnerError(f"cannot read corpus {path}: {exc}") from exc
    cases: list[EvalCase] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            raw = _strict_json_loads(line)
        except (json.JSONDecodeError, DuplicateJsonKeyError) as exc:
            raise RunnerError(f"line {line_number}: invalid JSON: {exc}") from exc
        cases.append(validate_case(raw, line_number))
    if not cases:
        raise RunnerError("corpus contains no cases")
    ids = [case.id for case in cases]
    if len(ids) != len(set(ids)):
        raise RunnerError("corpus contains duplicate case ids")
    return cases


def select_cases(cases: Iterable[EvalCase], requested: list[str]) -> list[EvalCase]:
    selected = list(cases)
    if not requested:
        return selected
    by_id = {case.id: case for case in selected}
    missing = sorted(set(requested) - by_id.keys())
    if missing:
        raise RunnerError("unknown case id(s): " + ", ".join(missing))
    return [by_id[case_id] for case_id in requested]


def _load_jsonl_objects(path: Path, label: str) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise RunnerError(f"cannot read {label} {path}: {exc}") from exc
    values: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = _strict_json_loads(line)
        except (json.JSONDecodeError, DuplicateJsonKeyError) as exc:
            raise RunnerError(f"{label} line {line_number}: invalid JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise RunnerError(f"{label} line {line_number}: object required")
        values.append(value)
    return values


def load_responses(path: Path) -> dict[str, str]:
    responses: dict[str, str] = {}
    for value in _load_jsonl_objects(path, "responses"):
        if set(value) != {"case_id", "final_output"}:
            raise RunnerError("response must contain exactly case_id and final_output")
        case_id, output = value["case_id"], value["final_output"]
        if not isinstance(case_id, str) or not isinstance(output, str):
            raise RunnerError("response case_id and final_output must be strings")
        if case_id in responses:
            raise RunnerError(f"duplicate response for {case_id!r}")
        responses[case_id] = output
    return responses


def load_adjudications(path: Path) -> dict[str, Adjudication]:
    adjudications: dict[str, Adjudication] = {}
    for value in _load_jsonl_objects(path, "adjudications"):
        if set(value) != {"case_id", "reviewer", "reviewed_at", "checks"}:
            raise RunnerError(
                "adjudication must contain exactly case_id, reviewer, reviewed_at, checks"
            )
        case_id, reviewer, reviewed_at = (
            value["case_id"],
            value["reviewer"],
            value["reviewed_at"],
        )
        if not all(isinstance(item, str) and item.strip() for item in (case_id, reviewer, reviewed_at)):
            raise RunnerError("adjudication identity fields must be non-empty strings")
        try:
            timestamp = dt.datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise RunnerError(f"adjudication {case_id!r}: invalid reviewed_at") from exc
        if timestamp.tzinfo is None:
            raise RunnerError(f"adjudication {case_id!r}: reviewed_at needs a timezone")
        if not isinstance(value["checks"], list):
            raise RunnerError(f"adjudication {case_id!r}: checks must be an array")
        checks: dict[str, dict[str, str]] = {}
        for item in value["checks"]:
            if not isinstance(item, dict) or set(item) != {"id", "status", "evidence"}:
                raise RunnerError(
                    f"adjudication {case_id!r}: each check needs id, status, evidence"
                )
            if (
                not isinstance(item["id"], str)
                or item["status"] not in {"pass", "fail"}
                or not isinstance(item["evidence"], str)
                or not item["evidence"].strip()
            ):
                raise RunnerError(f"adjudication {case_id!r}: invalid check")
            if item["id"] in checks:
                raise RunnerError(
                    f"adjudication {case_id!r}: duplicate check {item['id']!r}"
                )
            checks[item["id"]] = item
        if case_id in adjudications:
            raise RunnerError(f"duplicate adjudication for {case_id!r}")
        adjudications[case_id] = Adjudication(
            case_id, reviewer, reviewed_at, checks
        )
    return adjudications


@functools.lru_cache(maxsize=2)
def _load_schema(path: Path) -> dict[str, Any]:
    try:
        value = _strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, DuplicateJsonKeyError) as exc:
        raise RunnerError(f"cannot load JSON schema {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RunnerError(f"schema {path} must be an object")
    return value


def _schema_failures(value: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    # ponytail: validates only this repository's schema subset; extend here if
    # a future schema adds keywords, because runtime must stay dependency-free.
    failures: list[str] = []
    expected_type = schema.get("type")
    checks = {
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str),
    }
    if expected_type in checks and not checks[expected_type](value):
        return [f"{path} must be {expected_type}"]
    if "const" in schema and value != schema["const"]:
        failures.append(f"{path} must equal {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        failures.append(f"{path} must be one of {schema['enum']!r}")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            failures.append(f"{path} is too short")
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            failures.append(f"{path} does not match {schema['pattern']!r}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            failures.append(f"{path} has too few items")
        if schema.get("uniqueItems") and len({json.dumps(v, sort_keys=True) for v in value}) != len(value):
            failures.append(f"{path} items must be unique")
        if isinstance(schema.get("items"), dict):
            for index, item in enumerate(value):
                failures.extend(_schema_failures(item, schema["items"], f"{path}[{index}]"))
    if isinstance(value, dict):
        for name in schema.get("required", []):
            if name not in value:
                failures.append(f"{path}.{name} is required")
        properties = schema.get("properties", {})
        for name, child_schema in properties.items():
            if name in value:
                failures.extend(_schema_failures(value[name], child_schema, f"{path}.{name}"))
        if schema.get("additionalProperties") is False:
            for name in sorted(value.keys() - properties.keys()):
                failures.append(f"{path}.{name} is not allowed")
    for branch in schema.get("allOf", []):
        condition, consequence = branch.get("if"), branch.get("then")
        if isinstance(condition, dict) and isinstance(consequence, dict):
            if not _schema_failures(value, condition, path):
                failures.extend(_schema_failures(value, consequence, path))
        else:
            failures.extend(_schema_failures(value, branch, path))
    return failures


def _decode_json_output(message: str) -> Any:
    return _strict_json_loads(message.strip())


def _output_citation(unit: Any, topic: Any) -> str | None:
    if not isinstance(unit, str) or not isinstance(topic, str):
        return None
    parts = topic.split(" ", 1)
    if re.fullmatch(r"Unit \d+", unit) is None or len(parts) != 2:
        return None
    if re.fullmatch(r"\d+\.\d+", parts[0]) is None:
        return None
    return f"{unit}, Topic {parts[0]} — {parts[1]}"


def _json_mappings(value: dict[str, Any]) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    primary = _output_citation(value.get("unit"), value.get("topic"))
    scope = value.get("topic_exam_scope")
    if primary and isinstance(scope, str):
        rows.append((primary, scope))
    for item in value.get("supporting_topics", []):
        if isinstance(item, dict):
            citation = _output_citation(item.get("unit"), item.get("topic"))
            item_scope = item.get("topic_exam_scope")
            if citation and isinstance(item_scope, str):
                rows.append((citation, item_scope))
    return rows


@functools.lru_cache(maxsize=3)
def _course_citations(course: str) -> tuple[str, ...]:
    topics = VALIDATOR.filter_by_course(VALIDATOR.parse_framework(), course)
    return tuple(sorted((topic.citation for topic in topics), key=len, reverse=True))


def _text_mappings(message: str, course: str) -> tuple[list[str], list[str]]:
    normalized = unicodedata.normalize("NFKC", message)
    citations: list[str] = []
    recognized_starts: set[int] = set()
    for citation in _course_citations(course):
        pattern = re.compile(
            rf"(?<![A-Za-z0-9]){re.escape(citation)}(?=[ \t]*(?:\r?\n|$))"
        )
        for match in pattern.finditer(normalized):
            citations.append(citation)
            recognized_starts.add(match.start())
    extra_starts = [
        match.start()
        for match in TOPIC_START.finditer(normalized)
        if match.start() not in recognized_starts
    ]
    failures = []
    if extra_starts:
        failures.append("final text contains an extra or non-exact Topic citation")
    repeated = [name for name, count in Counter(citations).items() if count > 1]
    if repeated:
        failures.append("final text repeats Topic citation(s): " + ", ".join(repeated))
    return citations, failures


def _validate_topics(
    case: EvalCase, message: str, value: dict[str, Any] | None
) -> tuple[list[str], dict[str, Any] | None]:
    required = case.expect["topic_validation"]
    failures: list[str] = []
    if value is not None:
        rows = _json_mappings(value)
        citations = [row[0] for row in rows]
        course = value.get("course")
        style = _canonical_style(value.get("style"))
    else:
        course = case.expect.get("validation_course")
        style = case.expect.get("validation_style")
        citations, text_failures = (
            _text_mappings(message, course) if isinstance(course, str) else ([], [])
        )
        rows = []
        failures.extend(text_failures)

    if required is False:
        normalized = unicodedata.normalize("NFKC", message)
        if TOPIC_START.search(normalized):
            failures.append("Topic mappings are forbidden for this case")
        return failures, None
    if required is None:
        return failures, None
    if course not in VALID_COURSES or style is None:
        failures.append("cannot determine validation course/style from final output")
        return failures, None
    if not citations:
        failures.append("final output contains no complete Topic mapping")
        return failures, None

    assessed_topic = style in {"assessed-topic", "exam-oriented"}
    code, evidence = VALIDATOR.validate_citations(
        citations, course=course, assessed_topic=assessed_topic
    )
    if code == 2:
        raise RunnerError(f"validator setup failure: {evidence.get('error')}")
    if code == 1:
        failures.extend(
            row.get("message", "Topic validation failed")
            for row in evidence["results"]
            if row.get("status") == "fail"
        )

    if value is not None:
        evidence_rows = [
            (row["citation"], row["topic_exam_scope"])
            for row in evidence["results"]
            if row.get("status") == "pass"
        ]
        if Counter(evidence_rows) != Counter(rows):
            failures.append("final output Topic scopes do not match validator results")
        topic_validation = value.get("citation_validation")
        if not isinstance(topic_validation, dict) or topic_validation.get("automated_status") != "pass":
            failures.append("citation_validation must report automated_status pass")
        primary_topic = value.get("topic", "").split(" ", 1)[0]
        supporting = [
            item.get("topic", "").split(" ", 1)[0]
            for item in value.get("supporting_topics", [])
            if isinstance(item, dict)
        ]
        try:
            failures.extend(
                VALIDATOR.validate_content_boundary(
                    course=course,
                    content_topic=primary_topic,
                    supporting_topics=supporting,
                    methods=value.get("methods", []),
                    mathematical_practices=value.get("mathematical_practices", []),
                    assessed_topic=assessed_topic,
                )
            )
        except VALIDATOR.BoundaryDataError as exc:
            raise RunnerError(f"content-boundary setup failure: {exc}") from exc
    return failures, evidence


def _json_contract_failures(value: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for field, expected_value in expected.items():
        actual = _canonical_style(value.get(field)) if field == "style" else value.get(field)
        if actual != expected_value:
            failures.append(
                f"JSON field {field!r} expected {expected_value!r}, observed {actual!r}"
            )
    return failures


def evaluate_case(
    case: EvalCase, message: str
) -> tuple[list[str], dict[str, Any] | None]:
    """Validate the final output, then invoke Topic/content validation directly."""

    failures: list[str] = []
    if not message.strip():
        return ["final output is empty"], None
    kind = case.expect["output_kind"]
    value: dict[str, Any] | None = None
    try:
        decoded = _decode_json_output(message)
    except (json.JSONDecodeError, DuplicateJsonKeyError, TypeError) as exc:
        if kind in {"json_error", "json_success"}:
            failures.append(f"final output is not exactly one JSON value: {exc}")
    else:
        if kind == "text":
            failures.append("expected text but final output is JSON")
        elif not isinstance(decoded, dict):
            failures.append("final JSON value must be an object")
        else:
            value = decoded
            schema = ERROR_SCHEMA if kind == "json_error" else OUTPUT_SCHEMA
            if kind in {"json_error", "json_success"}:
                failures.extend(_schema_failures(value, _load_schema(schema)))
            if kind == "json_success":
                failures.extend(
                    _json_contract_failures(value, case.expect["json_contract"])
                )

    normalized = message.casefold()
    for text in case.expect["must_contain"]:
        if text.casefold() not in normalized:
            failures.append(f"missing required text: {text!r}")
    for text in case.expect["must_not_contain"]:
        if text.casefold() in normalized:
            failures.append(f"contains forbidden text: {text!r}")
    if value is not None and kind == "json_success":
        content = value.get("content", {})
        for field in case.expect.get("forbidden_content_fields", []):
            if isinstance(content, dict) and field in content:
                failures.append(f"content field {field!r} is forbidden")

    topic_failures, evidence = _validate_topics(case, message, value)
    failures.extend(topic_failures)
    return failures, evidence


def adjudicate(
    case: EvalCase,
    automated_passed: bool,
    adjudication: Adjudication | None,
) -> tuple[str, list[dict[str, str]]]:
    records: list[dict[str, str]] = []
    failed = False
    pending = False
    allowed_ids = {check.id for check in case.manual_checks}
    if adjudication is not None:
        unknown = adjudication.checks.keys() - allowed_ids
        if unknown:
            raise RunnerError(
                f"adjudication {case.id!r} has unknown check(s): {sorted(unknown)}"
            )
    for check in case.manual_checks:
        outcome = adjudication.checks.get(check.id) if adjudication else None
        if outcome is None:
            pending = True
            records.append(
                {"id": check.id, "description": check.description, "status": "pending"}
            )
        else:
            failed = failed or outcome["status"] == "fail"
            records.append(
                {
                    "id": check.id,
                    "description": check.description,
                    "status": outcome["status"],
                    "evidence": outcome["evidence"],
                    "reviewer": adjudication.reviewer,
                    "reviewed_at": adjudication.reviewed_at,
                }
            )
    if not automated_passed or failed:
        return FAIL, records
    if pending:
        return MANUAL_REVIEW_REQUIRED, records
    return PASS, records


def evaluate_responses(
    cases: Iterable[EvalCase],
    responses: dict[str, str],
    adjudications: dict[str, Adjudication] | None = None,
) -> list[dict[str, Any]]:
    adjudications = adjudications or {}
    selected = list(cases)
    expected_ids = {case.id for case in selected}
    unknown = (responses.keys() | adjudications.keys()) - expected_ids
    if unknown:
        raise RunnerError("response/adjudication has unknown case(s): " + ", ".join(sorted(unknown)))
    missing = expected_ids - responses.keys()
    if missing:
        raise RunnerError("missing response(s): " + ", ".join(sorted(missing)))

    results: list[dict[str, Any]] = []
    for case in selected:
        failures, validator_evidence = evaluate_case(case, responses[case.id])
        automated_passed = not failures
        overall_status, manual = adjudicate(
            case, automated_passed, adjudications.get(case.id)
        )
        results.append(
            {
                "id": case.id,
                "contract_status": CONTRACT_PASS if automated_passed else FAIL,
                "overall_status": overall_status,
                "failures": failures,
                "validator_evidence": validator_evidence,
                "final_output": responses[case.id],
                "manual_checks": manual,
            }
        )
    return results


def parse_json_events(stdout: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(stdout.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = _strict_json_loads(line)
        except (json.JSONDecodeError, DuplicateJsonKeyError) as exc:
            raise RunnerError(f"Codex JSONL line {line_number} is invalid: {exc}") from exc
        if not isinstance(value, dict):
            raise RunnerError(f"Codex JSONL line {line_number} is not an object")
        events.append(value)
    return events


def extract_final_message(events: Iterable[dict[str, Any]]) -> str:
    messages: list[str] = []
    for event in events:
        item = event.get("item")
        if (
            event.get("type") == "item.completed"
            and isinstance(item, dict)
            and item.get("type") == "agent_message"
            and isinstance(item.get("text"), str)
        ):
            messages.append(item["text"])
        response = event.get("response")
        if isinstance(response, dict) and isinstance(response.get("output_text"), str):
            messages.append(response["output_text"])
    if not messages:
        raise RunnerError("Codex event stream contains no final agent message")
    return messages[-1]


def _copy_skill(temp_repo: Path) -> None:
    target = temp_repo / ".agents" / "skills" / "ap-advisor"
    target.mkdir(parents=True)
    shutil.copy2(REPO_ROOT / "SKILL.md", target / "SKILL.md")
    shutil.copytree(REPO_ROOT / "references", target / "references")
    (target / "scripts").mkdir()
    shutil.copy2(VALIDATOR_PATH, target / "scripts" / VALIDATOR_PATH.name)


def _resolve_executable(command: str) -> str:
    resolved = shutil.which(command)
    if resolved:
        return resolved
    candidate = Path(command)
    if candidate.is_file():
        return str(candidate.resolve())
    raise RunnerError(f"Codex executable not found: {command!r}")


def run_codex_case(
    case: EvalCase, codex_executable: str, timeout_seconds: int, use_user_config: bool
) -> tuple[str, str]:
    prompt = f"$ap-advisor\n\n{case.prompt}" if case.invocation == "explicit" else case.prompt
    with tempfile.TemporaryDirectory(prefix="ap-advisor-eval-") as temp_dir:
        temp_repo = Path(temp_dir)
        _copy_skill(temp_repo)
        git = subprocess.run(
            ["git", "init", "--quiet"],
            cwd=temp_repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        if git.returncode:
            raise RunnerError(f"git init failed: {git.stderr or git.stdout}")
        command = [codex_executable, "exec", "--ephemeral", "--json", "--sandbox", "read-only"]
        if not use_user_config:
            command.append("--ignore-user-config")
        command.append(prompt)
        try:
            completed = subprocess.run(
                command,
                cwd=temp_repo,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RunnerError(f"case {case.id!r}: Codex execution failed: {exc}") from exc
    if completed.returncode:
        raise RunnerError(
            f"case {case.id!r}: Codex exited {completed.returncode}: "
            f"{completed.stderr.strip() or completed.stdout.strip()}"
        )
    return extract_final_message(parse_json_events(completed.stdout)), completed.stderr


def _aggregate_status(results: Iterable[dict[str, Any]]) -> tuple[str, str]:
    values = list(results)
    contract = FAIL if any(item["contract_status"] == FAIL for item in values) else CONTRACT_PASS
    if any(item["overall_status"] == FAIL for item in values):
        overall = FAIL
    elif any(item["overall_status"] == MANUAL_REVIEW_REQUIRED for item in values):
        overall = MANUAL_REVIEW_REQUIRED
    else:
        overall = PASS
    return contract, overall


def write_results(output_dir: Path, payload: dict[str, Any]) -> Path:
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = output_dir / f"behavior-eval-{timestamp}.json"
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        raise RunnerError(f"cannot write results {path}: {exc}") from exc
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--case", dest="case_ids", action="append", default=[])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--responses", type=Path, help="evaluate saved final-output JSONL")
    mode.add_argument("--run", action="store_true", help="run Codex; may consume usage")
    parser.add_argument("--adjudications", type=Path)
    parser.add_argument("--codex-command", default="codex")
    parser.add_argument("--use-user-config", action="store_true")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "eval-results")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cases = select_cases(load_cases(args.corpus), args.case_ids)
        _load_schema(OUTPUT_SCHEMA)
        _load_schema(ERROR_SCHEMA)
        VALIDATOR.load_boundaries()
        if args.adjudications and not (args.responses or args.run):
            raise RunnerError("--adjudications requires --responses or --run")
        if not args.responses and not args.run:
            print(
                f"VALID: {len(cases)} case(s); CORPUS CONTRACT ONLY; "
                f"LIVE MODEL EVAL: {NOT_RUN}"
            )
            return 0

        adjudications = load_adjudications(args.adjudications) if args.adjudications else {}
        stderr_by_case: dict[str, str] = {}
        if args.responses:
            responses = load_responses(args.responses)
        else:
            if args.timeout <= 0:
                raise RunnerError("--timeout must be positive")
            executable = _resolve_executable(args.codex_command)
            responses = {}
            for case in cases:
                print(f"RUN: {case.id}", flush=True)
                output, stderr = run_codex_case(
                    case, executable, args.timeout, args.use_user_config
                )
                responses[case.id] = output
                stderr_by_case[case.id] = stderr

        results = evaluate_responses(cases, responses, adjudications)
        for result in results:
            if result["id"] in stderr_by_case:
                result["stderr"] = stderr_by_case[result["id"]]
            print(
                f"{result['contract_status']}: {result['id']}; "
                f"OVERALL: {result['overall_status']}"
            )
        contract_status, overall_status = _aggregate_status(results)
        payload = {
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "corpus": str(args.corpus.resolve()),
            "contract_status": contract_status,
            "overall_status": overall_status,
            "results": results,
        }
        path = write_results(args.output_dir, payload)
        print(f"OVERALL: {overall_status}")
        print(f"RESULTS: {path}")
        return 1 if overall_status == FAIL else 0
    except (RunnerError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
