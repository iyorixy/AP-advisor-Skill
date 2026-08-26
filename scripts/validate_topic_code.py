#!/usr/bin/env python3
"""
validate_topic_code.py

Validates that a Unit/Topic citation string (e.g. produced by an AI agent
generating AP Precalculus / Calculus content) actually corresponds to a real
entry in references/ap-calc-framework.md.

Requires Python 3.10 or newer. Standard-library only; no network access or
third-party dependencies.

Usage:
    python3 scripts/validate_topic_code.py "Unit 1, Topic 1.2 — Rates of Change"
    python3 scripts/validate_topic_code.py "Unit 1, Topic 1.2 — Rates of Change" "Unit 2, Topic 2.4 — Exponential Function Manipulation"
    python3 scripts/validate_topic_code.py --framework references/other.md "..."
    python3 scripts/validate_topic_code.py --course calc-ab "Unit 6, Topic 6.11 — ..."
    python3 scripts/validate_topic_code.py --course precalculus --ap-oriented "..."
    python3 scripts/validate_topic_code.py --course calc-bc --evidence-json "..."

--course restricts matching to one of {precalculus, calc-ab, calc-bc}. For
calc-ab, topics marked (BC)-only in the framework (at the unit or topic
level) are rejected even if the number/title otherwise match.

Exit codes:
    0  -> every citation matched and passed the requested scope checks
    1  -> at least one citation failed content or exam-scope validation
    2  -> command-line, framework configuration, or framework data error
"""

import argparse
import difflib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_FRAMEWORK_PATH = Path(__file__).resolve().parent.parent / "references" / "ap-calc-framework.md"

RE_COURSE = re.compile(r"^##\s+(.+?)\s*$")
RE_UNIT = re.compile(r"^-\s+Unit\s+(\d+)\s+—\s+(.+?)\s*$")
RE_TOPIC_START = re.compile(r"^ {2}-\s+(.+?)\s*$")
RE_CONTINUATION = re.compile(r"^ {4}(?!-)(.+?)\s*$")
RE_TOPIC_CODE = re.compile(r"^(\d+\.\d+)\s+(.+?)\s*$")
RE_BC_MARKER = re.compile(r"\(BC\)\s*$")
RE_NOT_ASSESSED_MARKER = re.compile(r"\s*\(not assessed on AP Exam\)\s*$", re.IGNORECASE)

COURSE_FILTERS = {
    "precalculus": lambda t: t.course.startswith("AP Precalculus"),
    "calc-ab": lambda t: t.course.startswith("AP Calculus") and not t.bc_only,
    "calc-bc": lambda t: t.course.startswith("AP Calculus"),
}

EVIDENCE_SCHEMA_VERSION = 1
EVIDENCE_VALIDATOR = "ap-advisor-topic-code"


class FrameworkParseError(ValueError):
    """Raised when a framework line looks structural but is malformed."""


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
        return f"{self.course} — Unit {self.unit_num} ({self.unit_title}), Topic {self.topic_num} — {self.topic_title}"


def parse_framework(path: Path) -> list[Topic]:
    lines = path.read_text(encoding="utf-8").splitlines()

    topics: list[Topic] = []
    course = None
    unit_num = None
    unit_title = None
    unit_bc_only = False
    unit_not_assessed = False

    i = 0
    while i < len(lines):
        line = lines[i]

        m_course = RE_COURSE.match(line)
        if m_course:
            course = m_course.group(1)
            unit_num = None
            unit_title = None
            unit_bc_only = False
            unit_not_assessed = False
            i += 1
            continue

        m_unit = RE_UNIT.match(line)
        if m_unit:
            unit_num = m_unit.group(1)
            raw_unit_title = m_unit.group(2)
            unit_bc_only = bool(RE_BC_MARKER.search(raw_unit_title))
            unit_not_assessed = bool(RE_NOT_ASSESSED_MARKER.search(raw_unit_title))
            unit_title = RE_BC_MARKER.sub("", raw_unit_title).rstrip()
            unit_title = RE_NOT_ASSESSED_MARKER.sub("", unit_title).rstrip()
            i += 1
            continue

        if re.match(r"^\s*-\s+Unit\b", line):
            raise FrameworkParseError(
                f"malformed unit entry at line {i + 1}: {line!r}"
            )

        m_topic_start = RE_TOPIC_START.match(line)
        if m_topic_start:
            topic_line_number = i + 1
            buf = [m_topic_start.group(1)]
            i += 1
            while i < len(lines):
                m_cont = RE_CONTINUATION.match(lines[i])
                if not m_cont:
                    break
                buf.append(m_cont.group(1))
                i += 1

            joined = " ".join(buf)
            for chunk in joined.split("/"):
                chunk = chunk.strip()
                if not chunk:
                    continue
                m_code = RE_TOPIC_CODE.match(chunk)
                if not m_code:
                    raise FrameworkParseError(
                        f"malformed topic entry at line {topic_line_number}: "
                        f"{chunk!r}"
                    )
                topic_num, raw_topic_title = m_code.group(1), m_code.group(2)
                if course is None or unit_num is None or unit_title is None:
                    raise FrameworkParseError(
                        f"topic entry before course/unit at line "
                        f"{topic_line_number}: {chunk!r}"
                    )
                topic_bc_only = bool(RE_BC_MARKER.search(raw_topic_title))
                topic_not_assessed = bool(
                    RE_NOT_ASSESSED_MARKER.search(raw_topic_title)
                )
                topic_title = RE_BC_MARKER.sub("", raw_topic_title).rstrip()
                topic_title = RE_NOT_ASSESSED_MARKER.sub(
                    "", topic_title
                ).rstrip()
                bc_only = unit_bc_only or topic_bc_only
                exam_assessed = not (unit_not_assessed or topic_not_assessed)
                topics.append(
                    Topic(
                        course=course,
                        unit_num=unit_num,
                        unit_title=unit_title,
                        topic_num=topic_num,
                        topic_title=topic_title,
                        bc_only=bc_only,
                        exam_assessed=exam_assessed,
                    )
                )
            continue

        if re.match(r"^\s*-\s+\d+\.\d+\b", line):
            raise FrameworkParseError(
                f"malformed topic indentation at line {i + 1}: {line!r}"
            )

        i += 1

    return topics


def normalize(text: str) -> str:
    text = text.lower()
    text = text.replace("’", "'")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return text.strip()


def extract_query_fields(query: str):
    unit_match = re.search(r"\bunit\s+(\d+)\b", query, re.IGNORECASE)
    unit_num = unit_match.group(1) if unit_match else None

    code_match = re.search(r"\btopic\s+(\d+\.\d+)\b", query, re.IGNORECASE)
    topic_num = code_match.group(1) if code_match else None

    # The title is everything after the explicitly labeled topic code. Strip
    # only citation separators; any remaining text must exactly normalize to
    # the catalog title in find_match().
    title = None
    if code_match:
        title = query[code_match.end():].strip(" \t,-—–:")

    return unit_num, topic_num, (title or None)


def find_match(topics: list[Topic], query: str) -> Topic | None:
    unit_num, topic_num, title = extract_query_fields(query)

    if unit_num is None or topic_num is None or title is None:
        return None

    norm_title = normalize(title)
    matches = [
        t
        for t in topics
        if t.unit_num == unit_num
        and t.topic_num == topic_num
        and normalize(t.topic_title) == norm_title
    ]
    return matches[0] if len(matches) == 1 else None


def closest_candidates(topics: list[Topic], query: str, n: int = 5) -> list[str]:
    normalized_query = normalize(query)
    ranked = sorted(
        topics,
        key=lambda topic: difflib.SequenceMatcher(
            None, normalized_query, normalize(topic.citation)
        ).ratio(),
        reverse=True,
    )
    return [topic.full_citation for topic in ranked[: max(n, 0)]]


def filter_by_course(topics: list[Topic], course: str | None) -> list[Topic]:
    if course is None:
        return topics
    return [t for t in topics if COURSE_FILTERS[course](t)]


def framework_data_errors(topics: list[Topic]) -> list[str]:
    errors: list[str] = []
    seen: set[tuple[str, str]] = set()

    for topic in topics:
        key = (topic.course, topic.topic_num)
        if key in seen:
            errors.append(
                f"duplicate topic code {topic.topic_num!r} in course {topic.course!r}"
            )
        seen.add(key)

        topic_unit = topic.topic_num.partition(".")[0]
        if topic_unit != topic.unit_num:
            errors.append(
                f"topic {topic.topic_num!r} is listed under Unit {topic.unit_num} "
                f"in course {topic.course!r}"
            )

    return errors


def emit_evidence(
    *,
    course: str | None,
    ap_oriented: bool,
    overall_status: str,
    results: list[dict[str, object]],
    error: str | None = None,
) -> None:
    """Write one stable JSON evidence object for machine consumers."""

    payload: dict[str, object] = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "validator": EVIDENCE_VALIDATOR,
        "course": course or "unfiltered",
        "ap_oriented": ap_oriented,
        "overall_status": overall_status,
        "results": results,
    }
    if error is not None:
        payload["error"] = error
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def report_configuration_error(args: argparse.Namespace, message: str) -> int:
    """Report an exit-2 error without mixing human text into JSON evidence."""

    if args.evidence_json:
        emit_evidence(
            course=args.course,
            ap_oriented=args.ap_oriented,
            overall_status="error",
            results=[],
            error=message,
        )
    else:
        print(f"ERROR — {message}", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a Unit/Topic citation against a framework outline.",
    )
    parser.add_argument(
        "citation",
        nargs="+",
        help='one or more citations, e.g. "Unit N, Topic X.Y — Topic Title"',
    )
    parser.add_argument(
        "--framework",
        type=Path,
        default=DEFAULT_FRAMEWORK_PATH,
        help="path to the framework outline (default: references/ap-calc-framework.md)",
    )
    parser.add_argument(
        "--course",
        choices=sorted(COURSE_FILTERS),
        default=None,
        help=(
            "restrict matching to this course variant. For 'calc-ab', topics "
            "marked (BC)-only in the framework (at the unit or topic level) "
            "are rejected even when the topic number/title otherwise match. "
            "Omit when the requested course isn't known or doesn't need this "
            "distinction (e.g. AP Precalculus content matched without a "
            "course filter still works as before)."
        ),
    )
    parser.add_argument(
        "--ap-oriented",
        "--exam-style",
        dest="ap_oriented",
        action="store_true",
        help=(
            "reject topics that are part of the course but not assessed on its "
            "AP exam; --exam-style is retained as a compatibility alias"
        ),
    )
    parser.add_argument(
        "--evidence-json",
        action="store_true",
        help=(
            "write exactly one versioned JSON evidence object instead of "
            "human-readable validation lines"
        ),
    )
    args = parser.parse_args(argv)

    framework_path = args.framework

    if not framework_path.is_file():
        return report_configuration_error(
            args, f"framework file not found at {framework_path}"
        )

    try:
        all_topics = parse_framework(framework_path)
    except FrameworkParseError as exc:
        return report_configuration_error(args, f"invalid framework data: {exc}")
    except (OSError, UnicodeError) as exc:
        return report_configuration_error(args, f"could not read framework file: {exc}")

    if not all_topics:
        return report_configuration_error(
            args, "no topics parsed from framework file; parser or file may be broken"
        )

    data_errors = framework_data_errors(all_topics)
    if data_errors:
        return report_configuration_error(
            args, "invalid framework data: " + "; ".join(data_errors)
        )

    topics = filter_by_course(all_topics, args.course)
    if not topics:
        return report_configuration_error(
            args, f"no topics found for course filter {args.course!r}"
        )

    failed = False
    evidence_results: list[dict[str, object]] = []
    for raw_query in args.citation:
        query = raw_query.strip()
        match = find_match(topics, query)
        if match is not None:
            scope = "assessed" if match.exam_assessed else "not-assessed"
            if args.ap_oriented and not match.exam_assessed:
                message = (
                    f"{match.full_citation} is not assessed on the AP exam "
                    "and cannot be used with --ap-oriented"
                )
                evidence_results.append(
                    {
                        "input": query,
                        "status": "fail",
                        "citation": match.citation,
                        "topic_exam_scope": scope,
                        "message": message,
                    }
                )
                if not args.evidence_json:
                    print(f"FAIL — {message}")
                failed = True
            else:
                evidence_results.append(
                    {
                        "input": query,
                        "status": "pass",
                        "citation": match.citation,
                        "topic_exam_scope": scope,
                    }
                )
                if not args.evidence_json:
                    print(f"OK — matched: {match.citation}")
                    print(f"META — topic_exam_scope: {scope}")
            continue

        if args.course == "calc-ab":
            bc_match = find_match(filter_by_course(all_topics, "calc-bc"), query)
            if bc_match is not None and bc_match.bc_only:
                message = (
                    f"{bc_match.full_citation} is BC-only and is not valid "
                    "for AP Calculus AB"
                )
                evidence_results.append(
                    {
                        "input": query,
                        "status": "fail",
                        "citation": bc_match.citation,
                        "topic_exam_scope": (
                            "assessed" if bc_match.exam_assessed else "not-assessed"
                        ),
                        "message": message,
                    }
                )
                if not args.evidence_json:
                    print(f"FAIL — {message}")
                failed = True
                continue

        candidates = closest_candidates(topics, query)
        message = f"no exact match for: {query}"
        evidence_results.append(
            {
                "input": query,
                "status": "fail",
                "message": message,
                "candidates": candidates,
            }
        )
        if not args.evidence_json:
            print(f"FAIL — {message}")
            print("Closest candidates:")
            for candidate in candidates:
                print(f"  - {candidate}")
        failed = True

    if args.evidence_json:
        emit_evidence(
            course=args.course,
            ap_oriented=args.ap_oriented,
            overall_status="fail" if failed else "pass",
            results=evidence_results,
        )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
