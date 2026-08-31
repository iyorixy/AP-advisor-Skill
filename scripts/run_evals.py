#!/usr/bin/env python3
"""Validate and score AP Calculus Advisor behavioral review records."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CASES = SKILL_ROOT / "evals" / "cases.jsonl"
DEFAULT_CASE_SCHEMA = SKILL_ROOT / "evals" / "case-schema.json"
DEFAULT_REVIEW_SCHEMA = SKILL_ROOT / "evals" / "review-schema.json"
DEFAULT_REVIEWS = SKILL_ROOT / "evals" / "release-reviews.jsonl"

CATEGORIES = {"Review": 12, "Advisor": 8, "Coach": 8, "Generate": 8, "Boundary": 4}
PRACTICES = {
    "calc-1-implementing-processes",
    "calc-2-connecting-representations",
    "calc-3-justification",
    "calc-4-communication-notation",
}
REPRESENTATIONS = {"analytical", "graphical", "numerical", "tabular", "verbal"}
CRITICAL_LANES = {
    "math_correctness",
    "first_substantive_error",
    "answer_visibility",
    "topic_practice_boundary",
    "unauthorized_persistence",
    "unsupported_mastery",
}
CASE_ID_RE = re.compile(r"^(REV|ADV|COA|GEN|BND)-[0-9]{3}$")
INVARIANT_ID_RE = re.compile(r"^[A-Z0-9-]+$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

CASE_FIELDS = {
    "case_id",
    "category",
    "language",
    "unit",
    "representations",
    "user_request",
    "supplied_evidence",
    "expected_primary_topic",
    "expected_primary_practice",
    "expected_first_substantive_error",
    "allowed_diagnoses",
    "forbidden_inferences",
    "required_behaviors",
    "forbidden_behaviors",
    "expected_minimum_next_step",
    "severity",
    "critical_lanes",
    "semantic_rubric_invariants",
}
REVIEW_FIELDS = {
    "schema_version",
    "case_id",
    "round_id",
    "forward_context_id",
    "forward_context_independent",
    "rubric_hidden_from_forward_tester",
    "reviewer_context_id",
    "reviewer_independent",
    "raw_output_sha256",
    "reviewed_at",
    "invariants",
}


class EvalError(ValueError):
    pass


def _iso_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise EvalError(f"{field} must be an ISO 8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvalError(f"{field} must be an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise EvalError(f"{field} must include a timezone")
    return parsed


def _strict_object(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or value.keys() != fields:
        raise EvalError(f"{label} has missing or unexpected fields")
    return value


def _strings(value: Any, label: str, *, minimum: int = 1) -> list[str]:
    if (
        not isinstance(value, list)
        or len(value) < minimum
        or any(not isinstance(item, str) or len(item) < 5 for item in value)
        or len(value) != len(set(value))
    ):
        raise EvalError(f"{label} must be a nonempty unique string array")
    return value


def validate_case(value: Any, line_number: int) -> dict[str, Any]:
    case = _strict_object(value, CASE_FIELDS, f"case line {line_number}")
    case_id = case["case_id"]
    if not isinstance(case_id, str) or not CASE_ID_RE.fullmatch(case_id):
        raise EvalError(f"case line {line_number} has invalid case_id")
    if case["category"] not in CATEGORIES:
        raise EvalError(f"{case_id} has invalid category")
    expected_prefix = {"Review": "REV", "Advisor": "ADV", "Coach": "COA", "Generate": "GEN", "Boundary": "BND"}[case["category"]]
    if not case_id.startswith(expected_prefix + "-"):
        raise EvalError(f"{case_id} category does not match its prefix")
    if case["language"] not in {"en", "zh-CN"}:
        raise EvalError(f"{case_id} has invalid language")
    unit = case["unit"]
    if unit is not None and (not isinstance(unit, int) or isinstance(unit, bool) or not 1 <= unit <= 8):
        raise EvalError(f"{case_id} has invalid Unit")
    representations = case["representations"]
    if (
        not isinstance(representations, list)
        or not representations
        or len(representations) != len(set(representations))
        or not set(representations) <= REPRESENTATIONS
    ):
        raise EvalError(f"{case_id} has invalid representations")
    if not isinstance(case["user_request"], str) or len(case["user_request"]) < 12:
        raise EvalError(f"{case_id} has an incomplete request")
    evidence = _strict_object(case["supplied_evidence"], {"kind", "content"}, f"{case_id} evidence")
    if evidence["kind"] not in {
        "student_work",
        "performance_summary",
        "conversation_state",
        "generation_constraints",
        "external_material",
    } or not isinstance(evidence["content"], str) or len(evidence["content"]) < 3:
        raise EvalError(f"{case_id} has invalid supplied evidence")

    topic = _strict_object(
        case["expected_primary_topic"], {"status", "code", "citation", "rationale"}, f"{case_id} topic"
    )
    if topic["status"] not in {"established", "not_established"} or not isinstance(topic["rationale"], str) or len(topic["rationale"]) < 8:
        raise EvalError(f"{case_id} has invalid Topic expectation")
    if topic["status"] == "established":
        if (
            not isinstance(topic["code"], str)
            or not re.fullmatch(r"[1-8]\.[0-9]+", topic["code"])
            or not isinstance(topic["citation"], str)
            or len(topic["citation"]) < 5
        ):
            raise EvalError(f"{case_id} has incomplete established Topic")
    elif topic["code"] is not None or topic["citation"] is not None:
        raise EvalError(f"{case_id} must keep an unestablished Topic null")

    practice = _strict_object(
        case["expected_primary_practice"], {"status", "id", "label", "rationale"}, f"{case_id} practice"
    )
    if practice["status"] not in {"established", "not_established"} or not isinstance(practice["rationale"], str) or len(practice["rationale"]) < 8:
        raise EvalError(f"{case_id} has invalid Practice expectation")
    if practice["status"] == "established":
        if practice["id"] not in PRACTICES or not isinstance(practice["label"], str) or len(practice["label"]) < 5:
            raise EvalError(f"{case_id} has incomplete established Practice")
    elif practice["id"] is not None or practice["label"] is not None:
        raise EvalError(f"{case_id} must keep an unestablished Practice null")

    error = _strict_object(
        case["expected_first_substantive_error"], {"status", "statement", "rationale"}, f"{case_id} first error"
    )
    if error["status"] not in {"identified", "none", "not_established"}:
        raise EvalError(f"{case_id} has invalid first-error status")
    if not isinstance(error["statement"], str) or len(error["statement"]) < 3 or not isinstance(error["rationale"], str) or len(error["rationale"]) < 8:
        raise EvalError(f"{case_id} has incomplete first-error expectation")
    for field in (
        "allowed_diagnoses",
        "forbidden_inferences",
        "required_behaviors",
        "forbidden_behaviors",
    ):
        _strings(case[field], f"{case_id} {field}")
    if not isinstance(case["expected_minimum_next_step"], str) or len(case["expected_minimum_next_step"]) < 8:
        raise EvalError(f"{case_id} has an incomplete next step")
    if case["severity"] not in {"critical", "noncritical"}:
        raise EvalError(f"{case_id} has invalid severity")
    lanes = case["critical_lanes"]
    if not isinstance(lanes, list) or len(lanes) != len(set(lanes)) or not set(lanes) <= CRITICAL_LANES:
        raise EvalError(f"{case_id} has invalid critical lanes")
    if (case["severity"] == "critical") != bool(lanes):
        raise EvalError(f"{case_id} severity and critical lanes disagree")
    invariants = case["semantic_rubric_invariants"]
    if not isinstance(invariants, list) or len(invariants) < 2:
        raise EvalError(f"{case_id} needs at least two semantic invariants")
    invariant_ids: set[str] = set()
    for invariant in invariants:
        _strict_object(invariant, {"invariant_id", "criterion", "failure_condition"}, f"{case_id} invariant")
        invariant_id = invariant["invariant_id"]
        if not isinstance(invariant_id, str) or not INVARIANT_ID_RE.fullmatch(invariant_id) or invariant_id in invariant_ids:
            raise EvalError(f"{case_id} has an invalid or duplicate invariant_id")
        invariant_ids.add(invariant_id)
        if not isinstance(invariant["criterion"], str) or len(invariant["criterion"]) < 12:
            raise EvalError(f"{case_id} has an incomplete invariant criterion")
        if not isinstance(invariant["failure_condition"], str) or len(invariant["failure_condition"]) < 12:
            raise EvalError(f"{case_id} has an incomplete invariant failure condition")
    return case


def _load_jsonl(path: Path, label: str) -> list[Any]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise EvalError(f"could not read {label}: {exc}") from exc
    if not lines:
        raise EvalError(f"{label} is empty")
    values = []
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            raise EvalError(f"{label} contains a blank record at line {line_number}")
        try:
            values.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise EvalError(f"{label} line {line_number} is invalid JSON: {exc}") from exc
    return values


def load_cases(path: Path, schema_path: Path = DEFAULT_CASE_SCHEMA) -> dict[str, dict[str, Any]]:
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvalError(f"could not read valid case schema: {exc}") from exc
    if not isinstance(schema, dict) or schema.get("additionalProperties") is not False:
        raise EvalError("case schema must be a strict JSON object schema")
    cases: dict[str, dict[str, Any]] = {}
    for line_number, value in enumerate(_load_jsonl(path, "behavior cases"), 1):
        case = validate_case(value, line_number)
        if case["case_id"] in cases:
            raise EvalError(f"duplicate case_id: {case['case_id']}")
        cases[case["case_id"]] = case
    counts = Counter(case["category"] for case in cases.values())
    for category, required in CATEGORIES.items():
        if counts[category] < required:
            raise EvalError(f"case coverage needs at least {required} {category} cases")
    if len(cases) < 40:
        raise EvalError("case coverage needs at least 40 cases")
    if {case["unit"] for case in cases.values() if case["unit"] is not None} != set(range(1, 9)):
        raise EvalError("case coverage must include all AP Calculus AB Units 1-8")
    established_practices = {
        case["expected_primary_practice"]["id"]
        for case in cases.values()
        if case["expected_primary_practice"]["status"] == "established"
    }
    if established_practices != PRACTICES:
        raise EvalError("case coverage must include all four mathematical practices")
    if set().union(*(set(case["representations"]) for case in cases.values())) != REPRESENTATIONS:
        raise EvalError("case coverage must include all five representations")
    if sum(case["language"] == "zh-CN" for case in cases.values()) < 8:
        raise EvalError("case coverage needs at least eight zh-CN requests")
    if set().union(*(set(case["critical_lanes"]) for case in cases.values())) != CRITICAL_LANES:
        raise EvalError("case coverage must include all six critical lanes")
    return cases


def validate_review(value: Any, line_number: int, cases: dict[str, dict[str, Any]]) -> dict[str, Any]:
    review = _strict_object(value, REVIEW_FIELDS, f"review line {line_number}")
    if review["schema_version"] != 1 or review["case_id"] not in cases:
        raise EvalError(f"review line {line_number} has unsupported schema or case_id")
    if review["round_id"] not in {"primary", "repeat"}:
        raise EvalError(f"review line {line_number} has invalid round_id")
    for field in ("forward_context_id", "reviewer_context_id"):
        if not isinstance(review[field], str) or len(review[field]) < 3:
            raise EvalError(f"review line {line_number} has invalid {field}")
    if review["forward_context_id"] == review["reviewer_context_id"]:
        raise EvalError(f"review line {line_number} must separate forward and review contexts")
    for field in (
        "forward_context_independent",
        "rubric_hidden_from_forward_tester",
        "reviewer_independent",
    ):
        if review[field] is not True:
            raise EvalError(f"review line {line_number} must record {field}=true")
    if not isinstance(review["raw_output_sha256"], str) or not SHA256_RE.fullmatch(review["raw_output_sha256"]):
        raise EvalError(f"review line {line_number} has invalid raw_output_sha256")
    _iso_timestamp(review["reviewed_at"], f"review line {line_number} reviewed_at")
    invariants = review["invariants"]
    if not isinstance(invariants, list):
        raise EvalError(f"review line {line_number} invariants must be an array")
    expected_ids = {
        invariant["invariant_id"]
        for invariant in cases[review["case_id"]]["semantic_rubric_invariants"]
    }
    actual_ids: set[str] = set()
    for result in invariants:
        _strict_object(result, {"invariant_id", "passed", "evidence"}, f"review line {line_number} invariant")
        invariant_id = result["invariant_id"]
        if invariant_id in actual_ids:
            raise EvalError(f"review line {line_number} duplicates invariant {invariant_id}")
        actual_ids.add(invariant_id)
        if not isinstance(result["passed"], bool):
            raise EvalError(f"review line {line_number} invariant {invariant_id} lacks a boolean judgment")
        if not isinstance(result["evidence"], str) or len(result["evidence"]) < 12:
            raise EvalError(f"review line {line_number} invariant {invariant_id} lacks review evidence")
    if actual_ids != expected_ids:
        raise EvalError(f"review line {line_number} does not judge the exact case invariants")
    return review


def load_reviews(
    path: Path,
    cases: dict[str, dict[str, Any]],
    schema_path: Path = DEFAULT_REVIEW_SCHEMA,
) -> list[dict[str, Any]]:
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvalError(f"could not read valid review schema: {exc}") from exc
    if not isinstance(schema, dict) or schema.get("additionalProperties") is not False:
        raise EvalError("review schema must be a strict JSON object schema")
    reviews = [
        validate_review(value, line_number, cases)
        for line_number, value in enumerate(_load_jsonl(path, "behavior reviews"), 1)
    ]
    keys: set[tuple[str, str]] = set()
    forward_contexts: set[str] = set()
    reviewer_contexts: set[str] = set()
    for review in reviews:
        key = (review["case_id"], review["round_id"])
        if key in keys:
            raise EvalError(f"duplicate review for {key[0]} round {key[1]}")
        keys.add(key)
        context = review["forward_context_id"]
        if context in forward_contexts:
            raise EvalError(f"forward context {context} was reused across case rounds")
        forward_contexts.add(context)
        reviewer_contexts.add(review["reviewer_context_id"])
    overlap = forward_contexts & reviewer_contexts
    if overlap:
        raise EvalError(f"forward and reviewer context sets overlap: {sorted(overlap)}")
    primary_ids = {review["case_id"] for review in reviews if review["round_id"] == "primary"}
    if primary_ids != set(cases):
        missing = sorted(set(cases) - primary_ids)
        extra = sorted(primary_ids - set(cases))
        raise EvalError(f"primary reviews must cover every case; missing={missing}, extra={extra}")
    repeats = [review for review in reviews if review["round_id"] == "repeat"]
    if len(repeats) < 10 or len({review["case_id"] for review in repeats}) < 10:
        raise EvalError("at least 10 distinct cases need fresh-context repeat reviews")
    for repeat in repeats:
        if cases[repeat["case_id"]]["severity"] != "critical":
            raise EvalError(f"repeat case {repeat['case_id']} is not critical")
        primary = next(
            review for review in reviews
            if review["case_id"] == repeat["case_id"] and review["round_id"] == "primary"
        )
        if primary["forward_context_id"] == repeat["forward_context_id"]:
            raise EvalError(f"repeat case {repeat['case_id']} did not use a fresh context")
    repeat_lanes = set().union(
        *(set(cases[review["case_id"]]["critical_lanes"]) for review in repeats)
    )
    if repeat_lanes != CRITICAL_LANES:
        raise EvalError(
            f"repeat cases must cover all six critical lanes; missing={sorted(CRITICAL_LANES - repeat_lanes)}"
        )
    repeat_categories = {cases[review["case_id"]]["category"] for review in repeats}
    if repeat_categories != set(CATEGORIES):
        raise EvalError(
            f"repeat cases must cover all five behavior categories; missing={sorted(set(CATEGORIES) - repeat_categories)}"
        )
    return reviews


def repeat_case_ids(cases: dict[str, dict[str, Any]], minimum: int = 10) -> list[str]:
    """Choose stable critical repeats that cover every lane and behavior category."""

    candidates = [case_id for case_id, case in cases.items() if case["severity"] == "critical"]
    selected: list[str] = []
    missing_lanes = set(CRITICAL_LANES)
    missing_categories = set(CATEGORIES)
    while missing_lanes or missing_categories:
        ranked = sorted(
            (case_id for case_id in candidates if case_id not in selected),
            key=lambda case_id: (
                -(
                    len(set(cases[case_id]["critical_lanes"]) & missing_lanes)
                    + int(cases[case_id]["category"] in missing_categories)
                ),
                case_id,
            ),
        )
        if not ranked:
            raise EvalError("critical cases cannot cover all repeat lanes/categories")
        chosen = ranked[0]
        gain = len(set(cases[chosen]["critical_lanes"]) & missing_lanes) + int(
            cases[chosen]["category"] in missing_categories
        )
        if gain == 0:
            raise EvalError("critical cases cannot cover all repeat lanes/categories")
        selected.append(chosen)
        missing_lanes -= set(cases[chosen]["critical_lanes"])
        missing_categories.discard(cases[chosen]["category"])
    for case_id in sorted(candidates):
        if len(selected) >= minimum:
            break
        if case_id not in selected:
            selected.append(case_id)
    if len(selected) < minimum:
        raise EvalError(f"fewer than {minimum} critical cases are available for repeat testing")
    return selected


def score(cases: dict[str, dict[str, Any]], reviews: Iterable[dict[str, Any]]) -> dict[str, Any]:
    reviews = list(reviews)
    primary = {review["case_id"]: review for review in reviews if review["round_id"] == "primary"}
    repeats = [review for review in reviews if review["round_id"] == "repeat"]
    case_pass = {
        case_id: all(result["passed"] for result in review["invariants"])
        for case_id, review in primary.items()
    }
    failures = [case_id for case_id in sorted(cases) if not case_pass[case_id]]
    failed_invariants = [
        {"case_id": review["case_id"], "round_id": review["round_id"], "invariant_id": result["invariant_id"]}
        for review in reviews
        for result in review["invariants"]
        if not result["passed"]
    ]
    category_scores: dict[str, dict[str, Any]] = {}
    for category in CATEGORIES:
        identifiers = [case_id for case_id, case in cases.items() if case["category"] == category]
        passed = sum(case_pass[case_id] for case_id in identifiers)
        category_scores[category] = {
            "passed": passed,
            "total": len(identifiers),
            "pass_rate": passed / len(identifiers),
        }
    critical_failures = [
        failure for failure in failed_invariants
        if cases[failure["case_id"]]["severity"] == "critical"
    ]
    repeat_failures = [failure for failure in failed_invariants if failure["round_id"] == "repeat"]
    repeat_lanes = set().union(
        *(set(cases[review["case_id"]]["critical_lanes"]) for review in repeats)
    ) if repeats else set()
    repeat_categories = {cases[review["case_id"]]["category"] for review in repeats}
    lane_failures = defaultdict(list)
    for case_id in failures:
        for lane in cases[case_id]["critical_lanes"]:
            lane_failures[lane].append(case_id)
    overall_rate = sum(case_pass.values()) / len(cases)
    thresholds = {
        "overall_case_pass_rate_at_least_0_95": overall_rate >= 0.95,
        "every_category_at_least_0_90": all(
            result["pass_rate"] >= 0.90 for result in category_scores.values()
        ),
        "all_critical_invariants_pass": not critical_failures,
        "all_six_critical_lanes_zero_failures": not lane_failures,
        "ten_or_more_critical_fresh_context_repeats": len(repeats) >= 10,
        "repeat_cases_cover_all_six_critical_lanes": repeat_lanes == CRITICAL_LANES,
        "repeat_cases_cover_all_five_categories": repeat_categories == set(CATEGORIES),
        "all_repeat_invariants_pass": not repeat_failures,
    }
    return {
        "overall_status": "pass" if all(thresholds.values()) else "fail",
        "case_count": len(cases),
        "primary_passed": sum(case_pass.values()),
        "overall_case_pass_rate": overall_rate,
        "category_scores": category_scores,
        "repeat_case_count": len(repeats),
        "failed_case_ids": failures,
        "failed_invariants": failed_invariants,
        "critical_lane_failures": dict(sorted(lane_failures.items())),
        "thresholds": thresholds,
    }


def self_check(cases: dict[str, dict[str, Any]]) -> dict[str, Any]:
    reviews = []
    repeat_ids = repeat_case_ids(cases)
    for index, (case_id, case) in enumerate(cases.items()):
        reviews.append(
            {
                "schema_version": 1,
                "case_id": case_id,
                "round_id": "primary",
                "forward_context_id": f"self-forward-primary-{index}",
                "forward_context_independent": True,
                "rubric_hidden_from_forward_tester": True,
                "reviewer_context_id": "self-reviewer",
                "reviewer_independent": True,
                "raw_output_sha256": hashlib.sha256(case_id.encode()).hexdigest(),
                "reviewed_at": "2026-08-31T00:00:00Z",
                "invariants": [
                    {"invariant_id": item["invariant_id"], "passed": True, "evidence": "Synthetic scorer self-check evidence only."}
                    for item in case["semantic_rubric_invariants"]
                ],
            }
        )
    for index, case_id in enumerate(repeat_ids):
        case = cases[case_id]
        reviews.append(
            {
                **reviews[list(cases).index(case_id)],
                "round_id": "repeat",
                "forward_context_id": f"self-forward-repeat-{index}",
                "raw_output_sha256": hashlib.sha256((case_id + "repeat").encode()).hexdigest(),
                "invariants": [
                    {"invariant_id": item["invariant_id"], "passed": True, "evidence": "Synthetic repeat scorer self-check evidence."}
                    for item in case["semantic_rubric_invariants"]
                ],
            }
        )
    passing = score(cases, reviews)
    if passing["overall_status"] != "pass":
        raise EvalError("scorer self-check did not accept a complete passing fixture")
    failing = json.loads(json.dumps(reviews))
    failing[0]["invariants"][0]["passed"] = False
    rejected = score(cases, failing)
    if rejected["overall_status"] != "fail" or not rejected["failed_invariants"]:
        raise EvalError("scorer self-check did not reject a failed critical invariant")
    return {
        "status": "pass",
        "case_count": len(cases),
        "synthetic_review_count": len(reviews),
        "threshold_rejection_checked": True,
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    result.add_argument("--case-schema", type=Path, default=DEFAULT_CASE_SCHEMA)
    result.add_argument("--reviews", type=Path, default=DEFAULT_REVIEWS)
    result.add_argument("--review-schema", type=Path, default=DEFAULT_REVIEW_SCHEMA)
    result.add_argument("--self-check", action="store_true")
    result.add_argument("--evidence-json", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        cases = load_cases(args.cases, args.case_schema)
        if args.self_check:
            payload = {"overall_status": "pass", "self_check": self_check(cases)}
        else:
            payload = score(cases, load_reviews(args.reviews, cases, args.review_schema))
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        return 0 if payload["overall_status"] == "pass" else 1
    except (EvalError, OSError, UnicodeError, json.JSONDecodeError) as exc:
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
