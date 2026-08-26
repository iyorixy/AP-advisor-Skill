#!/usr/bin/env python3
"""Validate and optionally run AP Advisor behavioral evaluation cases.

The default mode validates ``evals/cases.jsonl`` only. It does not invoke
Codex, access the network, or write result files. Live model execution is
available only with the explicit ``--run`` flag. Live runs use a temporary
read-only repository and ignore the user's ``config.toml`` unless
``--use-user-config`` is supplied.

Exit codes:
    0: corpus is valid and (when run) every automated assertion passed
    1: at least one live behavioral assertion failed
    2: invalid corpus, configuration problem, or runner failure
"""

from __future__ import annotations

import argparse
import datetime as dt
import functools
import html
import json
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from collections import Counter
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CORPUS = REPO_ROOT / "evals" / "cases.jsonl"
OUTPUT_SCHEMA = REPO_ROOT / "references" / "output-schema.json"
ERROR_SCHEMA = REPO_ROOT / "references" / "machine-error-schema.json"
VALID_INVOCATIONS = {"explicit", "implicit"}
VALID_OUTPUT_KINDS = {"any", "text", "json_error", "json_success"}
VALID_CATEGORIES = {
    "advisor",
    "machine-output",
    "negative-routing",
    "review",
    "scope",
}
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
SUPPORTED_SCHEMA_KEYWORDS = {
    "$schema",
    "additionalProperties",
    "allOf",
    "const",
    "description",
    "enum",
    "if",
    "items",
    "minItems",
    "minLength",
    "pattern",
    "properties",
    "required",
    "then",
    "title",
    "type",
}
VALIDATOR_COMMAND_HINT = re.compile(
    r"(?:^|(?:bash|sh|zsh)\s+-lc\s+|(?:powershell|pwsh)(?:\.exe)?[^\r\n]*?"
    r"-command\s+|cmd(?:\.exe)?\s+/c\s+|[;&|]\s*)"
    r"(?:&\s*)?(?:\"[^\"\r\n]*python(?:3(?:\.\d+)?)?(?:\.exe)?\"|"
    r"'[^'\r\n]*python(?:3(?:\.\d+)?)?(?:\.exe)?'|"
    r"[^\s;&|]*python(?:3(?:\.\d+)?)?(?:\.exe)?|py(?:\.exe)?\s+-3(?:\.\d+)?)"
    r"[^;&|\r\n]*validate_topic_code\.py(?:\s|$|[\"'])",
    re.IGNORECASE,
)
VALID_COURSES = {"precalculus", "calc-ab", "calc-bc"}
VALID_CONTENT_TYPES = {"explanation", "practice_problem", "worked_example"}
VALID_CONTENT_FIELDS = {
    "principle",
    "real_world_application",
    "problem_statement",
    "final_answer",
    "solution",
    "common_mistake",
}
VALID_DIFFICULTIES = {"foundational", "standard", "challenge"}
VALID_STYLES = {"instructional", "ap-oriented"}
VALID_TOPIC_SCOPES = {"assessed", "not-assessed"}
JSON_CONTRACT_FIELDS = {
    "course",
    "unit",
    "topic",
    "topic_exam_scope",
    "type",
    "difficulty",
    "style",
    "supporting_topics",
}
VALIDATOR_SCHEMA_VERSION = 1
VALIDATOR_NAME = "ap-advisor-topic-code"
REQUIRED_LAUNCHER_FAMILIES = {"python3", "python", "py-3"}
CATALOG_TOPIC_REFERENCE = re.compile(
    r"(?<![A-Za-z0-9])topic[\W_]+\d+\.\d+(?!\d)(?!\.\d)", re.IGNORECASE
)
CATALOG_FULL_CITATION_REFERENCE = re.compile(
    r"(?<![A-Za-z0-9])unit[\W_]+\d+[\W_]+topic[\W_]+\d+\.\d+"
    r"(?!\d)(?!\.\d)",
    re.IGNORECASE,
)
NON_EXECUTION_COMMANDS = {
    "cat",
    "findstr",
    "get-content",
    "grep",
    "head",
    "less",
    "more",
    "rg",
    "select-string",
    "tail",
    "type",
}
SAFE_ENV_ASSIGNMENTS = {
    "PYTHONIOENCODING=utf-8",
    "PYTHONIOENCODING=UTF-8",
    "PYTHONUTF8=1",
}
TEXT_EVIDENCE_MANUAL_CHECK = (
    "Any free-form course, style, and topic-scope claims are consistent with "
    "the validator evidence, and each citation is visibly rendered to the user."
)
RAW_HTML_MARKUP = re.compile(
    r"<!--|</?[A-Za-z][A-Za-z0-9-]*(?=[\s/>])", re.IGNORECASE
)
MARKDOWN_REFERENCE_DEFINITION = re.compile(
    r"(?m)^[ ]{0,3}\[[^\]\r\n]+\]:[ \t]*\S"
)
MARKDOWN_INLINE_LINK_MARKER = re.compile(r"\]\(")


class RunnerError(RuntimeError):
    """A corpus, configuration, or execution failure (exit code 2)."""


class DuplicateJsonKeyError(ValueError):
    """Raised when a machine-readable object repeats a JSON member name."""


def _strict_json_loads(source: str) -> Any:
    """Decode JSON while rejecting ambiguous duplicate object keys."""

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise DuplicateJsonKeyError(f"duplicate JSON key {key!r}")
            value[key] = item
        return value

    return json.loads(source, object_pairs_hook=reject_duplicates)


@dataclass(frozen=True)
class EvalCase:
    """One validated behavioral case from the JSONL corpus."""

    id: str
    category: str
    invocation: str
    prompt: str
    expect: dict[str, Any]
    manual_checks: tuple[str, ...]


@dataclass(frozen=True)
class ValidatorInvocation:
    """A safely parsed invocation of the bundled citation validator."""

    launcher: str
    launcher_executable: str
    launcher_is_canonical: bool
    course: str
    ap_oriented: bool
    citations: tuple[str, ...]


@dataclass(frozen=True)
class ValidatorRun:
    """Evidence extracted from one validator command lifecycle."""

    item_id: str | None
    command: str
    completed: bool
    status: str | None
    exit_code: int | None
    invocation: ValidatorInvocation | None
    evidence: dict[str, Any] | None
    failures: tuple[str, ...]
    fatal: bool
    prestart_failure: bool = False

    @property
    def accepted(self) -> bool:
        return (
            self.completed
            and not self.fatal
            and self.exit_code == 0
            and self.evidence is not None
            and self.evidence.get("overall_status") == "pass"
        )

    def as_dict(self) -> dict[str, Any]:
        invocation = None
        if self.invocation is not None:
            invocation = {
                "launcher": self.invocation.launcher,
                "launcher_executable": self.invocation.launcher_executable,
                "launcher_is_canonical": self.invocation.launcher_is_canonical,
                "course": self.invocation.course,
                "ap_oriented": self.invocation.ap_oriented,
                "citations": list(self.invocation.citations),
            }
        return {
            "item_id": self.item_id,
            "command": self.command,
            "completed": self.completed,
            "status": self.status,
            "exit_code": self.exit_code,
            "invocation": invocation,
            "evidence": self.evidence,
            "failures": list(self.failures),
            "fatal": self.fatal,
            "prestart_failure": self.prestart_failure,
            "accepted": self.accepted,
        }


@dataclass(frozen=True)
class ValidatorObservation:
    """All validator commands observed in one Codex JSONL event stream."""

    runs: tuple[ValidatorRun, ...]

    @property
    def observed(self) -> bool:
        return bool(self.runs)

    @property
    def accepted_runs(self) -> tuple[ValidatorRun, ...]:
        return tuple(run for run in self.runs if run.accepted)

    @property
    def fatal_failures(self) -> tuple[str, ...]:
        failures: list[str] = []
        for index, run in enumerate(self.runs, start=1):
            if run.fatal:
                failures.extend(
                    f"validator run {index}: {failure}" for failure in run.failures
                )
        return tuple(failures)

    @property
    def only_verified_prestart_failures(self) -> bool:
        return bool(self.runs) and all(run.prestart_failure for run in self.runs)

    @property
    def exhausted_launcher_families(self) -> bool:
        if not self.only_verified_prestart_failures:
            return False
        observed = {
            run.invocation.launcher
            for run in self.runs
            if run.invocation is not None and run.invocation.launcher_is_canonical
        }
        return REQUIRED_LAUNCHER_FAMILIES <= observed

    def as_dict(self) -> dict[str, Any]:
        return {
            "observed": self.observed,
            "accepted_run_count": len(self.accepted_runs),
            "only_verified_prestart_failures": self.only_verified_prestart_failures,
            "exhausted_launcher_families": self.exhausted_launcher_families,
            "fatal_failures": list(self.fatal_failures),
            "runs": [run.as_dict() for run in self.runs],
        }


def _require_string_list(value: Any, field: str, case_id: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise RunnerError(f"case {case_id!r}: {field} must be a list of non-empty strings")
    return value


def _validate_json_contract(value: Any, case_id: str) -> dict[str, Any]:
    """Validate fixed JSON fields copied from one behavior-case prompt."""

    if not isinstance(value, dict):
        raise RunnerError(
            f"case {case_id!r}: json_contract must be an object for json_success"
        )
    missing = sorted(JSON_CONTRACT_FIELDS - value.keys())
    extra = sorted(value.keys() - JSON_CONTRACT_FIELDS)
    if missing or extra:
        detail = []
        if missing:
            detail.append("missing " + ", ".join(missing))
        if extra:
            detail.append("unknown " + ", ".join(extra))
        raise RunnerError(
            f"case {case_id!r}: invalid json_contract ({'; '.join(detail)})"
        )
    enum_fields = {
        "course": VALID_COURSES,
        "topic_exam_scope": VALID_TOPIC_SCOPES,
        "type": VALID_CONTENT_TYPES,
        "difficulty": VALID_DIFFICULTIES,
        "style": VALID_STYLES,
    }
    for field, allowed in enum_fields.items():
        field_value = value[field]
        if not isinstance(field_value, str) or field_value not in allowed:
            raise RunnerError(
                f"case {case_id!r}: json_contract.{field} is invalid"
            )
    if not isinstance(value["unit"], str) or re.fullmatch(
        r"Unit (?:[1-9]|10)", value["unit"]
    ) is None:
        raise RunnerError(f"case {case_id!r}: json_contract.unit is invalid")
    if not isinstance(value["topic"], str) or re.fullmatch(
        r"[1-9][0-9]*\.[1-9][0-9]* .+", value["topic"]
    ) is None:
        raise RunnerError(f"case {case_id!r}: json_contract.topic is invalid")

    supporting = value["supporting_topics"]
    if not isinstance(supporting, list):
        raise RunnerError(
            f"case {case_id!r}: json_contract.supporting_topics must be an array"
        )
    seen: set[tuple[str, str, str]] = set()
    for index, item in enumerate(supporting):
        if not isinstance(item, dict) or set(item) != {
            "unit",
            "topic",
            "topic_exam_scope",
        }:
            raise RunnerError(
                f"case {case_id!r}: json_contract.supporting_topics[{index}] "
                "must contain exactly unit, topic, and topic_exam_scope"
            )
        if not isinstance(item["unit"], str) or re.fullmatch(
            r"Unit (?:[1-9]|10)", item["unit"]
        ) is None:
            raise RunnerError(
                f"case {case_id!r}: json_contract.supporting_topics[{index}].unit "
                "is invalid"
            )
        if not isinstance(item["topic"], str) or re.fullmatch(
            r"[1-9][0-9]*\.[1-9][0-9]* .+", item["topic"]
        ) is None:
            raise RunnerError(
                f"case {case_id!r}: json_contract.supporting_topics[{index}].topic "
                "is invalid"
            )
        scope = item["topic_exam_scope"]
        if not isinstance(scope, str) or scope not in VALID_TOPIC_SCOPES:
            raise RunnerError(
                f"case {case_id!r}: json_contract.supporting_topics[{index}]."
                "topic_exam_scope is invalid"
            )
        key = (item["unit"], item["topic"], scope)
        if key in seen:
            raise RunnerError(
                f"case {case_id!r}: json_contract has a duplicate supporting topic"
            )
        seen.add(key)

    primary_key = (value["unit"], value["topic"], value["topic_exam_scope"])
    if primary_key in seen:
        raise RunnerError(
            f"case {case_id!r}: primary topic cannot repeat as a supporting topic"
        )
    if value["topic_exam_scope"] == "not-assessed" and value["style"] != "instructional":
        raise RunnerError(
            f"case {case_id!r}: not-assessed json_contract requires instructional style"
        )
    if value["style"] == "ap-oriented" and any(
        item["topic_exam_scope"] != "assessed" for item in supporting
    ):
        raise RunnerError(
            f"case {case_id!r}: ap-oriented json_contract requires assessed supporting topics"
        )
    return value


def validate_case(raw: Any, line_number: int) -> EvalCase:
    """Validate and normalize one decoded corpus object."""

    if not isinstance(raw, dict):
        raise RunnerError(f"line {line_number}: each JSONL record must be an object")

    required = {"id", "category", "invocation", "prompt", "expect", "manual_checks"}
    missing = sorted(required - raw.keys())
    unknown = sorted(raw.keys() - required)
    if missing:
        raise RunnerError(f"line {line_number}: missing field(s): {', '.join(missing)}")
    if unknown:
        raise RunnerError(f"line {line_number}: unknown field(s): {', '.join(unknown)}")

    case_id = raw["id"]
    if not isinstance(case_id, str) or not ID_PATTERN.fullmatch(case_id):
        raise RunnerError(
            f"line {line_number}: id must match {ID_PATTERN.pattern!r}"
        )

    category = raw["category"]
    if not isinstance(category, str) or category not in VALID_CATEGORIES:
        raise RunnerError(
            f"case {case_id!r}: category must be one of {sorted(VALID_CATEGORIES)}"
        )

    invocation = raw["invocation"]
    if not isinstance(invocation, str) or invocation not in VALID_INVOCATIONS:
        raise RunnerError(
            f"case {case_id!r}: invocation must be 'explicit' or 'implicit'"
        )

    prompt = raw["prompt"]
    if not isinstance(prompt, str) or not prompt.strip():
        raise RunnerError(f"case {case_id!r}: prompt must be a non-empty string")

    expect = raw["expect"]
    if not isinstance(expect, dict):
        raise RunnerError(f"case {case_id!r}: expect must be an object")
    allowed_expect = {
        "output_kind",
        "validator_call",
        "validator_course",
        "validator_ap_oriented",
        "json_contract",
        "forbidden_content_fields",
        "must_contain",
        "must_not_contain",
    }
    unknown_expect = sorted(expect.keys() - allowed_expect)
    if unknown_expect:
        raise RunnerError(
            f"case {case_id!r}: unknown expect field(s): {', '.join(unknown_expect)}"
        )
    output_kind = expect.get("output_kind", "any")
    if not isinstance(output_kind, str) or output_kind not in VALID_OUTPUT_KINDS:
        raise RunnerError(
            f"case {case_id!r}: output_kind must be one of {sorted(VALID_OUTPUT_KINDS)}"
        )
    validator_call = expect.get("validator_call")
    if validator_call is not None and not isinstance(validator_call, bool):
        raise RunnerError(f"case {case_id!r}: validator_call must be true, false, or null")
    validator_course = expect.get("validator_course")
    validator_ap_oriented = expect.get("validator_ap_oriented")
    json_contract = expect.get("json_contract")
    if validator_course is not None and (
        not isinstance(validator_course, str)
        or validator_course not in VALID_COURSES
    ):
        raise RunnerError(
            f"case {case_id!r}: validator_course must be one of "
            f"{sorted(VALID_COURSES)} or null"
        )
    if validator_ap_oriented is not None and not isinstance(
        validator_ap_oriented, bool
    ):
        raise RunnerError(
            f"case {case_id!r}: validator_ap_oriented must be true, false, or null"
        )
    if output_kind == "json_success":
        json_contract = _validate_json_contract(json_contract, case_id)
    elif json_contract is not None:
        raise RunnerError(
            f"case {case_id!r}: json_contract is allowed only for json_success"
        )

    if validator_call is True and output_kind == "text":
        if validator_course is None or validator_ap_oriented is None:
            raise RunnerError(
                f"case {case_id!r}: text cases requiring the validator must set "
                "validator_course and validator_ap_oriented"
            )
    elif validator_course is not None or validator_ap_oriented is not None:
        raise RunnerError(
            f"case {case_id!r}: validator_course and validator_ap_oriented are "
            "allowed only on text cases with validator_call=true"
        )
    must_contain = _require_string_list(expect.get("must_contain", []), "must_contain", case_id)
    must_not_contain = _require_string_list(
        expect.get("must_not_contain", []), "must_not_contain", case_id
    )
    forbidden_content_fields = _require_string_list(
        expect.get("forbidden_content_fields", []),
        "forbidden_content_fields",
        case_id,
    )
    if forbidden_content_fields and output_kind != "json_success":
        raise RunnerError(
            f"case {case_id!r}: forbidden_content_fields is allowed only for "
            "json_success"
        )
    unknown_content_fields = sorted(
        set(forbidden_content_fields) - VALID_CONTENT_FIELDS
    )
    if unknown_content_fields:
        raise RunnerError(
            f"case {case_id!r}: forbidden_content_fields contains unknown "
            f"field(s): {', '.join(unknown_content_fields)}"
        )
    if len(forbidden_content_fields) != len(set(forbidden_content_fields)):
        raise RunnerError(
            f"case {case_id!r}: forbidden_content_fields contains duplicates"
        )

    manual_check_items = list(
        _require_string_list(raw["manual_checks"], "manual_checks", case_id)
    )
    if (
        output_kind == "text"
        and validator_call is True
        and TEXT_EVIDENCE_MANUAL_CHECK not in manual_check_items
    ):
        manual_check_items.append(TEXT_EVIDENCE_MANUAL_CHECK)
    manual_checks = tuple(manual_check_items)
    normalized_expect = {
        "output_kind": output_kind,
        "validator_call": validator_call,
        "validator_course": validator_course,
        "validator_ap_oriented": validator_ap_oriented,
        "json_contract": json_contract,
        "forbidden_content_fields": forbidden_content_fields,
        "must_contain": must_contain,
        "must_not_contain": must_not_contain,
    }
    return EvalCase(
        id=case_id,
        category=category,
        invocation=invocation,
        prompt=prompt.strip(),
        expect=normalized_expect,
        manual_checks=manual_checks,
    )


def load_cases(path: Path) -> list[EvalCase]:
    """Load a UTF-8 JSONL corpus and enforce cross-record invariants."""

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise RunnerError(f"cannot read corpus {path}: {exc}") from exc

    cases: list[EvalCase] = []
    seen: set[str] = set()
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            raw = _strict_json_loads(line)
        except (json.JSONDecodeError, DuplicateJsonKeyError) as exc:
            detail = exc.msg if isinstance(exc, json.JSONDecodeError) else str(exc)
            raise RunnerError(
                f"{path}:{line_number}: invalid JSON: {detail}"
            ) from exc
        case = validate_case(raw, line_number)
        if case.id in seen:
            raise RunnerError(f"{path}:{line_number}: duplicate case id {case.id!r}")
        seen.add(case.id)
        cases.append(case)

    if not cases:
        raise RunnerError(f"corpus {path} contains no cases")
    return cases


def select_cases(cases: Iterable[EvalCase], requested_ids: list[str]) -> list[EvalCase]:
    selected = list(cases)
    if not requested_ids:
        return selected
    by_id = {case.id: case for case in selected}
    missing = [case_id for case_id in requested_ids if case_id not in by_id]
    if missing:
        raise RunnerError(f"unknown case id(s): {', '.join(missing)}")
    # Preserve command-line order while suppressing accidental duplicates.
    return [by_id[case_id] for case_id in dict.fromkeys(requested_ids)]


def parse_json_events(stdout: str) -> list[dict[str, Any]]:
    """Decode the JSONL emitted by ``codex exec --json``."""

    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(stdout.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = _strict_json_loads(line)
        except (json.JSONDecodeError, DuplicateJsonKeyError) as exc:
            detail = exc.msg if isinstance(exc, json.JSONDecodeError) else str(exc)
            raise RunnerError(
                f"codex JSONL line {line_number} is invalid: {detail}"
            ) from exc
        if not isinstance(event, dict):
            raise RunnerError(f"codex JSONL line {line_number} is not an object")
        events.append(event)
    if not events:
        raise RunnerError("codex produced no JSON events")
    return events


def extract_final_message(events: Iterable[dict[str, Any]]) -> str:
    """Return the last completed Codex agent message."""

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
    if not messages:
        raise RunnerError("codex produced no completed agent_message")
    return messages[-1]


def _command_text(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return subprocess.list2cmdline(value)
    return None


def _strip_outer_quotes(value: str) -> str | None:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return None


def _unwrap_shell_command(command: str) -> tuple[str, list[str], str | None]:
    """Unwrap at most one known shell wrapper and reject ambiguous forms."""

    failures: list[str] = []
    shell_kind: str | None = None
    command = command.strip()
    unix = re.fullmatch(
        r"(?:[^\s\"']+[/\\])?(?:bash|sh|zsh)(?:\.exe)?\s+"
        r"(?:(?:-lc|-cl|-c)|(?:(?:-l|--login)\s+-c))\s+(.+)",
        command,
        re.IGNORECASE,
    )
    if unix:
        shell_kind = "posix"
        payload = unix.group(1).strip()
        try:
            wrapper_tokens = shlex.split(command, posix=True)
        except ValueError as exc:
            failures.append(f"cannot tokenize POSIX shell wrapper: {exc}")
            command = payload
        else:
            options = wrapper_tokens[1:-1]
            if options not in (
                ["-c"],
                ["-lc"],
                ["-cl"],
                ["-l", "-c"],
                ["--login", "-c"],
            ):
                failures.append(
                    "POSIX shell wrapper requires exactly one command-string argument"
                )
                command = payload
            else:
                command = wrapper_tokens[-1].strip()
    else:
        powershell = re.fullmatch(
            r"(?:"
            r'"[^"\r\n]*[/\\](?:powershell|pwsh)(?:\.exe)?"|'
            r"'[^'\r\n]*[/\\](?:powershell|pwsh)(?:\.exe)?'|"
            r"[^\s\"']*[/\\](?:powershell|pwsh)(?:\.exe)?|"
            r"(?:powershell|pwsh)(?:\.exe)?"
            r")\s+"
            r"(?:(?:-noprofile|-noninteractive|-nologo)\s+)*"
            r"(?:-command|-c)\s+(.+)",
            command,
            re.IGNORECASE,
        )
        if powershell:
            shell_kind = "powershell"
            payload = powershell.group(1).strip()
            command = (_strip_outer_quotes(payload) or payload).strip()
            if command.startswith("&"):
                command = command[1:].lstrip()
        else:
            cmd = re.fullmatch(
                r"cmd(?:\.exe)?\s+/c\s+(.+)", command, re.IGNORECASE
            )
            if cmd:
                shell_kind = "cmd"
                payload = cmd.group(1).strip()
                command = (_strip_outer_quotes(payload) or payload).strip()

    # PowerShell requires its call operator when the executable path itself is
    # quoted. Treat one leading operator as invocation syntax, not composition.
    if command.startswith("&"):
        shell_kind = shell_kind or "powershell"
        command = command[1:].lstrip()

    if re.match(
        r"^(?:bash|sh|zsh|powershell|pwsh|cmd)(?:\.exe)?\b",
        command,
        re.IGNORECASE,
    ):
        failures.append("nested shell wrappers are not accepted as validator evidence")
    return command, failures, shell_kind


def _protect_powershell_apostrophes(command: str) -> str:
    """Protect PowerShell's doubled apostrophe inside single-quoted strings."""

    sentinel = "\ue000"
    if sentinel in command:
        return command
    output: list[str] = []
    in_single_quote = False
    in_double_quote = False
    index = 0
    while index < len(command):
        char = command[index]
        if char == "'" and not in_double_quote:
            if (
                in_single_quote
                and index + 1 < len(command)
                and command[index + 1] == "'"
            ):
                output.append(sentinel)
                index += 2
                continue
            in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote:
            if (
                in_double_quote
                and index + 1 < len(command)
                and command[index + 1] == '"'
            ):
                output.extend(('"', '"'))
                index += 2
                continue
            in_double_quote = not in_double_quote
        output.append(char)
        index += 1
    return "".join(output)


def _shell_control_failure(command: str) -> str | None:
    """Return a reason when unquoted shell composition is present."""

    if "$" in command or "`" in command:
        return "shell variable or command expansion is not allowed"
    if re.search(r"%[^%\r\n]+%|![A-Za-z_][A-Za-z0-9_]*!", command):
        return "shell environment-variable expansion is not allowed"
    quote: str | None = None
    index = 0
    while index < len(command):
        char = command[index]
        if quote is not None:
            if char == quote:
                quote = None
            index += 1
            continue
        if char in {"'", '"'}:
            quote = char
        elif char in "\r\n;&|<>":
            return f"shell control character {char!r} is not allowed"
        index += 1
    if quote is not None:
        return "validator command contains an unmatched quote"
    return None


def _executable_name(token: str) -> str:
    return token.replace("\\", "/").rsplit("/", 1)[-1].casefold()


def _is_python_executable(token: str) -> bool:
    return bool(
        re.fullmatch(
            r"python(?:3(?:\.\d+)*)?(?:\.exe)?", _executable_name(token)
        )
    )


def _is_canonical_launcher_token(token: str, name: str) -> bool:
    """Return whether *token* is the platform's bare canonical launcher.

    Windows command lookup is case-insensitive and commonly exposes either a
    bare name or its ``.exe`` form.  POSIX lookup is case-sensitive, and an
    ``.exe`` suffix names a different command, so neither equivalence is safe
    there when proving that all ordinary launchers were exhausted.
    """

    normalized = token.replace("\\", "/")
    if "/" in normalized:
        return False
    if sys.platform == "win32":
        return normalized.casefold() in {name, f"{name}.exe"}
    return normalized == name


def _is_validator_path(
    token: str, expected_validator_path: Path | None = None
) -> bool:
    normalized = token.replace("\\", "/")
    parts = [part.casefold() for part in normalized.split("/") if part]
    if ".." in parts:
        return False
    if expected_validator_path is not None:
        expected = str(expected_validator_path).replace("\\", "/")
        return normalized.casefold() == expected.casefold()
    if parts == ["scripts", "validate_topic_code.py"]:
        return True
    is_absolute = normalized.startswith("/") or bool(
        re.match(r"^[A-Za-z]:/", normalized)
    )
    return is_absolute and len(parts) >= 5 and parts[-5:] == [
        ".agents",
        "skills",
        "ap-advisor",
        "scripts",
        "validate_topic_code.py",
    ]


def _parse_validator_invocation(
    command: str,
    expected_validator_path: Path | None = None,
) -> tuple[bool, ValidatorInvocation | None, tuple[str, ...]]:
    """Recognize one direct validator call and parse its security-relevant args."""

    hint = bool(VALIDATOR_COMMAND_HINT.search(command)) or (
        "validate_topic_code.py" in command.casefold()
    )
    inner, failures, shell_kind = _unwrap_shell_command(command)
    control_failure = _shell_control_failure(inner)
    if control_failure:
        failures.append(control_failure)

    try:
        # ``posix=False`` preserves backslashes in unquoted Windows absolute
        # paths. Strip only a token's matching outer quotes afterward so the
        # same parser also accepts the quoted Unix/PowerShell forms above.
        use_powershell_quoting = shell_kind == "powershell" or (
            shell_kind is None and sys.platform == "win32"
        )
        token_source = (
            _protect_powershell_apostrophes(inner)
            if use_powershell_quoting
            else inner
        )
        tokens = []
        split_as_posix = shell_kind == "posix" or (
            shell_kind is None and sys.platform != "win32"
        )
        for token in shlex.split(token_source, posix=split_as_posix):
            stripped = _strip_outer_quotes(token) or token
            tokens.append(stripped.replace("\ue000", "'"))
    except ValueError as exc:
        if hint:
            failures.append(f"cannot tokenize validator command: {exc}")
            return True, None, tuple(failures)
        return False, None, ()
    if not tokens:
        return (True, None, tuple(failures or ["validator command is empty"])) if hint else (False, None, ())

    validator_path_present = any(
        _is_validator_path(token, expected_validator_path) for token in tokens
    )
    hint = hint or validator_path_present

    if _executable_name(tokens[0]) in NON_EXECUTION_COMMANDS:
        # A plain source read/search is not execution.  However, never let a
        # read-command prefix erase an already detected shell-composition or
        # expansion failure: ``rg ... ; python validator.py ...`` still runs
        # the validator and therefore must be observed and rejected.
        if not failures:
            return False, None, ()
        return True, None, tuple(failures)

    # Accept only encoding-related environment setup; other environment
    # mutation can change Python import/execution behavior and is not sealed.
    command_tokens = list(tokens)
    if _executable_name(command_tokens[0]) == "env":
        command_tokens.pop(0)
        if command_tokens and command_tokens[0] == "--":
            command_tokens.pop(0)
        while command_tokens and "=" in command_tokens[0]:
            assignment = command_tokens.pop(0)
            if assignment not in SAFE_ENV_ASSIGNMENTS:
                failures.append(
                    f"unsupported environment assignment {assignment!r}"
                )
    else:
        while command_tokens and "=" in command_tokens[0]:
            assignment = command_tokens.pop(0)
            if assignment not in SAFE_ENV_ASSIGNMENTS:
                failures.append(
                    f"unsupported environment assignment {assignment!r}"
                )
    if not command_tokens:
        if hint:
            failures.append("validator command contains no executable")
            return True, None, tuple(failures)
        return False, None, ()
    tokens = command_tokens

    script_index: int | None = None
    launcher_family: str | None = None
    launcher_executable: str | None = None
    launcher_is_canonical = False
    executable = _executable_name(tokens[0])
    if _is_python_executable(tokens[0]):
        if len(tokens) > 1 and tokens[1].casefold() in {"-c", "-m"}:
            if hint:
                failures.append(
                    "indirect Python execution mentioning the validator is not "
                    "accepted as evidence"
                )
                return True, None, tuple(failures)
            return False, None, ()
        script_index = 1
        launcher_family = "python3" if executable.startswith("python3") else "python"
        launcher_executable = executable
        launcher_is_canonical = _is_canonical_launcher_token(
            tokens[0], launcher_family
        )
    elif executable in {"py", "py.exe"}:
        if len(tokens) > 2 and re.fullmatch(r"-3(?:\.\d+)?", tokens[1]):
            script_index = 2
            launcher_family = "py-3"
            launcher_executable = executable
            launcher_is_canonical = (
                _is_canonical_launcher_token(tokens[0], "py")
                and tokens[1] == "-3"
            )

    if script_index is None or script_index >= len(tokens):
        if hint:
            failures.append("validator command is not a direct supported Python invocation")
            return True, None, tuple(failures)
        return False, None, ()
    if not _is_validator_path(tokens[script_index], expected_validator_path):
        if hint:
            failures.append(
                "Python must invoke scripts/validate_topic_code.py directly"
            )
            return True, None, tuple(failures)
        return False, None, ()

    arguments = tokens[script_index + 1 :]
    course_values: list[str] = []
    citations: list[str] = []
    ap_oriented_count = 0
    evidence_count = 0
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument == "--course":
            if index + 1 >= len(arguments):
                failures.append("--course is missing its value")
                index += 1
                continue
            course_values.append(arguments[index + 1])
            index += 2
            continue
        if argument.startswith("--course="):
            course_values.append(argument.partition("=")[2])
        elif argument == "--ap-oriented":
            ap_oriented_count += 1
        elif argument == "--exam-style":
            failures.append(
                "legacy --exam-style cannot satisfy the current evidence contract"
            )
        elif argument == "--evidence-json":
            evidence_count += 1
        elif argument == "--framework" or argument.startswith("--framework="):
            failures.append("--framework overrides are not accepted as sealed evidence")
            if argument == "--framework" and index + 1 < len(arguments):
                index += 1
        elif argument.startswith("-"):
            failures.append(f"unsupported validator option {argument!r}")
        else:
            citations.append(argument)
        index += 1

    if len(course_values) != 1:
        failures.append("validator evidence requires exactly one --course option")
        course = ""
    else:
        course = course_values[0]
        if course not in VALID_COURSES:
            failures.append(f"unsupported validator course {course!r}")
    if ap_oriented_count > 1:
        failures.append("--ap-oriented may appear at most once")
    if evidence_count != 1:
        failures.append("validator evidence requires exactly one --evidence-json flag")
    if not citations:
        failures.append("validator evidence contains no citations")

    invocation = None
    if (
        course
        and course in VALID_COURSES
        and launcher_family is not None
        and launcher_executable is not None
    ):
        invocation = ValidatorInvocation(
            launcher=launcher_family,
            launcher_executable=launcher_executable,
            launcher_is_canonical=launcher_is_canonical,
            course=course,
            ap_oriented=ap_oriented_count == 1,
            citations=tuple(citations),
        )
    return True, invocation, tuple(failures)


def _validator_evidence_failures(value: Any, exit_code: int) -> list[str]:
    """Validate the versioned validator evidence envelope and result rows."""

    if not isinstance(value, dict):
        return ["validator output must be one JSON object"]
    required = {
        "schema_version",
        "validator",
        "course",
        "ap_oriented",
        "overall_status",
        "results",
    }
    allowed = required | {"error"}
    failures: list[str] = []
    missing = sorted(required - value.keys())
    extra = sorted(value.keys() - allowed)
    if missing:
        failures.append("validator evidence missing field(s): " + ", ".join(missing))
    if extra:
        failures.append("validator evidence has extra field(s): " + ", ".join(extra))
    schema_version = value.get("schema_version")
    if type(schema_version) is not int or schema_version != VALIDATOR_SCHEMA_VERSION:
        failures.append(
            f"validator schema_version must equal {VALIDATOR_SCHEMA_VERSION}"
        )
    if value.get("validator") != VALIDATOR_NAME:
        failures.append(f"validator must equal {VALIDATOR_NAME!r}")
    evidence_course = value.get("course")
    if not isinstance(evidence_course, str) or evidence_course not in (
        VALID_COURSES | {"unfiltered"}
    ):
        failures.append("validator course is invalid")
    if not isinstance(value.get("ap_oriented"), bool):
        failures.append("validator ap_oriented must be boolean")

    expected_status = {0: "pass", 1: "fail", 2: "error"}.get(exit_code)
    overall_status = value.get("overall_status")
    if not isinstance(overall_status, str) or overall_status not in {
        "pass",
        "fail",
        "error",
    }:
        failures.append("validator overall_status is invalid")
    elif expected_status is not None and overall_status != expected_status:
        failures.append(
            f"exit {exit_code} requires overall_status {expected_status!r}"
        )

    results = value.get("results")
    if not isinstance(results, list):
        failures.append("validator results must be an array")
        return failures
    if exit_code in {0, 1} and not results:
        failures.append("validator pass/fail evidence requires at least one result")

    statuses: list[str] = []
    for index, result in enumerate(results):
        path = f"validator results[{index}]"
        if not isinstance(result, dict):
            failures.append(f"{path} must be an object")
            continue
        status = result.get("status")
        statuses.append(status if isinstance(status, str) else "")
        base_required = {"input", "status"}
        if status == "pass":
            row_required = base_required | {"citation", "topic_exam_scope"}
            row_allowed = row_required
        elif status == "fail":
            row_required = base_required | {"message"}
            row_allowed = row_required | {
                "citation",
                "topic_exam_scope",
                "candidates",
            }
        else:
            failures.append(f"{path}.status must be 'pass' or 'fail'")
            row_required = base_required
            row_allowed = set(result)
        missing_row = sorted(row_required - result.keys())
        extra_row = sorted(result.keys() - row_allowed)
        if missing_row:
            failures.append(f"{path} missing field(s): {', '.join(missing_row)}")
        if extra_row:
            failures.append(f"{path} has extra field(s): {', '.join(extra_row)}")
        for field in ("input", "citation", "message"):
            if field in result and (
                not isinstance(result[field], str) or not result[field].strip()
            ):
                failures.append(f"{path}.{field} must be a non-empty string")
        if "topic_exam_scope" in result:
            scope = result["topic_exam_scope"]
            if not isinstance(scope, str) or scope not in {
                "assessed",
                "not-assessed",
            }:
                failures.append(f"{path}.topic_exam_scope is invalid")
        if ("citation" in result) != ("topic_exam_scope" in result):
            failures.append(
                f"{path}.citation and topic_exam_scope must appear together"
            )
        if "candidates" in result and (
            not isinstance(result["candidates"], list)
            or any(
                not isinstance(candidate, str) or not candidate.strip()
                for candidate in result["candidates"]
            )
        ):
            failures.append(f"{path}.candidates must be an array of strings")

    if overall_status == "pass" and any(status != "pass" for status in statuses):
        failures.append("overall pass requires every result to pass")
    if overall_status == "fail" and "fail" not in statuses:
        failures.append("overall fail requires at least one failed result")
    if overall_status == "error":
        if results:
            failures.append("overall error requires an empty results array")
        if not isinstance(value.get("error"), str) or not value["error"].strip():
            failures.append("overall error requires a non-empty error field")
    elif "error" in value:
        failures.append("error is allowed only when overall_status is 'error'")
    return failures


def _event_field(
    item: dict[str, Any], names: tuple[str, ...], label: str
) -> tuple[Any, list[str]]:
    present = [(name, item[name]) for name in names if name in item]
    if not present:
        return None, []
    first = present[0][1]
    failures = []
    if any(
        type(value) is not type(first) or value != first
        for _, value in present[1:]
    ):
        failures.append(f"conflicting {label} fields in completed event")
    return first, failures


def _is_verified_launcher_failure(
    exit_code: int, output: str, launcher_executable: str
) -> bool:
    """Recognize a shell-level launcher failure before Python starts."""

    if exit_code not in {1, 127, 9009}:
        return False
    try:
        json.loads(output.strip())
    except (json.JSONDecodeError, TypeError):
        pass
    else:
        return False
    executable = re.escape(launcher_executable)
    without_suffix = re.escape(re.sub(r"\.exe$", "", launcher_executable))
    names = executable if executable == without_suffix else f"(?:{executable}|{without_suffix})"
    quote = r"[`'\"\u2018\u2019\u201c\u201d]?"
    path = r"(?:(?:[A-Za-z]:)?[/\\](?:[^\s:'\"`/\\]+[/\\])*)?"
    launcher = (
        rf"(?<![A-Za-z0-9_.-]){quote}{path}{names}{quote}"
        rf"(?![A-Za-z0-9_.-])"
    )
    patterns = (
        rf"{launcher}\s*:\s*(?:command\s+)?not found\b",
        rf"\bcommand\s+not\s+found\s*:\s*{launcher}",
        rf"{launcher}\s+is not recognized as (?:the name of a cmdlet|an internal or external command)\b",
        rf"\bthe term\s+{launcher}\s+is not recognized as the name of a cmdlet\b",
        rf"\benv:\s+{launcher}.*\bno such file or directory\b",
        rf"\bObjectNotFound:\s*\(\s*{launcher}\s*:String\).*\bCommandNotFoundException\b",
    )
    if any(re.search(pattern, output, re.IGNORECASE) for pattern in patterns):
        return True
    if re.sub(r"\.exe$", "", launcher_executable) in {"python", "python3"}:
        return bool(
            re.search(
                r"^\s*Python was not found; run without arguments to install "
                r"from the Microsoft Store\.\s*$",
                output,
                re.IGNORECASE | re.MULTILINE,
            )
        )
    return False


def _completed_validator_run(
    *,
    item_id: str | None,
    command: str,
    item: dict[str, Any],
    prefix_failures: list[str],
    expected_validator_path: Path | None,
) -> ValidatorRun | None:
    candidate, invocation, parse_failures = _parse_validator_invocation(
        command, expected_validator_path
    )
    if not candidate:
        return None
    failures = [*prefix_failures, *parse_failures]
    fatal = bool(prefix_failures or parse_failures)

    status = item.get("status")

    exit_code, field_failures = _event_field(
        item, ("exit_code", "exitCode"), "exit code"
    )
    failures.extend(field_failures)
    fatal = fatal or bool(field_failures)
    if not isinstance(exit_code, int) or isinstance(exit_code, bool):
        failures.append("completed event must include an integer exit code")
        fatal = True
        exit_code = None

    if status not in {"completed", "failed"}:
        failures.append(
            "completed event status must be 'completed' or 'failed'"
        )
        fatal = True
    elif exit_code == 0 and status != "completed":
        failures.append("exit-zero completed event must report status 'completed'")
        fatal = True

    output, output_failures = _event_field(
        item, ("aggregated_output", "aggregatedOutput"), "aggregated output"
    )
    failures.extend(output_failures)
    fatal = fatal or bool(output_failures)
    if output is None:
        stdout, stdout_failures = _event_field(item, ("stdout",), "stdout")
        stderr, stderr_failures = _event_field(item, ("stderr",), "stderr")
        failures.extend(stdout_failures + stderr_failures)
        if stdout is None and stderr is None:
            failures.append("completed event contains no validator output")
            fatal = True
        elif all(value is None or isinstance(value, str) for value in (stdout, stderr)):
            output = (stdout or "") + (stderr or "")
        else:
            failures.append("validator stdout/stderr fields must be strings")
            fatal = True
    elif not isinstance(output, str):
        failures.append("validator aggregated output must be a string")
        fatal = True
        output = None

    evidence: dict[str, Any] | None = None
    prestart_failure = bool(
        not fatal
        and invocation is not None
        and output is not None
        and exit_code is not None
        and _is_verified_launcher_failure(
            exit_code, output, invocation.launcher_executable
        )
    )
    if prestart_failure:
        failures.append("validator launcher failed before the Python script started")
    elif output is not None and exit_code is not None:
        try:
            decoded = _strict_json_loads(output.strip())
        except (json.JSONDecodeError, DuplicateJsonKeyError, TypeError) as exc:
            failures.append(f"validator output is not one JSON object: {exc}")
            fatal = True
        else:
            evidence_failures = _validator_evidence_failures(decoded, exit_code)
            failures.extend(evidence_failures)
            fatal = fatal or bool(evidence_failures)
            if isinstance(decoded, dict):
                evidence = decoded

    if exit_code not in {0, 1} and not prestart_failure:
        failures.append(
            "validator exit 2 or any non-contract exit is a fatal setup/data failure"
        )
        fatal = True

    if invocation is not None and evidence is not None:
        if evidence.get("course") != invocation.course:
            failures.append("validator evidence course does not match its command")
            fatal = True
        if evidence.get("ap_oriented") is not invocation.ap_oriented:
            failures.append("validator evidence AP-oriented flag does not match its command")
            fatal = True
        results = evidence.get("results")
        if isinstance(results, list):
            inputs = [
                result.get("input")
                for result in results
                if isinstance(result, dict) and isinstance(result.get("input"), str)
            ]
            if Counter(inputs) != Counter(invocation.citations):
                failures.append(
                    "validator evidence inputs do not exactly match command citations"
                )
                fatal = True

    return ValidatorRun(
        item_id=item_id,
        command=command,
        completed=True,
        status=status if isinstance(status, str) else None,
        exit_code=exit_code,
        invocation=invocation,
        evidence=evidence,
        failures=tuple(failures),
        fatal=fatal,
        prestart_failure=prestart_failure,
    )


def extract_validator_evidence(
    events: Iterable[dict[str, Any]],
    expected_validator_path: Path | None = None,
) -> ValidatorObservation:
    """Correlate command events and accept evidence only from completed runs."""

    all_started_commands: dict[str, str] = {}
    seen_started_ids: set[str] = set()
    started_identity_failures: dict[str, list[str]] = {}
    started: dict[str, tuple[str, ValidatorInvocation | None, tuple[str, ...]]] = {}
    unkeyed_started: list[tuple[str, ValidatorInvocation | None, tuple[str, ...]]] = []
    matched_started_ids: set[str] = set()
    seen_completed_ids: set[str] = set()
    completed_validator_ids: set[str] = set()
    runs: list[ValidatorRun] = []

    for event in events:
        item = event.get("item")
        if not isinstance(item, dict) or item.get("type") != "command_execution":
            continue
        event_type = event.get("type")
        if event_type not in {"item.started", "item.completed"}:
            continue
        item_id = item.get("id") if isinstance(item.get("id"), str) else None
        command = _command_text(item.get("command"))

        if event_type == "item.started":
            identity_failures: list[str] = []
            if item_id is not None:
                if item_id in seen_started_ids:
                    identity_failures.append(
                        "duplicate item.started id in command event stream"
                    )
                    previous_command = all_started_commands.get(item_id)
                    if (
                        command is not None
                        and previous_command is not None
                        and command != previous_command
                    ):
                        identity_failures.append(
                            "duplicate item.started id reports different commands"
                        )
                else:
                    seen_started_ids.add(item_id)
                if command is None:
                    identity_failures.append(
                        "item.started command is missing or malformed"
                    )
                elif item_id not in all_started_commands:
                    all_started_commands[item_id] = command
                if identity_failures:
                    started_identity_failures.setdefault(item_id, []).extend(
                        identity_failures
                    )

            if command is None:
                if item_id is not None and item_id in completed_validator_ids:
                    runs.append(
                        ValidatorRun(
                            item_id=item_id,
                            command="",
                            completed=False,
                            status=None,
                            exit_code=None,
                            invocation=None,
                            evidence=None,
                            failures=tuple(
                                [
                                    *started_identity_failures.get(item_id, ()),
                                    "item.started appears after item.completed for "
                                    "the same id",
                                ]
                            ),
                            fatal=True,
                        )
                    )
                continue
            candidate, invocation, failures = _parse_validator_invocation(
                command, expected_validator_path
            )
            if item_id is not None and item_id in seen_completed_ids:
                if candidate or item_id in completed_validator_ids:
                    runs.append(
                        ValidatorRun(
                            item_id=item_id,
                            command=command,
                            completed=False,
                            status=None,
                            exit_code=None,
                            invocation=invocation,
                            evidence=None,
                            failures=tuple(
                                [
                                    *failures,
                                    *started_identity_failures.get(item_id, ()),
                                    "item.started appears after item.completed for "
                                    "the same id",
                                ]
                            ),
                            fatal=True,
                        )
                    )
                continue
            if not candidate:
                continue
            if item_id is None:
                unkeyed_started.append((command, invocation, failures))
            else:
                if item_id in started:
                    previous_command, previous_invocation, previous_failures = started[
                        item_id
                    ]
                    duplicate_failures = [
                        *previous_failures,
                        *failures,
                    ]
                    started[item_id] = (
                        previous_command,
                        previous_invocation,
                        tuple(duplicate_failures),
                    )
                else:
                    started[item_id] = (
                        command,
                        invocation,
                        failures,
                    )
            continue

        prefix_failures: list[str] = []
        duplicate_completed_id = (
            item_id is not None and item_id in seen_completed_ids
        )
        prior_completed_validator = (
            item_id is not None and item_id in completed_validator_ids
        )
        if item_id is not None:
            seen_completed_ids.add(item_id)
        if duplicate_completed_id:
            prefix_failures.append(
                "duplicate item.completed id in command event stream"
            )
        identity_started_command = (
            all_started_commands.get(item_id) if item_id is not None else None
        )
        started_record = started.get(item_id) if item_id is not None else None
        if started_record is not None:
            matched_started_ids.add(item_id)
            prefix_failures.extend(started_record[2])
        if item_id is not None:
            prefix_failures.extend(started_identity_failures.get(item_id, ()))
        if identity_started_command is not None:
            if command is None:
                command = (
                    started_record[0]
                    if started_record is not None
                    else identity_started_command
                )
            elif command != identity_started_command:
                prefix_failures.append(
                    "started and completed events report different commands"
                )
                if started_record is not None:
                    command = started_record[0]
        if command is None:
            if duplicate_completed_id and prior_completed_validator:
                runs.append(
                    ValidatorRun(
                        item_id=item_id,
                        command="",
                        completed=True,
                        status=(
                            item.get("status")
                            if isinstance(item.get("status"), str)
                            else None
                        ),
                        exit_code=None,
                        invocation=None,
                        evidence=None,
                        failures=tuple(prefix_failures),
                        fatal=True,
                    )
                )
            continue
        run = _completed_validator_run(
            item_id=item_id,
            command=command,
            item=item,
            prefix_failures=prefix_failures,
            expected_validator_path=expected_validator_path,
        )
        if run is not None:
            runs.append(run)
            if item_id is not None:
                completed_validator_ids.add(item_id)
        elif duplicate_completed_id and prior_completed_validator:
            runs.append(
                ValidatorRun(
                    item_id=item_id,
                    command=command,
                    completed=True,
                    status=(
                        item.get("status")
                        if isinstance(item.get("status"), str)
                        else None
                    ),
                    exit_code=None,
                    invocation=None,
                    evidence=None,
                    failures=tuple(prefix_failures),
                    fatal=True,
                )
            )

    for item_id, (command, invocation, failures) in started.items():
        if item_id in matched_started_ids:
            continue
        runs.append(
            ValidatorRun(
                item_id=item_id,
                command=command,
                completed=False,
                status=None,
                exit_code=None,
                invocation=invocation,
                evidence=None,
                failures=tuple(
                    [
                        *failures,
                        *started_identity_failures.get(item_id, ()),
                        "validator item.started has no matching item.completed",
                    ]
                ),
                fatal=True,
            )
        )
    for command, invocation, failures in unkeyed_started:
        runs.append(
            ValidatorRun(
                item_id=None,
                command=command,
                completed=False,
                status=None,
                exit_code=None,
                invocation=invocation,
                evidence=None,
                failures=tuple(
                    [*failures, "validator item.started has no id for completion correlation"]
                ),
                fatal=True,
            )
        )
    return ValidatorObservation(tuple(runs))


def detected_validator_call(events: Iterable[dict[str, Any]]) -> bool:
    """Compatibility helper: report observation, never validation success."""

    return extract_validator_evidence(events).observed


def _decode_json_message(message: str) -> Any:
    candidate = message.strip()
    if candidate.startswith("```") and candidate.endswith("```"):
        lines = candidate.splitlines()
        if len(lines) >= 3:
            candidate = "\n".join(lines[1:-1]).strip()
            if candidate.casefold().startswith("json\n"):
                candidate = candidate[5:]
    return _strict_json_loads(candidate)


@functools.lru_cache(maxsize=2)
def _load_schema(path: Path) -> dict[str, Any]:
    try:
        value = _strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, DuplicateJsonKeyError) as exc:
        raise RunnerError(f"cannot load JSON schema {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RunnerError(f"JSON schema {path} is not an object")
    return value


def _schema_failures(value: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    """Validate the Draft 7 subset used by this repository's two schemas."""

    unsupported = sorted(schema.keys() - SUPPORTED_SCHEMA_KEYWORDS)
    if unsupported:
        raise RunnerError(
            "unsupported JSON Schema keyword(s): " + ", ".join(unsupported)
        )

    failures: list[str] = []
    expected_type = schema.get("type")
    type_checks = {
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str),
    }
    if expected_type in type_checks and not type_checks[expected_type](value):
        return [f"{path} must be {expected_type}"]

    if "const" in schema and value != schema["const"]:
        failures.append(f"{path} must equal {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        failures.append(f"{path} must be one of {schema['enum']!r}")

    if isinstance(value, str):
        min_length = schema.get("minLength")
        if isinstance(min_length, int) and len(value) < min_length:
            failures.append(f"{path} must contain at least {min_length} character(s)")
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and re.search(pattern, value) is None:
            failures.append(f"{path} does not match {pattern!r}")

    if isinstance(value, list):
        min_items = schema.get("minItems")
        if isinstance(min_items, int) and len(value) < min_items:
            failures.append(f"{path} must contain at least {min_items} item(s)")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                failures.extend(_schema_failures(item, item_schema, f"{path}[{index}]"))

    if isinstance(value, dict):
        required = schema.get("required", [])
        if isinstance(required, list):
            for name in required:
                if name not in value:
                    failures.append(f"{path}.{name} is required")
        properties = schema.get("properties", {})
        if isinstance(properties, dict):
            for name, property_schema in properties.items():
                if name in value and isinstance(property_schema, dict):
                    failures.extend(
                        _schema_failures(value[name], property_schema, f"{path}.{name}")
                    )
            if schema.get("additionalProperties") is False:
                for name in sorted(value.keys() - properties.keys()):
                    failures.append(f"{path}.{name} is not allowed")

    all_of = schema.get("allOf", [])
    if isinstance(all_of, list):
        for branch in all_of:
            if not isinstance(branch, dict):
                continue
            condition = branch.get("if")
            consequence = branch.get("then")
            if isinstance(condition, dict) and isinstance(consequence, dict):
                if not _schema_failures(value, condition, path):
                    failures.extend(_schema_failures(value, consequence, path))
            else:
                failures.extend(_schema_failures(value, branch, path))
    return failures


def _json_shape_failures(kind: str, message: str) -> list[str]:
    if kind == "any":
        return []
    try:
        value = _decode_json_message(message)
    except (json.JSONDecodeError, DuplicateJsonKeyError, TypeError) as exc:
        if kind == "text":
            return []
        return [f"expected {kind}, but the final message is not one JSON object: {exc}"]
    if kind == "text":
        return ["expected text, but the final message is valid JSON"]
    if not isinstance(value, dict):
        return [f"expected {kind}, but the decoded value is not an object"]
    schema_path = ERROR_SCHEMA if kind == "json_error" else OUTPUT_SCHEMA
    return [f"{kind}: {failure}" for failure in _schema_failures(value, _load_schema(schema_path))]


def _output_citation(unit: Any, topic: Any) -> str | None:
    if not isinstance(unit, str) or not isinstance(topic, str):
        return None
    if re.fullmatch(r"Unit \d+", unit) is None:
        return None
    topic_parts = topic.split(" ", 1)
    if len(topic_parts) != 2 or re.fullmatch(r"\d+\.\d+", topic_parts[0]) is None:
        return None
    return f"{unit}, Topic {topic_parts[0]} — {topic_parts[1]}"


def _json_output_evidence_expectation(
    value: dict[str, Any],
) -> tuple[str | None, bool | None, Counter[tuple[str, str]], str | None]:
    raw_course = value.get("course")
    course = (
        raw_course
        if isinstance(raw_course, str) and raw_course in VALID_COURSES
        else None
    )
    style = value.get("style")
    ap_oriented = (
        style == "ap-oriented"
        if isinstance(style, str) and style in {"instructional", "ap-oriented"}
        else None
    )
    expected: Counter[tuple[str, str]] = Counter()
    primary = _output_citation(value.get("unit"), value.get("topic"))
    primary_scope = value.get("topic_exam_scope")
    if (
        primary is not None
        and isinstance(primary_scope, str)
        and primary_scope in {"assessed", "not-assessed"}
    ):
        expected[(primary, primary_scope)] += 1
    supporting = value.get("supporting_topics", [])
    if isinstance(supporting, list):
        for item in supporting:
            if not isinstance(item, dict):
                continue
            citation = _output_citation(item.get("unit"), item.get("topic"))
            scope = item.get("topic_exam_scope")
            if (
                citation is not None
                and isinstance(scope, str)
                and scope in {"assessed", "not-assessed"}
            ):
                expected[(citation, scope)] += 1
    validation = value.get("citation_validation")
    automated_status = (
        validation.get("automated_status") if isinstance(validation, dict) else None
    )
    return course, ap_oriented, expected, automated_status


def _accepted_evidence_rows(
    observation: ValidatorObservation,
) -> tuple[Counter[tuple[str, str]], set[str], set[bool]]:
    rows: Counter[tuple[str, str]] = Counter()
    courses: set[str] = set()
    modes: set[bool] = set()
    for run in observation.accepted_runs:
        if run.invocation is not None:
            courses.add(run.invocation.course)
            modes.add(run.invocation.ap_oriented)
        results = run.evidence.get("results", []) if run.evidence else []
        for result in results:
            if not isinstance(result, dict) or result.get("status") != "pass":
                continue
            citation = result.get("citation")
            scope = result.get("topic_exam_scope")
            if isinstance(citation, str) and isinstance(scope, str):
                rows[(citation, scope)] += 1
    return rows, courses, modes


class _VisibleTextExtractor(HTMLParser):
    """Extract rendered text while omitting comments and common hidden nodes."""

    VOID_TAGS = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.stack: list[tuple[str, bool]] = []
        self.hidden_depth = 0

    @staticmethod
    def _is_hidden(tag: str, attrs: list[tuple[str, str | None]]) -> bool:
        values = {name.casefold(): value for name, value in attrs}
        style = re.sub(r"\s+", "", values.get("style") or "").casefold()
        classes = set((values.get("class") or "").casefold().split())
        return (
            tag.casefold() in {"script", "style", "template"}
            or "hidden" in values
            or (values.get("aria-hidden") or "").casefold() == "true"
            or "display:none" in style
            or "visibility:hidden" in style
            or bool(classes & {"hidden", "sr-only", "visually-hidden"})
        )

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag.casefold() in self.VOID_TAGS:
            return
        hidden = self.hidden_depth > 0 or self._is_hidden(tag, attrs)
        self.stack.append((tag.casefold(), hidden))
        if hidden:
            self.hidden_depth += 1

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        return

    def handle_endtag(self, tag: str) -> None:
        target = tag.casefold()
        match = next(
            (
                index
                for index in range(len(self.stack) - 1, -1, -1)
                if self.stack[index][0] == target
            ),
            None,
        )
        if match is None:
            return
        for _tag, hidden in self.stack[match:]:
            if hidden:
                self.hidden_depth -= 1
        del self.stack[match:]

    def handle_data(self, data: str) -> None:
        if self.hidden_depth == 0:
            self.parts.append(data)


def _normalize_citation_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", html.unescape(value))
    return "".join(
        char
        for char in normalized
        if unicodedata.category(char) != "Cf"
        and char != "\u034f"
        and not "\ufe00" <= char <= "\ufe0f"
        and not "\U000e0100" <= char <= "\U000e01ef"
    )


def _citation_scan_text(value: str) -> str:
    """Normalize visible rendered text before catalog-reference scans."""

    parser = _VisibleTextExtractor()
    try:
        parser.feed(value)
        parser.close()
    except Exception:
        # HTMLParser is deliberately tolerant, but malformed future inputs
        # must not make the eval runner crash.
        rendered = value
    else:
        rendered = "".join(parser.parts)
    return _normalize_citation_text(rendered)


def _plain_text_citation_failures(
    message: str, evidence_rows: Counter[tuple[str, str]]
) -> list[str]:
    failures: list[str] = []
    if RAW_HTML_MARKUP.search(message):
        failures.append(
            "plain-text response contains raw HTML, so citation visibility is not sealed"
        )
    if MARKDOWN_REFERENCE_DEFINITION.search(message):
        failures.append(
            "plain-text response contains a Markdown reference definition, so "
            "citation visibility is not sealed"
        )
    if MARKDOWN_INLINE_LINK_MARKER.search(message):
        failures.append(
            "plain-text response contains Markdown inline link/image syntax, so "
            "citation visibility is not sealed"
        )
    expected_citations: Counter[str] = Counter()
    for (citation, _scope), count in evidence_rows.items():
        expected_citations[citation] += count

    visible_message = _citation_scan_text(message)
    remaining = visible_message
    for citation, expected_count in sorted(
        expected_citations.items(), key=lambda pair: len(pair[0]), reverse=True
    ):
        observed_count = visible_message.count(citation)
        if observed_count != expected_count:
            failures.append(
                f"plain-text citation {citation!r} expected {expected_count} time(s), "
                f"observed {observed_count}"
            )
        remaining = remaining.replace(citation, "")
    if CATALOG_TOPIC_REFERENCE.search(remaining):
        failures.append(
            "plain-text response contains an extra or non-exact catalog citation"
        )
    return failures


def _json_content_citation_failures(value: dict[str, Any]) -> list[str]:
    """Reject catalog-looking citations outside structured JSON topic fields."""

    content = value.get("content")
    if not isinstance(content, dict):
        return []
    failures: list[str] = []
    for field, field_value in content.items():
        if (
            isinstance(field_value, str)
            and (
                CATALOG_TOPIC_REFERENCE.search(
                    _normalize_citation_text(field_value)
                )
                or CATALOG_TOPIC_REFERENCE.search(_citation_scan_text(field_value))
            )
        ):
            failures.append(
                f"JSON content field {field!r} contains an unstructured catalog citation"
            )
    return failures


def _json_contract_failures(
    value: dict[str, Any], expected: dict[str, Any]
) -> list[str]:
    """Compare stable prompt constraints without constraining generated content."""

    failures: list[str] = []
    for field in JSON_CONTRACT_FIELDS - {"supporting_topics"}:
        if value.get(field) != expected[field]:
            failures.append(
                f"JSON field {field!r} expected {expected[field]!r}, "
                f"observed {value.get(field)!r}"
            )

    expected_supporting = Counter(
        (item["unit"], item["topic"], item["topic_exam_scope"])
        for item in expected["supporting_topics"]
    )
    actual_items = value.get("supporting_topics", [])
    actual_supporting: Counter[tuple[Any, Any, Any]] = Counter()
    if isinstance(actual_items, list):
        for item in actual_items:
            if isinstance(item, dict):
                key = (
                    item.get("unit"),
                    item.get("topic"),
                    item.get("topic_exam_scope"),
                )
                if all(isinstance(field, str) for field in key):
                    actual_supporting[key] += 1
    if actual_supporting != expected_supporting:
        failures.append("JSON supporting_topics do not match the case contract")
    return failures


def _validator_contract_failures(
    case: EvalCase,
    message: str,
    observation: ValidatorObservation,
) -> list[str]:
    failures = list(observation.fatal_failures)
    expected_call = case.expect["validator_call"]
    if expected_call is False and observation.observed:
        failures.append("validator_call expected false, observed true")
    elif expected_call is True and not observation.observed:
        failures.append("validator_call expected true, observed false")

    evidence_rows, courses, modes = _accepted_evidence_rows(observation)
    duplicate_evidence = [
        citation
        for (citation, _scope), count in evidence_rows.items()
        if count > 1
    ]
    if duplicate_evidence:
        failures.append(
            "validator successful evidence repeats citation(s): "
            + ", ".join(sorted(duplicate_evidence))
        )
    if len(observation.accepted_runs) > 1:
        failures.append(
            "validator evidence must come from one successful grouped run per case"
        )
    expected_kind = case.expect["output_kind"]
    expected_course: str | None = None
    expected_mode: bool | None = None
    expected_rows: Counter[tuple[str, str]] | None = None
    automated_status: str | None = None
    valid_not_run_fallback = False

    if expected_kind == "json_success":
        try:
            value = _decode_json_message(message)
        except (json.JSONDecodeError, DuplicateJsonKeyError, TypeError):
            value = None
        if isinstance(value, dict):
            failures.extend(_json_content_citation_failures(value))
            model_course, model_mode, model_rows, automated_status = (
                _json_output_evidence_expectation(value)
            )
            json_contract = case.expect.get("json_contract")
            if isinstance(json_contract, dict):
                failures.extend(_json_contract_failures(value, json_contract))
                (
                    expected_course,
                    expected_mode,
                    expected_rows,
                    _unused_status,
                ) = _json_output_evidence_expectation(json_contract)
            else:
                expected_course = model_course
                expected_mode = model_mode
                expected_rows = model_rows
            if automated_status == "pass":
                if not observation.accepted_runs:
                    failures.append(
                        "citation_validation.automated_status is pass without accepted evidence"
                    )
                elif evidence_rows != expected_rows:
                    failures.append(
                        "validator evidence citations/scopes do not exactly match JSON output"
                    )
            elif automated_status == "not_run":
                if observation.observed and not (
                    observation.only_verified_prestart_failures
                ):
                    failures.append(
                        "citation_validation.automated_status is not_run despite an "
                        "observed validator attempt that reached or may have reached "
                        "the script"
                    )
                elif observation.only_verified_prestart_failures:
                    if observation.exhausted_launcher_families:
                        valid_not_run_fallback = True
                    else:
                        failures.append(
                            "citation_validation.automated_status is not_run before "
                            "all supported launcher families were exhausted"
                        )
    elif expected_kind == "text" and expected_call is True:
        expected_course = case.expect["validator_course"]
        expected_mode = case.expect["validator_ap_oriented"]
        if observation.accepted_runs:
            failures.extend(_plain_text_citation_failures(message, evidence_rows))
    elif expected_kind == "text" and expected_call is False:
        if CATALOG_FULL_CITATION_REFERENCE.search(_citation_scan_text(message)):
            failures.append(
                "validator-forbidden text response contains a catalog topic citation"
            )

    if (
        expected_call is True
        and not observation.accepted_runs
        and not valid_not_run_fallback
    ):
        failures.append("validator produced no accepted successful evidence")

    if observation.accepted_runs and expected_course is not None and courses != {
        expected_course
    }:
        failures.append(
            f"validator course expected {expected_course!r}, observed {sorted(courses)!r}"
        )
    if observation.accepted_runs and expected_mode is not None and modes != {
        expected_mode
    }:
        failures.append(
            "validator AP-oriented mode expected "
            f"{str(expected_mode).lower()}, observed {sorted(modes)!r}"
        )
    return failures


def _forbidden_content_field_failures(
    kind: str, message: str, forbidden_fields: Iterable[str]
) -> list[str]:
    """Check JSON content keys structurally, without searching prose values."""

    fields = tuple(forbidden_fields)
    if kind != "json_success" or not fields:
        return []
    try:
        value = _decode_json_message(message)
    except (json.JSONDecodeError, DuplicateJsonKeyError, TypeError):
        return []
    if not isinstance(value, dict) or not isinstance(value.get("content"), dict):
        return []
    content = value["content"]
    return [
        f"JSON content field {field!r} is forbidden by the case contract"
        for field in fields
        if field in content
    ]


def evaluate_case(
    case: EvalCase, message: str, validator_evidence: ValidatorObservation
) -> list[str]:
    """Return automated assertion failures for one completed case."""

    failures: list[str] = []
    if not message.strip():
        failures.append("final message is empty")
        return failures

    expected_kind = case.expect["output_kind"]
    failures.extend(_json_shape_failures(expected_kind, message))
    failures.extend(
        _forbidden_content_field_failures(
            expected_kind,
            message,
            case.expect.get("forbidden_content_fields", []),
        )
    )

    normalized = message.casefold()
    for required_text in case.expect["must_contain"]:
        if required_text.casefold() not in normalized:
            failures.append(f"missing required text: {required_text!r}")
    for forbidden_text in case.expect["must_not_contain"]:
        if forbidden_text.casefold() in normalized:
            failures.append(f"contains forbidden text: {forbidden_text!r}")

    failures.extend(_validator_contract_failures(case, message, validator_evidence))
    return failures


def _copy_skill(temp_repo: Path) -> Path:
    skill_target = temp_repo / ".agents" / "skills" / "ap-advisor"
    try:
        skill_target.mkdir(parents=True)
        shutil.copy2(REPO_ROOT / "SKILL.md", skill_target / "SKILL.md")
        shutil.copytree(
            REPO_ROOT / "references",
            skill_target / "references",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        scripts_target = skill_target / "scripts"
        scripts_target.mkdir()
        shutil.copy2(
            REPO_ROOT / "scripts" / "validate_topic_code.py",
            scripts_target / "validate_topic_code.py",
        )
    except OSError as exc:
        raise RunnerError(f"cannot stage skill in temporary repository: {exc}") from exc
    return skill_target


def _resolve_executable(command: str) -> str:
    resolved = shutil.which(command)
    if resolved:
        return resolved
    candidate = Path(command)
    if candidate.is_file():
        return str(candidate.resolve())
    raise RunnerError(f"codex executable not found: {command!r}")


def run_codex_case(
    case: EvalCase,
    codex_executable: str,
    timeout_seconds: int,
    use_user_config: bool = False,
) -> tuple[str, ValidatorObservation, str]:
    """Run one case with this skill staged in a fresh temporary Git repository."""

    prompt = case.prompt
    if case.invocation == "explicit":
        prompt = f"$ap-advisor\n\n{prompt}"

    with tempfile.TemporaryDirectory(prefix="ap-advisor-eval-") as temp_dir:
        temp_repo = Path(temp_dir)
        skill_target = _copy_skill(temp_repo)
        try:
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
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RunnerError(f"cannot initialize temporary Git repository: {exc}") from exc
        if git.returncode != 0:
            raise RunnerError(f"git init failed: {git.stderr.strip() or git.stdout.strip()}")

        command = [
            codex_executable,
            "exec",
            "--ephemeral",
            "--json",
            "--sandbox",
            "read-only",
        ]
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
        except subprocess.TimeoutExpired as exc:
            raise RunnerError(f"case {case.id!r}: codex timed out after {timeout_seconds}s") from exc
        except OSError as exc:
            raise RunnerError(f"case {case.id!r}: cannot start codex: {exc}") from exc

    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RunnerError(
            f"case {case.id!r}: codex exited {completed.returncode}: {detail}"
        )
    events = parse_json_events(completed.stdout)
    validator_evidence = extract_validator_evidence(
        events,
        expected_validator_path=skill_target / "scripts" / "validate_topic_code.py",
    )
    return extract_final_message(events), validator_evidence, completed.stderr


def write_results(output_dir: Path, payload: dict[str, Any]) -> Path:
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_path = output_dir / f"behavior-eval-{timestamp}.json"
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise RunnerError(f"cannot write result file {output_path}: {exc}") from exc
    return output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus",
        type=Path,
        default=DEFAULT_CORPUS,
        help="JSONL corpus path (default: evals/cases.jsonl)",
    )
    parser.add_argument(
        "--case",
        dest="case_ids",
        action="append",
        default=[],
        metavar="ID",
        help="select one case by id; repeat to select multiple cases",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="explicitly run selected cases with codex exec (may consume quota)",
    )
    parser.add_argument(
        "--codex-command",
        default="codex",
        help="Codex executable name or path (used only with --run)",
    )
    parser.add_argument(
        "--use-user-config",
        action="store_true",
        help="load the user's config.toml during live runs (ignored by default)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        metavar="SECONDS",
        help="per-case live timeout (default: 300)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "eval-results",
        help="live result directory (created only with --run)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cases = select_cases(load_cases(args.corpus), args.case_ids)
        if not args.run:
            print(
                f"VALID: {len(cases)} selected case(s); corpus-only mode, "
                "no model calls or result writes"
            )
            return 0
        if args.timeout <= 0:
            raise RunnerError("--timeout must be a positive integer")
        codex_executable = _resolve_executable(args.codex_command)

        results: list[dict[str, Any]] = []
        any_assertion_failure = False
        for case in cases:
            print(f"RUN: {case.id}", flush=True)
            message, validator_evidence, stderr = run_codex_case(
                case,
                codex_executable,
                args.timeout,
                use_user_config=args.use_user_config,
            )
            failures = evaluate_case(case, message, validator_evidence)
            any_assertion_failure = any_assertion_failure or bool(failures)
            results.append(
                {
                    "id": case.id,
                    "automated_passed": not failures,
                    "failures": failures,
                    "validator_observed": validator_evidence.observed,
                    "validator_evidence": validator_evidence.as_dict(),
                    "final_message": message,
                    "manual_checks": list(case.manual_checks),
                    "stderr": stderr,
                }
            )
            print(f"{'AUTO-PASS' if not failures else 'AUTO-FAIL'}: {case.id}")

        payload = {
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "corpus": str(args.corpus.resolve()),
            "used_user_config": args.use_user_config,
            "automated_pass": not any_assertion_failure,
            "manual_review_required": any(case.manual_checks for case in cases),
            "results": results,
        }
        output_path = write_results(args.output_dir, payload)
        print(f"RESULTS: {output_path}")
        return 1 if any_assertion_failure else 0
    except RunnerError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"ERROR: runner I/O failure: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
