#!/usr/bin/env python3
"""Validate exact AP Precalculus and Calculus Advisor Topic mappings and high-risk content boundaries.

The matcher compares the entire citation after Unicode NFKC normalization.
It intentionally does not extract a plausible Topic from surrounding text.

Exit codes: 0 pass, 1 invalid mapping/content claim, 2 setup/data error.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FRAMEWORK_PATH = REPO_ROOT / "references" / "ap-calc-framework.md"
DEFAULT_BOUNDARIES_PATH = REPO_ROOT / "references" / "ap-content-boundaries.json"
COURSES = {"precalculus", "calc-ab", "calc-bc"}
EVIDENCE_SCHEMA_VERSION = 2
EVIDENCE_VALIDATOR = "ap-calculus-advisor-topic-code"

RE_COURSE = re.compile(r"^##\s+(.+?)\s*$")
RE_UNIT = re.compile(r"^-\s+Unit\s+(\d+)\s+—\s+(.+?)\s*$")
RE_TOPIC = re.compile(r"^ {2}-\s+(.+?)\s*$")
RE_CONTINUATION = re.compile(r"^ {4}(?!-)(.+?)\s*$")
RE_TOPIC_CODE = re.compile(r"^(\d+\.\d+)\s+(.+?)\s*$")
RE_BC = re.compile(r"\s*\(BC\)\s*$")
RE_NOT_ASSESSED = re.compile(
    r"\s*\(not assessed on AP Exam\)\s*$", re.IGNORECASE
)


class FrameworkParseError(ValueError):
    pass


class BoundaryDataError(ValueError):
    pass


@dataclass(frozen=True)
class Topic:
    course: str
    unit_num: str
    unit_title: str
    topic_num: str
    topic_title: str
    bc_only: bool
    exam_assessed: bool

    @property
    def citation(self) -> str:
        return f"Unit {self.unit_num}, Topic {self.topic_num} — {self.topic_title}"

    @property
    def full_citation(self) -> str:
        return (
            f"{self.course} — Unit {self.unit_num} ({self.unit_title}), "
            f"Topic {self.topic_num} — {self.topic_title}"
        )


def parse_framework(path: Path = DEFAULT_FRAMEWORK_PATH) -> list[Topic]:
    lines = path.read_text(encoding="utf-8").splitlines()
    topics: list[Topic] = []
    course = unit_num = unit_title = None
    unit_bc_only = unit_not_assessed = False
    index = 0

    while index < len(lines):
        line = lines[index]
        if match := RE_COURSE.match(line):
            course = match.group(1)
            unit_num = unit_title = None
            unit_bc_only = unit_not_assessed = False
            index += 1
            continue
        if match := RE_UNIT.match(line):
            unit_num, raw_title = match.groups()
            unit_bc_only = bool(RE_BC.search(raw_title))
            unit_not_assessed = bool(RE_NOT_ASSESSED.search(raw_title))
            unit_title = RE_NOT_ASSESSED.sub("", RE_BC.sub("", raw_title)).rstrip()
            index += 1
            continue
        if re.match(r"^\s*-\s+Unit\b", line):
            raise FrameworkParseError(f"malformed unit at line {index + 1}: {line!r}")
        if match := RE_TOPIC.match(line):
            line_number = index + 1
            parts = [match.group(1)]
            index += 1
            while index < len(lines) and (continued := RE_CONTINUATION.match(lines[index])):
                parts.append(continued.group(1))
                index += 1
            if course is None or unit_num is None or unit_title is None:
                raise FrameworkParseError(f"topic before course/unit at line {line_number}")
            for chunk in " ".join(parts).split("/"):
                if not (topic_match := RE_TOPIC_CODE.match(chunk.strip())):
                    raise FrameworkParseError(
                        f"malformed topic at line {line_number}: {chunk.strip()!r}"
                    )
                topic_num, raw_title = topic_match.groups()
                topic_bc_only = bool(RE_BC.search(raw_title))
                topic_not_assessed = bool(RE_NOT_ASSESSED.search(raw_title))
                topic_title = RE_NOT_ASSESSED.sub(
                    "", RE_BC.sub("", raw_title)
                ).rstrip()
                topics.append(
                    Topic(
                        course,
                        unit_num,
                        unit_title,
                        topic_num,
                        topic_title,
                        unit_bc_only or topic_bc_only,
                        not (unit_not_assessed or topic_not_assessed),
                    )
                )
            continue
        if re.match(r"^\s*-\s+\d+\.\d+\b", line):
            raise FrameworkParseError(
                f"malformed topic indentation at line {index + 1}: {line!r}"
            )
        index += 1
    return topics


def framework_data_errors(topics: Iterable[Topic]) -> list[str]:
    errors: list[str] = []
    seen: set[tuple[str, str]] = set()
    for topic in topics:
        key = (topic.course, topic.topic_num)
        if key in seen:
            errors.append(f"duplicate topic {topic.topic_num!r} in {topic.course!r}")
        seen.add(key)
        if topic.topic_num.partition(".")[0] != topic.unit_num:
            errors.append(
                f"topic {topic.topic_num!r} is under Unit {topic.unit_num} "
                f"in {topic.course!r}"
            )
    return errors


def filter_by_course(topics: Iterable[Topic], course: str | None) -> list[Topic]:
    if course is None:
        return list(topics)
    if course == "precalculus":
        return [topic for topic in topics if topic.course.startswith("AP Precalculus")]
    calculus = [topic for topic in topics if topic.course.startswith("AP Calculus")]
    return calculus if course == "calc-bc" else [t for t in calculus if not t.bc_only]


def normalize_citation(text: str) -> str:
    """Apply the only allowed citation normalization."""

    return unicodedata.normalize("NFKC", text)


def find_match(topics: Iterable[Topic], query: str) -> Topic | None:
    normalized = normalize_citation(query)
    matches = [topic for topic in topics if normalize_citation(topic.citation) == normalized]
    return matches[0] if len(matches) == 1 else None


def closest_candidates(topics: Iterable[Topic], query: str, n: int = 5) -> list[str]:
    normalized = normalize_citation(query)
    ranked = sorted(
        topics,
        key=lambda topic: difflib.SequenceMatcher(
            None, normalized, normalize_citation(topic.citation)
        ).ratio(),
        reverse=True,
    )
    return [topic.citation for topic in ranked[: max(n, 0)]]


def validate_citations(
    citations: Iterable[str],
    *,
    course: str | None = None,
    assessed_topic: bool = False,
    framework_path: Path = DEFAULT_FRAMEWORK_PATH,
) -> tuple[int, dict[str, Any]]:
    """Return an exit code and stable evidence without printing."""

    if course is not None and course not in COURSES:
        return 2, _error_evidence(course, assessed_topic, f"unknown course {course!r}")
    citations = list(citations)
    if not citations:
        return 2, _error_evidence(course, assessed_topic, "no citations supplied")
    try:
        all_topics = parse_framework(framework_path)
    except (FrameworkParseError, OSError, UnicodeError) as exc:
        return 2, _error_evidence(
            course, assessed_topic, f"could not load framework: {exc}"
        )
    errors = framework_data_errors(all_topics)
    if not all_topics or errors:
        detail = "; ".join(errors) if errors else "no topics parsed"
        return 2, _error_evidence(course, assessed_topic, f"invalid framework: {detail}")

    topics = filter_by_course(all_topics, course)
    results: list[dict[str, Any]] = []
    failed = False
    for query in citations:
        match = find_match(topics, query)
        if match is None and course == "calc-ab":
            bc_match = find_match(filter_by_course(all_topics, "calc-bc"), query)
            if bc_match is not None and bc_match.bc_only:
                results.append(
                    _failed_result(
                        query,
                        f"{bc_match.full_citation} is BC-only and invalid for AP Calculus AB",
                        bc_match,
                    )
                )
                failed = True
                continue
        if match is None:
            results.append(
                {
                    "input": query,
                    "status": "fail",
                    "message": f"no NFKC exact match for: {query}",
                    "candidates": closest_candidates(topics, query),
                }
            )
            failed = True
        elif assessed_topic and not match.exam_assessed:
            results.append(
                _failed_result(
                    query,
                    f"{match.full_citation} is not assessed and cannot be used "
                    "as assessed-topic content",
                    match,
                )
            )
            failed = True
        else:
            results.append(
                {
                    "input": query,
                    "status": "pass",
                    "citation": match.citation,
                    "topic_exam_scope": (
                        "assessed" if match.exam_assessed else "not-assessed"
                    ),
                }
            )
    payload = _base_evidence(course, assessed_topic, "fail" if failed else "pass")
    payload["results"] = results
    return (1 if failed else 0), payload


def _base_evidence(
    course: str | None, assessed_topic: bool, overall_status: str
) -> dict[str, Any]:
    return {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "validator": EVIDENCE_VALIDATOR,
        "course": course or "unfiltered",
        "assessed_topic": assessed_topic,
        "overall_status": overall_status,
        "results": [],
    }


def _error_evidence(
    course: str | None, assessed_topic: bool, message: str
) -> dict[str, Any]:
    payload = _base_evidence(course, assessed_topic, "error")
    payload["error"] = message
    return payload


def _failed_result(query: str, message: str, topic: Topic) -> dict[str, Any]:
    return {
        "input": query,
        "status": "fail",
        "citation": topic.citation,
        "topic_exam_scope": "assessed" if topic.exam_assessed else "not-assessed",
        "message": message,
    }


def load_boundaries(path: Path = DEFAULT_BOUNDARIES_PATH) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BoundaryDataError(f"could not load content boundaries: {exc}") from exc
    required = {
        "schema_version",
        "source_checked_at",
        "school_year",
        "applicable_exam_administration",
        "sources",
        "ab_adaptive_scope",
        "mathematical_practices",
        "practice_names",
        "exam_tasks",
        "high_risk_methods",
        "topic_dependencies",
        "exclusions",
        "corrections",
        "official_source_conflicts",
        "legacy_markers",
    }
    if not isinstance(value, dict) or value.keys() != required:
        raise BoundaryDataError("content-boundary object has missing or unexpected fields")
    if value["schema_version"] != 1 or not isinstance(value["sources"], list):
        raise BoundaryDataError("unsupported schema version or invalid sources")
    if (
        not isinstance(value["source_checked_at"], str)
        or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value["source_checked_at"])
        or not isinstance(value["school_year"], str)
        or not value["school_year"]
        or not isinstance(value["applicable_exam_administration"], str)
        or not value["applicable_exam_administration"]
    ):
        raise BoundaryDataError("source date, school year, or exam administration is invalid")
    sources = value["sources"]
    if not sources or any(
        not isinstance(item, dict)
        or not isinstance(item.get("id"), str)
        or not isinstance(item.get("url"), str)
        or urlparse(item["url"]).scheme != "https"
        or urlparse(item["url"]).hostname
        not in {"apcentral.collegeboard.org", "apstudents.collegeboard.org"}
        for item in sources
    ):
        raise BoundaryDataError("sources must contain official College Board metadata")
    source_ids = {item["id"] for item in sources}
    if len(source_ids) != len(sources):
        raise BoundaryDataError("source ids must be unique")
    practices = value["mathematical_practices"]
    if (
        not isinstance(practices, dict)
        or set(practices) != {"precalculus", "calculus"}
        or any(
            not isinstance(items, list)
            or not items
            or any(not isinstance(item, str) or not item for item in items)
            for items in practices.values()
        )
    ):
        raise BoundaryDataError("mathematical_practices is invalid")
    practice_names = value["practice_names"]
    calculus_practices = set(practices["calculus"])
    if (
        not isinstance(practice_names, dict)
        or set(practice_names) != calculus_practices
        or any(not isinstance(name, str) or not name for name in practice_names.values())
    ):
        raise BoundaryDataError("practice_names is invalid")

    scope = value["ab_adaptive_scope"]
    if (
        not isinstance(scope, dict)
        or scope.get("units") != list(range(1, 9))
        or not isinstance(scope.get("embedded_bc_only_topics"), list)
        or scope.get("source") not in source_ids
    ):
        raise BoundaryDataError("ab_adaptive_scope is invalid")

    exam_tasks = value["exam_tasks"]
    if not isinstance(exam_tasks, dict) or set(exam_tasks) != {
        "multiple-choice",
        "free-response",
    }:
        raise BoundaryDataError("exam_tasks must contain current MCQ and FRQ contracts")
    allowed_conditions = {"calculator-not-permitted", "calculator-required-section"}
    allowed_representations = {"analytical", "graphical", "numerical", "tabular", "verbal"}
    for name, task in exam_tasks.items():
        if (
            not isinstance(task, dict)
            or not isinstance(task.get("supports_full_task"), bool)
            or set(task.get("allowed_calculator_conditions", [])) != allowed_conditions
            or set(task.get("allowed_representations", [])) != allowed_representations
            or not set(task.get("allowed_practices", [])) <= calculus_practices
            or task.get("source") not in source_ids
        ):
            raise BoundaryDataError(f"exam_tasks.{name} is invalid")
    for section in ("high_risk_methods", "topic_dependencies"):
        if not isinstance(value[section], dict):
            raise BoundaryDataError(f"{section} must be an object")
        for key, item in value[section].items():
            if not isinstance(item, dict) or item.get("source") not in source_ids:
                raise BoundaryDataError(f"{section}.{key} has an invalid source")
    for key, item in value["high_risk_methods"].items():
        if (
            not isinstance(item.get("allowed_courses"), list)
            or any(course not in COURSES for course in item["allowed_courses"])
            or not isinstance(item.get("allowed_content_topics"), list)
            or not isinstance(item.get("reason"), str)
        ):
            raise BoundaryDataError(f"high_risk_methods.{key} is invalid")
    for key, item in value["topic_dependencies"].items():
        if (
            not isinstance(item.get("requires_content_topics"), list)
            or not isinstance(item.get("reason"), str)
        ):
            raise BoundaryDataError(f"topic_dependencies.{key} is invalid")
    if not isinstance(value["exclusions"], list) or any(
        not isinstance(item, dict)
        or item.get("source") not in source_ids
        or item.get("course") not in COURSES
        or not isinstance(item.get("content_topic_prefix"), str)
        or not isinstance(item.get("excluded_from"), str)
        or not isinstance(item.get("reason"), str)
        for item in value["exclusions"]
    ):
        raise BoundaryDataError("exclusions contain invalid records or sources")
    if not isinstance(value["corrections"], list) or any(
        not isinstance(item, dict)
        or item.get("source") not in source_ids
        or not isinstance(item.get("rule"), str)
        for item in value["corrections"]
    ):
        raise BoundaryDataError("corrections contain an invalid record")
    if not isinstance(value["official_source_conflicts"], list) or any(
        not isinstance(item, dict)
        or not isinstance(item.get("id"), str)
        or not isinstance(item.get("sources"), list)
        or not item["sources"]
        or not set(item["sources"]) <= source_ids
        or not isinstance(item.get("handling"), str)
        for item in value["official_source_conflicts"]
    ):
        raise BoundaryDataError("official_source_conflicts contain an invalid record")
    if not isinstance(value["legacy_markers"], list) or not value["legacy_markers"]:
        raise BoundaryDataError("legacy_markers must be a non-empty array")
    return value


def validate_content_boundary(
    *,
    course: str,
    content_topic: str,
    supporting_topics: Iterable[str] = (),
    methods: Iterable[str] = (),
    mathematical_practices: Iterable[str] = (),
    assessed_topic: bool = False,
    boundaries_path: Path = DEFAULT_BOUNDARIES_PATH,
) -> list[str]:
    """Validate the small set of decision-changing AP content constraints."""

    data = load_boundaries(boundaries_path)
    failures: list[str] = []
    supporting = set(supporting_topics)
    if course not in COURSES:
        return [f"unknown course {course!r}"]

    practice_family = "precalculus" if course == "precalculus" else "calculus"
    allowed_practices = set(data["mathematical_practices"][practice_family])
    for practice in mathematical_practices:
        if practice not in allowed_practices:
            failures.append(
                f"mathematical practice {practice!r} is invalid for {course}"
            )

    for method in methods:
        constraint = data["high_risk_methods"].get(method)
        if constraint is None:
            failures.append(f"unknown high-risk method {method!r}")
            continue
        if course not in constraint["allowed_courses"]:
            failures.append(constraint["reason"])
        elif content_topic not in constraint["allowed_content_topics"]:
            failures.append(
                f"method {method!r} cannot be mapped to content Topic {content_topic}; "
                + constraint["reason"]
            )
        if content_topic in constraint.get("forbidden_content_topics", []):
            failures.append(
                f"method {method!r} is explicitly excluded from Topic {content_topic}"
            )

    dependency = data["topic_dependencies"].get(f"{course}:{content_topic}")
    if dependency:
        missing = set(dependency["requires_content_topics"]) - supporting
        if missing:
            failures.append(
                f"Topic {content_topic} is missing required supporting Topic(s): "
                + ", ".join(sorted(missing))
            )

    if assessed_topic:
        for exclusion in data["exclusions"]:
            if (
                exclusion["course"] == course
                and content_topic.startswith(exclusion["content_topic_prefix"])
                and exclusion["excluded_from"] == "assessed-topic"
            ):
                failures.append(exclusion["reason"])
    return failures


def validate_assessment_task(
    *,
    exam_task: str | None,
    full_task: bool,
    calculator_condition: str | None,
    representations: Iterable[str],
    justification: str | None,
    mathematical_practices: Iterable[str],
    boundaries_path: Path = DEFAULT_BOUNDARIES_PATH,
) -> list[str]:
    """Validate declared exam-task metadata without claiming content quality."""

    if exam_task is None:
        extras = []
        if full_task:
            extras.append("--full-task")
        if calculator_condition is not None:
            extras.append("--calculator-condition")
        if list(representations):
            extras.append("--representation")
        if justification is not None:
            extras.append("--justification")
        return [f"{', '.join(extras)} requires --exam-task"] if extras else []

    data = load_boundaries(boundaries_path)
    task = data["exam_tasks"].get(exam_task)
    if task is None:
        return [f"unknown exam task {exam_task!r}"]
    failures: list[str] = []
    representations = list(representations)
    practices = list(mathematical_practices)
    if full_task and not task["supports_full_task"]:
        failures.append(f"{exam_task} cannot be validated as a full task")
    if calculator_condition is None:
        failures.append("an exam task requires --calculator-condition")
    elif calculator_condition not in task["allowed_calculator_conditions"]:
        failures.append(
            f"calculator condition {calculator_condition!r} is invalid for {exam_task}"
        )
    if not representations:
        failures.append("an exam task requires at least one --representation")
    else:
        invalid = set(representations) - set(task["allowed_representations"])
        if invalid:
            failures.append(
                "invalid representation(s): " + ", ".join(sorted(invalid))
            )
    if justification is None:
        failures.append("an exam task requires --justification")
    elif exam_task == "multiple-choice" and justification != "not-required":
        failures.append("multiple-choice responses do not require written justification")
    if not practices:
        failures.append("an exam task requires at least one Mathematical Practice")
    else:
        invalid_practices = set(practices) - set(task["allowed_practices"])
        if invalid_practices:
            failures.append(
                f"{exam_task} does not assess: "
                + ", ".join(sorted(invalid_practices))
            )
    return failures


def _print_human(payload: dict[str, Any]) -> None:
    if payload["overall_status"] == "error":
        print(f"ERROR — {payload['error']}", file=sys.stderr)
        return
    for result in payload["results"]:
        if result["status"] == "pass":
            print(f"OK — matched: {result['citation']}")
            print(f"META — topic_exam_scope: {result['topic_exam_scope']}")
        else:
            print(f"FAIL — {result['message']}")
            for candidate in result.get("candidates", []):
                print(f"  - {candidate}")
    boundary = payload.get("content_boundary")
    if boundary:
        for failure in boundary["failures"]:
            print(f"FAIL — {failure}")


def validate_request(
    citations: Iterable[str],
    *,
    course: str | None,
    assessed_topic: bool = False,
    methods: Iterable[str] = (),
    mathematical_practices: Iterable[str] = (),
    practice_only: bool = False,
    exam_task: str | None = None,
    full_task: bool = False,
    calculator_condition: str | None = None,
    representations: Iterable[str] = (),
    justification: str | None = None,
    framework_path: Path = DEFAULT_FRAMEWORK_PATH,
    boundaries_path: Path = DEFAULT_BOUNDARIES_PATH,
) -> tuple[int, dict[str, Any]]:
    citations = list(citations)
    methods = list(methods)
    practices = list(mathematical_practices)
    representations = list(representations)

    if practice_only:
        conflicts = []
        if citations:
            conflicts.append("Topic citation")
        if assessed_topic:
            conflicts.append("--assessed-topic/--ap-oriented")
        if methods:
            conflicts.append("--method")
        if conflicts:
            payload = _error_evidence(
                course, assessed_topic, "--practice-only cannot be combined with " + ", ".join(conflicts)
            )
            payload.update({"validation_mode": "practice-only", "topic_status": "not-established"})
            return 2, payload
        if course is None or not practices:
            payload = _error_evidence(
                course,
                assessed_topic,
                "--practice-only requires --course and at least one --mathematical-practice",
            )
            payload.update({"validation_mode": "practice-only", "topic_status": "not-established"})
            return 2, payload
        code, payload = 0, _base_evidence(course, False, "pass")
        payload.update({"validation_mode": "practice-only", "topic_status": "not-established"})
        try:
            failures = validate_content_boundary(
                course=course,
                content_topic="",
                mathematical_practices=practices,
                boundaries_path=boundaries_path,
            )
            if exam_task is not None and course == "precalculus":
                failures.append("the Calculus assessment-task contract does not validate Precalculus tasks")
            else:
                failures.extend(
                    validate_assessment_task(
                        exam_task=exam_task,
                        full_task=full_task,
                        calculator_condition=calculator_condition,
                        representations=representations,
                        justification=justification,
                        mathematical_practices=practices,
                        boundaries_path=boundaries_path,
                    )
                )
        except BoundaryDataError as exc:
            error = _error_evidence(course, False, str(exc))
            error.update({"validation_mode": "practice-only", "topic_status": "not-established"})
            return 2, error
    else:
        if course is None and (
            methods
            or practices
            or assessed_topic
            or exam_task is not None
            or full_task
            or calculator_condition is not None
            or representations
            or justification is not None
        ):
            return 2, _error_evidence(
                None, assessed_topic, "--course is required for boundary or assessment-task checks"
            )
        code, payload = validate_citations(
            citations,
            course=course,
            assessed_topic=assessed_topic,
            framework_path=framework_path,
        )
        payload.update({"validation_mode": "topic", "topic_status": "validated" if code == 0 else "not-established"})
        if code != 0:
            return code, payload
        passed = [row for row in payload["results"] if row["status"] == "pass"]
        topic_numbers = [
            row["citation"].split(", Topic ", 1)[1].split(" ", 1)[0]
            for row in passed
        ]
        failures = []
        if course is not None:
            try:
                failures.extend(
                    validate_content_boundary(
                        course=course,
                        content_topic=topic_numbers[0],
                        supporting_topics=topic_numbers[1:],
                        methods=methods,
                        mathematical_practices=practices,
                        assessed_topic=assessed_topic or exam_task is not None,
                        boundaries_path=boundaries_path,
                    )
                )
                if exam_task is not None and course == "precalculus":
                    failures.append("the Calculus assessment-task contract does not validate Precalculus tasks")
                else:
                    failures.extend(
                        validate_assessment_task(
                            exam_task=exam_task,
                            full_task=full_task,
                            calculator_condition=calculator_condition,
                            representations=representations,
                            justification=justification,
                            mathematical_practices=practices,
                            boundaries_path=boundaries_path,
                        )
                    )
            except BoundaryDataError as exc:
                return 2, _error_evidence(course, assessed_topic, str(exc))

    payload["content_boundary"] = {
        "status": "fail" if failures else "pass",
        "failures": failures,
        "exam_task": exam_task,
        "task_scope": ("full" if full_task else "partial") if exam_task else None,
        "calculator_condition": calculator_condition,
        "representations": representations,
        "justification": justification,
        "mathematical_practices": practices,
    }
    if failures:
        payload["overall_status"] = "fail"
        code = 1
    return code, payload


def run_self_check(
    framework_path: Path = DEFAULT_FRAMEWORK_PATH,
    boundaries_path: Path = DEFAULT_BOUNDARIES_PATH,
) -> tuple[int, dict[str, Any]]:
    checks = 0

    def expect(label: str, expected: int, citations: Iterable[str] = (), **kwargs: Any) -> dict[str, Any]:
        nonlocal checks
        checks += 1
        code, payload = validate_request(
            citations,
            framework_path=framework_path,
            boundaries_path=boundaries_path,
            **kwargs,
        )
        if code != expected:
            detail = payload.get("error") or "; ".join(
                payload.get("content_boundary", {}).get("failures", [])
            )
            raise AssertionError(f"{label}: exit {code}; expected {expected}: {detail}")
        return payload

    try:
        topics = parse_framework(framework_path)
        errors = framework_data_errors(topics)
        boundaries = load_boundaries(boundaries_path)
        if errors:
            raise AssertionError("; ".join(errors))
        if len(topics) != 169:
            raise AssertionError(f"parsed {len(topics)} Topics; expected 169")
        calculus_topics = filter_by_course(topics, "calc-bc")
        by_code = {topic.topic_num: topic for topic in calculus_topics}
        embedded = set(boundaries["ab_adaptive_scope"]["embedded_bc_only_topics"])
        if any(code not in by_code or not by_code[code].bc_only for code in embedded):
            raise AssertionError("AB adaptive scope contains a non-BC-only or unknown Topic")

        chain_rule = "Unit 3, Topic 3.1 — The Chain Rule"
        expect("current AB Topic", 0, [chain_rule], course="calc-ab")
        parsed_legacy = build_parser().parse_args(
            ["--course", "calc-ab", "--ap-oriented", chain_rule]
        )
        checks += 1
        if not parsed_legacy.legacy_ap_oriented or parsed_legacy.assessed_topic:
            raise AssertionError("literal --ap-oriented parser compatibility failed")
        legacy = expect(
            "legacy input alias",
            0,
            [chain_rule],
            course="calc-ab",
            assessed_topic=True,
        )
        if "ap-oriented" in json.dumps(legacy):
            raise AssertionError("deprecated style leaked into evidence output")
        expect(
            "BC-only as AB",
            1,
            ["Unit 7, Topic 7.5 — Approximating Solutions Using Euler's Method"],
            course="calc-ab",
        )
        expect(
            "practice-only",
            0,
            course="calc-ab",
            practice_only=True,
            mathematical_practices=["calc-2-connecting-representations"],
        )
        expect("practice-only missing Practice", 2, course="calc-ab", practice_only=True)
        expect(
            "MCQ contract",
            0,
            [chain_rule],
            course="calc-ab",
            exam_task="multiple-choice",
            calculator_condition="calculator-not-permitted",
            representations=["analytical"],
            justification="not-required",
            mathematical_practices=["calc-1-implementing-processes"],
        )
        expect(
            "MCQ Practice 4",
            1,
            [chain_rule],
            course="calc-ab",
            exam_task="multiple-choice",
            calculator_condition="calculator-not-permitted",
            representations=["analytical"],
            justification="not-required",
            mathematical_practices=["calc-4-communication-notation"],
        )
        expect(
            "incomplete exam metadata",
            1,
            [chain_rule],
            course="calc-ab",
            exam_task="free-response",
            mathematical_practices=["calc-3-justification"],
        )
        expect(
            "FRQ contract",
            0,
            [chain_rule],
            course="calc-ab",
            exam_task="free-response",
            full_task=True,
            calculator_condition="calculator-required-section",
            representations=["analytical", "verbal"],
            justification="required",
            mathematical_practices=["calc-3-justification", "calc-4-communication-notation"],
        )
        expect(
            "Precalculus Unit 4 assessed",
            1,
            ["Unit 4, Topic 4.10 — Matrices"],
            course="precalculus",
            assessed_topic=True,
        )
        expect(
            "integration by parts as AB",
            1,
            ["Unit 6, Topic 6.14 — Selecting Techniques for Antidifferentiation"],
            course="calc-ab",
            methods=["integration-by-parts"],
        )
        expect(
            "shell method mapping",
            1,
            ["Unit 8, Topic 8.9 — Volume with Disc Method: Revolving Around the x- or y-Axis"],
            course="calc-ab",
            methods=["shell-method"],
        )
        lagrange = "Unit 10, Topic 10.12 — Lagrange Error Bound"
        taylor = "Unit 10, Topic 10.11 — Finding Taylor Polynomial Approximations of Functions"
        expect("dependency missing", 1, [lagrange], course="calc-bc")
        expect("dependency present", 0, [lagrange, taylor], course="calc-bc")
    except (AssertionError, BoundaryDataError, FrameworkParseError, OSError) as exc:
        return 2, _error_evidence(None, False, f"self-check failed: {exc}")

    payload = _base_evidence(None, False, "pass")
    payload["self_check"] = {
        "status": "pass",
        "topic_count": len(topics),
        "behavior_check_count": checks,
    }
    return 0, payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("citation", nargs="*", help="one or more complete citations")
    parser.add_argument("--framework", type=Path, default=DEFAULT_FRAMEWORK_PATH)
    parser.add_argument("--boundaries", type=Path, default=DEFAULT_BOUNDARIES_PATH)
    parser.add_argument("--course", choices=sorted(COURSES))
    style = parser.add_mutually_exclusive_group()
    style.add_argument("--assessed-topic", action="store_true")
    style.add_argument(
        "--ap-oriented",
        dest="legacy_ap_oriented",
        action="store_true",
        help="deprecated input alias for --assessed-topic; never emitted",
    )
    parser.add_argument("--practice-only", action="store_true")
    parser.add_argument("--method", action="append", default=[])
    parser.add_argument(
        "--mathematical-practice", dest="practices", action="append", default=[]
    )
    parser.add_argument("--exam-task", choices=["multiple-choice", "free-response"])
    parser.add_argument("--full-task", action="store_true")
    parser.add_argument(
        "--calculator-condition",
        choices=["calculator-not-permitted", "calculator-required-section"],
    )
    parser.add_argument(
        "--representation",
        dest="representations",
        action="append",
        choices=["analytical", "graphical", "numerical", "tabular", "verbal"],
        default=[],
    )
    parser.add_argument("--justification", choices=["required", "not-required"])
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--evidence-json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    assessed_topic = args.assessed_topic or args.legacy_ap_oriented
    if args.self_check:
        code, payload = run_self_check(args.framework, args.boundaries)
    else:
        code, payload = validate_request(
            args.citation,
            course=args.course,
            assessed_topic=assessed_topic,
            methods=args.method,
            mathematical_practices=args.practices,
            practice_only=args.practice_only,
            exam_task=args.exam_task,
            full_task=args.full_task,
            calculator_condition=args.calculator_condition,
            representations=args.representations,
            justification=args.justification,
            framework_path=args.framework,
            boundaries_path=args.boundaries,
        )
    if args.evidence_json:
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    else:
        _print_human(payload)
        if payload.get("self_check"):
            print(f"OK — self-check parsed {payload['self_check']['topic_count']} Topics")
    return code


def _configure_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="strict")


if __name__ == "__main__":
    _configure_utf8()
    raise SystemExit(main())
