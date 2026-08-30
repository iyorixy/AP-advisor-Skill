#!/usr/bin/env python3
"""Validate AP Biology internal Topic mappings and declared assessment boundaries."""

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


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FRAMEWORK_PATH = SKILL_ROOT / "references" / "ap-biology-framework.md"
DEFAULT_BOUNDARIES_PATH = SKILL_ROOT / "references" / "ap-biology-boundaries.json"
EVIDENCE_SCHEMA_VERSION = 1
EVIDENCE_VALIDATOR = "ap-biology-topic-v1"
UNIT_RE = re.compile(r"^- Unit ([1-8]) — (.+)$")
TOPIC_RE = re.compile(r"^  - (\d+\.\d+) (.+)$")


class FrameworkParseError(ValueError):
    pass


class BoundaryDataError(ValueError):
    pass


@dataclass(frozen=True)
class Topic:
    unit_num: str
    unit_title: str
    topic_num: str
    title: str

    @property
    def citation(self) -> str:
        return f"Unit {self.unit_num}, Topic {self.topic_num} — {self.title}"


def _nfkc(value: str) -> str:
    return unicodedata.normalize("NFKC", value)


def parse_framework(path: Path = DEFAULT_FRAMEWORK_PATH) -> list[Topic]:
    topics: list[Topic] = []
    current_unit: tuple[str, str] | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        unit_match = UNIT_RE.match(raw_line)
        if unit_match:
            current_unit = unit_match.groups()
            continue
        topic_match = TOPIC_RE.match(raw_line)
        if topic_match:
            if current_unit is None:
                raise FrameworkParseError("Topic appears before a Unit")
            topic_num, title = topic_match.groups()
            topics.append(Topic(*current_unit, topic_num, title))
    if not topics:
        raise FrameworkParseError("no Topics parsed")
    return topics


def framework_data_errors(topics: list[Topic]) -> list[str]:
    errors: list[str] = []
    codes = [topic.topic_num for topic in topics]
    citations = [topic.citation for topic in topics]
    if len(codes) != len(set(codes)):
        errors.append("duplicate Topic code")
    if len(citations) != len(set(citations)):
        errors.append("duplicate Topic citation")
    for topic in topics:
        if topic.topic_num.split(".", 1)[0] != topic.unit_num:
            errors.append(
                f"Topic {topic.topic_num} is nested under Unit {topic.unit_num}"
            )
    return errors


def find_match(topics: list[Topic], query: str) -> Topic | None:
    normalized = _nfkc(query)
    return next(
        (topic for topic in topics if _nfkc(topic.citation) == normalized),
        None,
    )


def closest_candidates(
    topics: list[Topic], query: str, *, limit: int = 3
) -> list[str]:
    by_normalized = {_nfkc(topic.citation): topic.citation for topic in topics}
    matches = difflib.get_close_matches(
        _nfkc(query), list(by_normalized), n=limit, cutoff=0.35
    )
    return [by_normalized[match] for match in matches]


def load_boundaries(path: Path = DEFAULT_BOUNDARIES_PATH) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BoundaryDataError(f"could not load boundaries: {exc}") from exc
    if data.get("schema_version") != 1:
        raise BoundaryDataError("unsupported boundary schema_version")

    sources = data.get("sources")
    if not isinstance(sources, list) or not sources:
        raise BoundaryDataError("sources must be a non-empty array")
    source_ids = {
        item.get("id")
        for item in sources
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    if len(source_ids) != len(sources):
        raise BoundaryDataError("sources contain an invalid or duplicate id")

    practices = data.get("science_practices")
    if not isinstance(practices, list) or not practices:
        raise BoundaryDataError("science_practices must be a non-empty array")
    practice_codes: set[str] = set()
    practice_families: set[str] = set()
    for item in practices:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("code"), str)
            or not isinstance(item.get("family"), str)
            or not isinstance(item.get("name"), str)
            or item["code"] in practice_codes
        ):
            raise BoundaryDataError("science_practices contains an invalid record")
        practice_codes.add(item["code"])
        practice_families.add(item["family"])

    tasks = data.get("exam_tasks")
    if not isinstance(tasks, dict) or not tasks:
        raise BoundaryDataError("exam_tasks must be a non-empty object")
    for name, task in tasks.items():
        if (
            not isinstance(name, str)
            or not isinstance(task, dict)
            or task.get("source") not in source_ids
            or not isinstance(task.get("supports_full_task"), bool)
        ):
            raise BoundaryDataError("exam_tasks contains an invalid record")
        allowed = task.get("allowed_practice_families")
        groups = task.get("required_practice_groups")
        if (
            not isinstance(allowed, list)
            or not allowed
            or len(allowed) != len(set(allowed))
            or not set(allowed) <= practice_families
            or not isinstance(groups, list)
        ):
            raise BoundaryDataError(f"exam task {name!r} has invalid Practice data")
        for group in groups:
            if (
                not isinstance(group, list)
                or not group
                or len(group) != len(set(group))
                or not set(group) <= set(allowed)
            ):
                raise BoundaryDataError(
                    f"exam task {name!r} has an invalid required Practice group"
                )

    flags = data.get("scope_flags")
    if not isinstance(flags, dict):
        raise BoundaryDataError("scope_flags must be an object")
    for name, flag in flags.items():
        values = flag.get("in_scope_values", []) if isinstance(flag, dict) else None
        if (
            not isinstance(name, str)
            or not isinstance(flag, dict)
            or not isinstance(flag.get("topics"), list)
            or not flag["topics"]
            or not all(isinstance(code, str) for code in flag["topics"])
            or not isinstance(flag.get("reason"), str)
            or flag.get("source") not in source_ids
            or not isinstance(values, list)
            or not all(isinstance(value, str) for value in values)
        ):
            raise BoundaryDataError("scope_flags contains an invalid record")

    corrections = data.get("corrections")
    if not isinstance(corrections, list) or any(
        not isinstance(item, dict)
        or item.get("source") not in source_ids
        or not isinstance(item.get("rule"), str)
        for item in corrections
    ):
        raise BoundaryDataError("corrections contains an invalid record")
    if not isinstance(data.get("legacy_markers"), list) or not data["legacy_markers"]:
        raise BoundaryDataError("legacy_markers must be a non-empty array")
    return data


def _base_evidence(overall_status: str) -> dict[str, Any]:
    return {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "validator": EVIDENCE_VALIDATOR,
        "course": "biology",
        "overall_status": overall_status,
        "results": [],
    }


def _error_evidence(message: str) -> dict[str, Any]:
    payload = _base_evidence("error")
    payload["error"] = message
    return payload


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
    if errors:
        return 2, _error_evidence("invalid framework: " + "; ".join(errors))

    failed = False
    results: list[dict[str, Any]] = []
    for query in citations:
        match = find_match(topics, query)
        if match is None:
            failed = True
            results.append(
                {
                    "input": query,
                    "status": "fail",
                    "message": f"no NFKC exact match for: {query}",
                    "candidates": closest_candidates(topics, query),
                }
            )
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
    scope_flags: Iterable[str],
    assessed_topic: bool,
    full_task: bool,
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
            known = [
                practice_map[code]
                for code in science_practices
                if code in practice_map
            ]
            families = {item["family"] for item in known}
            if not known:
                failures.append("an exam task requires at least one Science Practice")
            disallowed = families - set(task["allowed_practice_families"])
            if disallowed:
                failures.append(
                    f"{exam_task} does not assess Practice family/families: "
                    + ", ".join(sorted(disallowed))
                )
            if full_task and not task["supports_full_task"]:
                failures.append(f"{exam_task} cannot be validated as a full task")
            elif full_task:
                for group in task["required_practice_groups"]:
                    if families.isdisjoint(group):
                        failures.append(
                            f"{exam_task} is missing a Practice from required group: "
                            + " or ".join(group)
                        )

    for name in scope_flags:
        flag = data["scope_flags"].get(name)
        if flag is None:
            failures.append(f"unknown scope flag {name!r}")
            continue
        if topic_numbers.isdisjoint(flag["topics"]):
            failures.append(f"scope flag {name!r} does not apply to mapped Topic(s)")
        if assessed_topic or exam_task is not None:
            failures.append(flag["reason"])
    return failures


def validate_request(
    citations: Iterable[str],
    *,
    science_practices: Iterable[str] = (),
    exam_task: str | None = None,
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
        "task_scope": ("full" if full_task else "partial") if exam_task else None,
    }
    if failures:
        payload["overall_status"] = "fail"
        code = 1
    return code, payload


def _print_human(payload: dict[str, Any]) -> None:
    if payload["overall_status"] == "error":
        print(f"ERROR — {payload['error']}", file=sys.stderr)
        return
    if (
        payload.get("validation_mode") == "practice-only"
        and payload["overall_status"] == "pass"
    ):
        print("OK — Science Practice validated; Topic not established")
    for result in payload["results"]:
        if result["status"] == "pass":
            print(f"OK — matched: {result['citation']}")
            print(f"META — topic_exam_scope: {result['topic_exam_scope']}")
        else:
            print(f"FAIL — {result['message']}")
            for candidate in result.get("candidates", []):
                print(f"  - {candidate}")
    for failure in payload.get("content_boundary", {}).get("failures", []):
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
                failures = payload.get("content_boundary", {}).get("failures", [])
                raise AssertionError(
                    f"{label}: exit {code}; expected {expected_code}: "
                    + "; ".join(failures)
                )
            return payload

        topics = parse_framework(framework_path)
        errors = framework_data_errors(topics)
        boundaries = load_boundaries(boundaries_path)
        if errors:
            raise AssertionError("; ".join(errors))
        if len(topics) != 60:
            raise AssertionError(f"parsed {len(topics)} Topics; expected 60")
        if len(boundaries["science_practices"]) != 22:
            raise AssertionError("expected 22 Science Practices")
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

        good = "Unit 7, Topic 7.5 — Hardy–Weinberg Equilibrium"
        payload = expect("current Topic", 0, [good])
        if payload["overall_status"] != "pass":
            raise AssertionError("current Topic did not validate")
        old = "Unit 1, Topic 1.4 — Properties of Biological Macromolecules"
        old_payload = expect("legacy Topic", 1, [old])
        candidates = old_payload["results"][0]["candidates"]
        if not candidates or any(find_match(topics, item) is None for item in candidates):
            raise AssertionError("a suggested citation is not directly valid")

        expect(
            "partial FRQ 2",
            0,
            [good],
            science_practices=["4.A"],
            exam_task="free-response-2",
        )
        expect(
            "full FRQ 2",
            0,
            [good],
            science_practices=["1.B", "4.A", "5.A", "6.E"],
            exam_task="free-response-2",
            full_task=True,
        )
        expect(
            "full FRQ 2 missing flexible group",
            1,
            [good],
            science_practices=["1.B", "4.A", "6.E"],
            exam_task="free-response-2",
            full_task=True,
        )
        expect(
            "FRQ 5 disallowed Practice",
            1,
            [good],
            science_practices=["5.A"],
            exam_task="free-response-5",
        )
        expect(
            "full FRQ 5",
            0,
            [good],
            science_practices=["1.C", "2.B"],
            exam_task="free-response-5",
            full_task=True,
        )
        expect(
            "full MCQ is invalid",
            1,
            [good],
            science_practices=["1.B"],
            exam_task="multiple-choice",
            full_task=True,
        )

        practice_only = expect(
            "practice-only",
            0,
            science_practices=["5.C"],
            practice_only=True,
        )
        if practice_only["topic_status"] != "not-established":
            raise AssertionError("practice-only mode established a Topic")
        practice_component = expect(
            "practice-only partial FRQ 6",
            0,
            science_practices=["5.D"],
            exam_task="free-response-6",
            practice_only=True,
        )
        if practice_component["content_boundary"]["assessed_topic"]:
            raise AssertionError("practice-only task assessed a nonexistent Topic")
        expect("practice-only missing Practice", 2, practice_only=True)
        expect(
            "practice-only with Topic",
            2,
            [good],
            science_practices=["5.C"],
            practice_only=True,
        )
        expect("ordinary mode without citation", 2)
        expect("full task without exam task", 2, [good], full_task=True)
        expect(
            "unknown Practice",
            1,
            [good],
            science_practices=["7.A"],
        )

        energy = "Unit 3, Topic 3.3 — Cellular Energy"
        expect(
            "instructional exclusion",
            0,
            [energy],
            scope_flags=["gibbs-free-energy-equation"],
        )
        expect(
            "assessed exclusion",
            1,
            [energy],
            assessed_topic=True,
            scope_flags=["gibbs-free-energy-equation"],
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
        "science_practice_count": len(boundaries["science_practices"]),
        "scope_flag_count": len(boundaries["scope_flags"]),
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
            "free-response-1",
            "free-response-2",
            "free-response-3",
            "free-response-4",
            "free-response-5",
            "free-response-6",
        ],
    )
    parser.add_argument("--full-task", action="store_true")
    parser.add_argument("--practice-only", action="store_true")
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
            print(
                "OK — self-check parsed "
                f"{payload['self_check']['topic_count']} Topics"
            )
    return code


def _configure_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="strict")


if __name__ == "__main__":
    _configure_utf8()
    raise SystemExit(main())
