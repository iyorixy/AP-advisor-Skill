#!/usr/bin/env python3
"""Validate exact AP Psychology Topic mappings and declared boundaries.

The matcher compares the entire citation after Unicode NFKC normalization.
It does not extract a plausible Topic from surrounding text.

Exit codes: 0 pass, 1 invalid mapping or boundary claim, 2 setup/data error.
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


SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FRAMEWORK_PATH = SKILL_ROOT / "references" / "ap-psychology-framework.md"
DEFAULT_BOUNDARIES_PATH = SKILL_ROOT / "references" / "ap-psychology-boundaries.json"
EVIDENCE_SCHEMA_VERSION = 1
EVIDENCE_VALIDATOR = "ap-psychology-advisor-topic-code"
EXPECTED_TOPIC_COUNTS = {"1": 6, "2": 8, "3": 9, "4": 7, "5": 5}

RE_UNIT = re.compile(r"^- Unit (\d+) — (.+?)$")
RE_TOPIC = re.compile(r"^  - (\d+\.\d+) (.+?)$")
RE_PRACTICE_CODE = re.compile(r"^[1-4]\.[A-Z]$")


class FrameworkParseError(ValueError):
    pass


class BoundaryDataError(ValueError):
    pass


@dataclass(frozen=True)
class Topic:
    unit_num: str
    unit_title: str
    topic_num: str
    topic_title: str

    @property
    def citation(self) -> str:
        return f"Unit {self.unit_num}, Topic {self.topic_num} — {self.topic_title}"

def parse_framework(path: Path = DEFAULT_FRAMEWORK_PATH) -> list[Topic]:
    lines = path.read_text(encoding="utf-8").splitlines()
    topics: list[Topic] = []
    in_catalog = False
    unit_num = unit_title = None

    for line_number, line in enumerate(lines, 1):
        if line == "## AP Psychology":
            in_catalog = True
            unit_num = unit_title = None
            continue
        if line.startswith("## "):
            in_catalog = False
            unit_num = unit_title = None
            continue
        if not in_catalog:
            continue
        if match := RE_UNIT.match(line):
            unit_num, unit_title = match.groups()
            continue
        if line.startswith("- Unit "):
            raise FrameworkParseError(f"malformed unit at line {line_number}: {line!r}")
        if match := RE_TOPIC.match(line):
            if unit_num is None or unit_title is None:
                raise FrameworkParseError(f"topic before unit at line {line_number}")
            topic_num, topic_title = match.groups()
            topics.append(Topic(unit_num, unit_title, topic_num, topic_title))
            continue
        if re.match(r"^\s*- \d+\.\d+\b", line):
            raise FrameworkParseError(
                f"malformed topic indentation at line {line_number}: {line!r}"
            )
    return topics


def framework_data_errors(topics: Iterable[Topic]) -> list[str]:
    topics = list(topics)
    errors: list[str] = []
    seen: set[str] = set()
    counts = {unit: 0 for unit in EXPECTED_TOPIC_COUNTS}

    for topic in topics:
        if topic.topic_num in seen:
            errors.append(f"duplicate topic {topic.topic_num!r}")
        seen.add(topic.topic_num)
        if topic.topic_num.partition(".")[0] != topic.unit_num:
            errors.append(
                f"topic {topic.topic_num!r} is under Unit {topic.unit_num}"
            )
        if topic.unit_num not in counts:
            errors.append(f"unexpected Unit {topic.unit_num}")
        else:
            counts[topic.unit_num] += 1

    for unit, expected in EXPECTED_TOPIC_COUNTS.items():
        if counts[unit] != expected:
            errors.append(
                f"Unit {unit} has {counts[unit]} Topic(s); expected {expected}"
            )
        expected_codes = {f"{unit}.{index}" for index in range(1, expected + 1)}
        missing = sorted(expected_codes - seen)
        if missing:
            errors.append(f"Unit {unit} is missing Topic(s): {', '.join(missing)}")
    return errors


def normalize_citation(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def find_match(topics: Iterable[Topic], query: str) -> Topic | None:
    normalized = normalize_citation(query)
    matches = [
        topic for topic in topics if normalize_citation(topic.citation) == normalized
    ]
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


def load_boundaries(path: Path = DEFAULT_BOUNDARIES_PATH) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BoundaryDataError(f"could not load content boundaries: {exc}") from exc

    required = {
        "schema_version",
        "sources",
        "science_practices",
        "exam_tasks",
        "scope_flags",
        "corrections",
        "legacy_markers",
    }
    if not isinstance(data, dict) or not required <= data.keys():
        raise BoundaryDataError("boundary object is missing required fields")
    if data["schema_version"] != 1:
        raise BoundaryDataError("unsupported boundary schema version")

    sources = data["sources"]
    if not isinstance(sources, list) or not sources:
        raise BoundaryDataError("sources must be a non-empty array")
    if any(
        not isinstance(source, dict)
        or not isinstance(source.get("id"), str)
        or not isinstance(source.get("url"), str)
        or not source["url"].startswith("https://apcentral.collegeboard.org/")
        for source in sources
    ):
        raise BoundaryDataError("sources must contain official AP Central metadata")
    source_ids = {source["id"] for source in sources}
    if len(source_ids) != len(sources):
        raise BoundaryDataError("source ids must be unique")

    practices = data["science_practices"]
    if not isinstance(practices, list) or not practices:
        raise BoundaryDataError("science_practices must be a non-empty array")
    practice_codes: set[str] = set()
    for practice in practices:
        if (
            not isinstance(practice, dict)
            or not isinstance(practice.get("code"), str)
            or not RE_PRACTICE_CODE.fullmatch(practice["code"])
            or practice.get("family") != practice["code"].partition(".")[0]
            or not isinstance(practice.get("name"), str)
        ):
            raise BoundaryDataError("science_practices contains an invalid record")
        practice_codes.add(practice["code"])
    if len(practice_codes) != len(practices):
        raise BoundaryDataError("science practice codes must be unique")

    tasks = data["exam_tasks"]
    expected_tasks = {
        "multiple-choice",
        "article-analysis-question",
        "evidence-based-question",
    }
    if not isinstance(tasks, dict) or set(tasks) != expected_tasks:
        raise BoundaryDataError("exam_tasks must contain the three current tasks")
    for name, task in tasks.items():
        if (
            not isinstance(task, dict)
            or task.get("source") not in source_ids
            or not isinstance(task.get("allowed_practice_families"), list)
            or not isinstance(task.get("required_practice_families"), list)
            or not set(task["required_practice_families"]) <= set(
                task["allowed_practice_families"]
            )
            or task.get("source_count") is not None
            and not isinstance(task.get("source_count"), int)
        ):
            raise BoundaryDataError(f"exam_tasks.{name} is invalid")

    flags = data["scope_flags"]
    if not isinstance(flags, dict):
        raise BoundaryDataError("scope_flags must be an object")
    for name, flag in flags.items():
        if (
            not isinstance(flag, dict)
            or flag.get("source") not in source_ids
            or not isinstance(flag.get("topics"), list)
            or not flag["topics"]
            or not isinstance(flag.get("reason"), str)
        ):
            raise BoundaryDataError(f"scope_flags.{name} is invalid")
        if "in_scope_values" in flag:
            values = flag["in_scope_values"]
            if (
                not isinstance(values, list)
                or not values
                or any(not isinstance(value, str) or not value for value in values)
                or len(values) != len(set(values))
            ):
                raise BoundaryDataError(
                    f"scope_flags.{name}.in_scope_values must be a non-empty array "
                    "of unique strings"
                )

    corrections = data["corrections"]
    if not isinstance(corrections, list) or any(
        not isinstance(item, dict)
        or item.get("source") not in source_ids
        or not isinstance(item.get("rule"), str)
        for item in corrections
    ):
        raise BoundaryDataError("corrections contains an invalid record")
    if not isinstance(data["legacy_markers"], list) or not data["legacy_markers"]:
        raise BoundaryDataError("legacy_markers must be a non-empty array")
    return data


def validate_citations(
    citations: Iterable[str],
    *,
    framework_path: Path = DEFAULT_FRAMEWORK_PATH,
) -> tuple[int, dict[str, Any]]:
    citations = list(citations)
    if not citations:
        return 2, _error_evidence("no citations supplied")
    try:
        topics = parse_framework(framework_path)
    except (FrameworkParseError, OSError, UnicodeError) as exc:
        return 2, _error_evidence(f"could not load framework: {exc}")
    errors = framework_data_errors(topics)
    if not topics or errors:
        detail = "; ".join(errors) if errors else "no topics parsed"
        return 2, _error_evidence(f"invalid framework: {detail}")

    results: list[dict[str, Any]] = []
    failed = False
    for query in citations:
        match = find_match(topics, query)
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
        else:
            results.append(
                {
                    "input": query,
                    "status": "pass",
                    "citation": match.citation,
                    "topic_exam_scope": "assessed",
                }
            )
    payload = _base_evidence("fail" if failed else "pass")
    payload["results"] = results
    return (1 if failed else 0), payload


def validate_boundaries(
    *,
    topic_numbers: Iterable[str],
    science_practices: Iterable[str],
    exam_task: str | None,
    source_count: int | None,
    scope_flags: Iterable[str],
    assessed_topic: bool,
    full_task: bool = False,
    boundaries_path: Path = DEFAULT_BOUNDARIES_PATH,
) -> list[str]:
    data = load_boundaries(boundaries_path)
    failures: list[str] = []
    topic_numbers = set(topic_numbers)
    science_practices = list(science_practices)
    scope_flags = list(scope_flags)
    practice_map = {item["code"]: item for item in data["science_practices"]}

    for code in science_practices:
        if code not in practice_map:
            failures.append(f"unknown Science Practice {code!r}")

    if exam_task is not None:
        task = data["exam_tasks"].get(exam_task)
        if task is None:
            failures.append(f"unknown exam task {exam_task!r}")
        else:
            known_practices = [
                practice_map[code] for code in science_practices if code in practice_map
            ]
            families = {item["family"] for item in known_practices}
            if not known_practices:
                failures.append("an exam task requires at least one Science Practice")
            disallowed = families - set(task["allowed_practice_families"])
            if disallowed:
                failures.append(
                    f"{exam_task} does not assess Practice family/families: "
                    + ", ".join(sorted(disallowed))
                )
            if full_task:
                missing = set(task["required_practice_families"]) - families
                if missing:
                    failures.append(
                        f"{exam_task} is missing required Practice family/families: "
                        + ", ".join(sorted(missing))
                    )
            expected_sources = task["source_count"]
            if source_count is not None and source_count <= 0:
                failures.append("source_count must be a positive integer")
            elif expected_sources is None and source_count is not None:
                failures.append(f"{exam_task} does not allow source_count")
            elif full_task and expected_sources is not None and source_count is None:
                failures.append(f"{exam_task} requires source_count={expected_sources}")
            elif full_task and source_count != expected_sources:
                failures.append(
                    f"{exam_task} requires source_count={expected_sources}, got {source_count}"
                )
            elif (
                not full_task
                and source_count is not None
                and expected_sources is not None
                and source_count > expected_sources
            ):
                failures.append(
                    f"{exam_task} allows at most source_count={expected_sources}, "
                    f"got {source_count}"
                )
    elif source_count is not None:
        failures.append("--source-count requires --exam-task")

    for name in scope_flags:
        flag = data["scope_flags"].get(name)
        if flag is None:
            failures.append(f"unknown scope flag {name!r}")
            continue
        if topic_numbers.isdisjoint(flag["topics"]):
            failures.append(
                f"scope flag {name!r} does not apply to mapped Topic(s)"
            )
        if assessed_topic or exam_task is not None:
            failures.append(flag["reason"])
    return failures


def _base_evidence(overall_status: str) -> dict[str, Any]:
    return {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "validator": EVIDENCE_VALIDATOR,
        "course": "psychology",
        "overall_status": overall_status,
        "results": [],
    }


def _error_evidence(message: str) -> dict[str, Any]:
    payload = _base_evidence("error")
    payload["error"] = message
    return payload


def validate_request(
    citations: Iterable[str],
    *,
    science_practices: Iterable[str] = (),
    exam_task: str | None = None,
    source_count: int | None = None,
    scope_flags: Iterable[str] = (),
    assessed_topic: bool = False,
    full_task: bool = False,
    practice_only: bool = False,
    framework_path: Path = DEFAULT_FRAMEWORK_PATH,
    boundaries_path: Path = DEFAULT_BOUNDARIES_PATH,
) -> tuple[int, dict[str, Any]]:
    citations = list(citations)
    science_practices = list(science_practices)
    scope_flags = list(scope_flags)
    validation_mode = "practice-only" if practice_only else "topic"
    task_scope = ("full" if full_task else "partial") if exam_task else None

    def add_mode_metadata(payload: dict[str, Any], topic_status: str) -> None:
        payload["validation_mode"] = validation_mode
        payload["topic_status"] = topic_status

    if practice_only:
        conflicts = []
        if citations:
            conflicts.append("Topic citation")
        if assessed_topic:
            conflicts.append("--assessed-topic")
        if full_task:
            conflicts.append("--full-task")
        if scope_flags:
            conflicts.append("--scope-flag")
        if conflicts:
            payload = _error_evidence(
                "--practice-only cannot be combined with " + ", ".join(conflicts)
            )
            add_mode_metadata(payload, "not-established")
            return 2, payload
        if not science_practices:
            payload = _error_evidence(
                "--practice-only requires at least one --science-practice"
            )
            add_mode_metadata(payload, "not-established")
            return 2, payload
        code, payload = 0, _base_evidence("pass")
        topic_numbers: list[str] = []
        add_mode_metadata(payload, "not-established")
    else:
        if full_task and exam_task is None:
            payload = _error_evidence("--full-task requires --exam-task")
            add_mode_metadata(payload, "not-established")
            return 2, payload
        code, payload = validate_citations(citations, framework_path=framework_path)
        passed = [row for row in payload["results"] if row["status"] == "pass"]
        add_mode_metadata(payload, "validated" if passed else "not-established")
        if code == 2 or not passed:
            return code, payload
        topic_numbers = [
            row["citation"].split(", Topic ", 1)[1].split(" ", 1)[0]
            for row in passed
        ]

    assessed_topic = assessed_topic or (exam_task is not None and not practice_only)
    if exam_task is not None:
        for row in payload["results"]:
            if row["status"] == "pass":
                row["topic_exam_scope"] = "exam-oriented"

    try:
        failures = validate_boundaries(
            topic_numbers=topic_numbers,
            science_practices=science_practices,
            exam_task=exam_task,
            source_count=source_count,
            scope_flags=scope_flags,
            assessed_topic=assessed_topic,
            full_task=full_task,
            boundaries_path=boundaries_path,
        )
    except BoundaryDataError as exc:
        error_payload = _error_evidence(str(exc))
        add_mode_metadata(
            error_payload, "not-established" if practice_only else "validated"
        )
        return 2, error_payload

    payload["content_boundary"] = {
        "status": "fail" if failures else "pass",
        "failures": failures,
        "assessed_topic": assessed_topic,
        "exam_task": exam_task,
        "science_practices": science_practices,
        "scope_flags": scope_flags,
        "task_scope": task_scope,
        "source_count": source_count,
    }
    if failures:
        payload["overall_status"] = "fail"
        code = 1
    return code, payload


def _print_human(payload: dict[str, Any]) -> None:
    if payload["overall_status"] == "error":
        print(f"ERROR — {payload['error']}", file=sys.stderr)
        return
    if payload.get("validation_mode") == "practice-only" and payload["overall_status"] == "pass":
        print("OK — Science Practice validated; Topic not established")
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


def run_self_check(
    framework_path: Path = DEFAULT_FRAMEWORK_PATH,
    boundaries_path: Path = DEFAULT_BOUNDARIES_PATH,
) -> tuple[int, dict[str, Any]]:
    try:
        checks = 0

        def expect(
            label: str,
            expected_code: int,
            citations: Iterable[str] = (),
            **kwargs: Any,
        ) -> dict[str, Any]:
            nonlocal checks
            checks += 1
            code, payload = validate_request(
                citations,
                framework_path=framework_path,
                boundaries_path=boundaries_path,
                **kwargs,
            )
            if code != expected_code:
                raise AssertionError(
                    f"{label}: exit {code}; expected {expected_code}: "
                    + "; ".join(payload.get("content_boundary", {}).get("failures", []))
                )
            return payload

        topics = parse_framework(framework_path)
        errors = framework_data_errors(topics)
        boundaries = load_boundaries(boundaries_path)
        if errors:
            raise AssertionError("; ".join(errors))
        if len(topics) != 35:
            raise AssertionError(f"parsed {len(topics)} Topics; expected 35")
        topic_codes = {topic.topic_num for topic in topics}
        invalid_flag_topics = {
            code
            for flag in boundaries["scope_flags"].values()
            for code in flag["topics"]
            if code not in topic_codes
        }
        if invalid_flag_topics:
            raise AssertionError(
                "scope flags reference unknown Topic(s): "
                + ", ".join(sorted(invalid_flag_topics))
            )
        good = "Unit 3, Topic 3.7 — Classical Conditioning"
        payload = expect("current Topic", 0, [good])
        if payload["overall_status"] != "pass":
            raise AssertionError("current Topic did not validate")
        old = "Unit 4, Topic 4.1 — Learning"
        old_payload = expect("legacy Topic", 1, [old])
        candidates = old_payload["results"][0]["candidates"]
        if not candidates or any(find_match(topics, item) is None for item in candidates):
            raise AssertionError("a suggested citation is not directly valid")

        partial_aaq = expect(
            "partial AAQ",
            0,
            [good],
            science_practices=["2.D"],
            exam_task="article-analysis-question",
        )
        if (
            partial_aaq["results"][0]["topic_exam_scope"] != "exam-oriented"
            or not partial_aaq["content_boundary"]["assessed_topic"]
            or partial_aaq["content_boundary"]["task_scope"] != "partial"
        ):
            raise AssertionError("exam task did not produce assessed/exam-oriented metadata")
        expect(
            "partial AAQ disallowed Practice",
            1,
            [good],
            science_practices=["1.A"],
            exam_task="article-analysis-question",
        )
        expect(
            "full AAQ",
            0,
            [good],
            science_practices=["2.D", "3.C", "4.B"],
            exam_task="article-analysis-question",
            source_count=1,
            full_task=True,
        )
        expect(
            "full AAQ missing Practice family",
            1,
            [good],
            science_practices=["2.D", "3.C"],
            exam_task="article-analysis-question",
            source_count=1,
            full_task=True,
        )
        expect(
            "full AAQ missing source count",
            1,
            [good],
            science_practices=["2.D", "3.C", "4.B"],
            exam_task="article-analysis-question",
            full_task=True,
        )
        expect(
            "partial EBQ",
            0,
            [good],
            science_practices=["4.B"],
            exam_task="evidence-based-question",
            source_count=1,
        )
        expect(
            "full EBQ",
            0,
            [good],
            science_practices=["1.A", "4.B"],
            exam_task="evidence-based-question",
            source_count=3,
            full_task=True,
        )
        expect(
            "full EBQ wrong source count",
            1,
            [good],
            science_practices=["1.A", "4.B"],
            exam_task="evidence-based-question",
            source_count=2,
            full_task=True,
        )
        practice_only = expect(
            "practice-only",
            0,
            science_practices=["2.B"],
            practice_only=True,
        )
        if (
            practice_only["validation_mode"] != "practice-only"
            or practice_only["topic_status"] != "not-established"
            or practice_only["results"]
        ):
            raise AssertionError("practice-only mode established a Topic")
        practice_component = expect(
            "practice-only partial AAQ",
            0,
            science_practices=["2.D"],
            exam_task="article-analysis-question",
            practice_only=True,
        )
        if practice_component["content_boundary"]["assessed_topic"]:
            raise AssertionError("practice-only exam task assessed a nonexistent Topic")
        expect("practice-only missing Practice", 2, practice_only=True)
        expect(
            "practice-only with Topic",
            2,
            [good],
            science_practices=["2.B"],
            practice_only=True,
        )
        expect(
            "practice-only with scope flag",
            2,
            science_practices=["2.B"],
            scope_flags=["maslow-hierarchy-of-needs"],
            practice_only=True,
        )
        expect("ordinary mode without citation", 2)
        expect("full task without exam task", 2, [good], full_task=True)
        expect(
            "MCQ source count",
            1,
            [good],
            science_practices=["1.A"],
            exam_task="multiple-choice",
            source_count=1,
        )
        maslow = "Unit 4, Topic 4.6 — Motivation"
        expect(
            "Maslow assessed scope claim",
            1,
            [maslow],
            assessed_topic=True,
            scope_flags=["maslow-hierarchy-of-needs"],
        )
        legacy_option = "--ap-" + "oriented"
        _, unknown = build_parser().parse_known_args([legacy_option])
        if unknown != [legacy_option]:
            raise AssertionError("deleted legacy option is still accepted")
    except (AssertionError, BoundaryDataError, FrameworkParseError, OSError) as exc:
        return 2, _error_evidence(f"self-check failed: {exc}")
    payload = _base_evidence("pass")
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
    parser.add_argument("--assessed-topic", action="store_true")
    parser.add_argument(
        "--exam-task",
        choices=[
            "multiple-choice",
            "article-analysis-question",
            "evidence-based-question",
        ],
    )
    parser.add_argument("--full-task", action="store_true")
    parser.add_argument("--practice-only", action="store_true")
    parser.add_argument("--source-count", type=int)
    parser.add_argument(
        "--science-practice", dest="science_practices", action="append", default=[]
    )
    parser.add_argument("--scope-flag", dest="scope_flags", action="append", default=[])
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--evidence-json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.self_check:
        code, payload = run_self_check(args.framework, args.boundaries)
    else:
        code, payload = validate_request(
            args.citation,
            science_practices=args.science_practices,
            exam_task=args.exam_task,
            source_count=args.source_count,
            scope_flags=args.scope_flags,
            assessed_topic=args.assessed_topic,
            full_task=args.full_task,
            practice_only=args.practice_only,
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
