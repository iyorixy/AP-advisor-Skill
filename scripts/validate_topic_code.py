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
    return [topic.full_citation for topic in ranked[: max(n, 0)]]


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
        "sources",
        "mathematical_practices",
        "high_risk_methods",
        "topic_dependencies",
        "exclusions",
    }
    if not isinstance(value, dict) or not required <= value.keys():
        raise BoundaryDataError("content-boundary object is missing required fields")
    if value["schema_version"] != 1 or not isinstance(value["sources"], list):
        raise BoundaryDataError("unsupported schema version or invalid sources")
    sources = value["sources"]
    if not sources or any(
        not isinstance(item, dict)
        or not isinstance(item.get("id"), str)
        or not isinstance(item.get("url"), str)
        or not item["url"].startswith("https://apcentral.collegeboard.org/")
        for item in sources
    ):
        raise BoundaryDataError("sources must contain official AP Central metadata")
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("citation", nargs="+", help="one or more complete citations")
    parser.add_argument("--framework", type=Path, default=DEFAULT_FRAMEWORK_PATH)
    parser.add_argument("--boundaries", type=Path, default=DEFAULT_BOUNDARIES_PATH)
    parser.add_argument("--course", choices=sorted(COURSES))
    style = parser.add_mutually_exclusive_group()
    style.add_argument(
        "--assessed-topic",
        action="store_true",
        help="require every mapping to be assessed; this is not exam-oriented",
    )
    style.add_argument(
        "--ap-oriented",
        dest="legacy_ap_oriented",
        action="store_true",
        help="deprecated alias for --assessed-topic",
    )
    parser.add_argument("--method", action="append", default=[])
    parser.add_argument(
        "--mathematical-practice", dest="practices", action="append", default=[]
    )
    parser.add_argument("--evidence-json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    assessed_topic = args.assessed_topic or args.legacy_ap_oriented
    code, payload = validate_citations(
        args.citation,
        course=args.course,
        assessed_topic=assessed_topic,
        framework_path=args.framework,
    )
    if code != 2 and (args.method or args.practices):
        if args.course is None:
            code, payload = 2, _error_evidence(
                None, assessed_topic, "--course is required for content-boundary checks"
            )
        else:
            passed = [row for row in payload["results"] if row["status"] == "pass"]
            if passed:
                topic_numbers = [
                    row["citation"].split(", Topic ", 1)[1].split(" ", 1)[0]
                    for row in passed
                ]
                try:
                    failures = validate_content_boundary(
                        course=args.course,
                        content_topic=topic_numbers[0],
                        supporting_topics=topic_numbers[1:],
                        methods=args.method,
                        mathematical_practices=args.practices,
                        assessed_topic=assessed_topic,
                        boundaries_path=args.boundaries,
                    )
                except BoundaryDataError as exc:
                    code, payload = 2, _error_evidence(
                        args.course, assessed_topic, str(exc)
                    )
                else:
                    payload["content_boundary"] = {
                        "status": "fail" if failures else "pass",
                        "failures": failures,
                    }
                    if failures:
                        payload["overall_status"] = "fail"
                        code = 1
    if args.evidence_json:
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    else:
        _print_human(payload)
    return code


def _configure_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="strict")


if __name__ == "__main__":
    _configure_utf8()
    raise SystemExit(main())
