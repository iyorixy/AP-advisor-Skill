**English** | [简体中文](./README.zh-CN.md)

# AP Advisor Skills

This repository contains three Codex Skills that run on Python 3.10+ without
third-party packages:

| Skill | Path | Repository scope |
| --- | --- | --- |
| `ap-calculus-advisor` | repository root | AP Precalculus, AP Calculus AB, and AP Calculus BC; selected adaptive Coach support for Calculus AB |
| `ap-psychology-advisor` | `ap-psychology-advisor/` | AP Psychology under the five-unit framework represented in this repository |
| `ap-biology-advisor` | `ap-biology-advisor/` | AP Biology under the Fall 2025 framework represented in this repository |

The root Skill retains Generate, Review, and Advisor support across its three
math courses. Adaptive Coach v1 is narrower: its maintained misconception
graph, diagnostic bank, learner state, and next-item selector span AP Calculus
AB Units 1–8 but are not an exhaustive Topic bank. Do not infer equivalent
adaptive coverage for Precalculus or BC.

## AP Calculus AB adaptive loop v1

In Coach mode, the Skill uses the learner's actual work to identify the first
substantive error, separate observations from a bounded misconception
hypothesis, give one minimal hint, and wait for the learner's response. A
corrected attempt advances to one unseen same-form confirmation; an independent
success advances to one unseen cross-representation or cross-context transfer.
Only an independent unseen transfer at hint level 0 can pass the specific
intervention. It never establishes Unit-wide mastery.

Example:

```text
$ap-calculus-advisor Coach me on this AP Calculus AB Unit 4 solution. Give only
one minimal hint, wait for my work, and keep the session private.
```

The maintained bank contains original practice, not AP Classroom, Progress
Check, Practice Exam, or other secure College Board material. The Skill hides
bank answers from learner-facing responses by default. Difficulty labels are
`provisional` until real, de-identified learner data support calibration.

## Privacy and optional local state

Coach is session-only by default and writes nothing. Local persistence requires
both explicit authorization and a caller-supplied data directory outside this
repository. The state stores a pseudonymous profile ID, attempts, evidence,
hint/independence fields, and a review queue; it does not request names or email
addresses.

Use an explicit external directory (replace the examples below with paths
chosen by the caller):

```powershell
python scripts/update_learner_state.py --data-dir "D:\learner-data\calc-ab-demo" `
  --as-of "2026-08-31T12:00:00Z" --evidence-json init --profile-id demo_profile
python scripts/update_learner_state.py --data-dir "D:\learner-data\calc-ab-demo" `
  --as-of "2026-08-31T12:10:00Z" --evidence-json record --attempt-file attempt.json
python scripts/update_learner_state.py --data-dir "D:\learner-data\calc-ab-demo" `
  --as-of "2026-08-31T12:10:00Z" --evidence-json queue
```

`clear-test-profile` works only for a directory initialized with `--test-data`
and removes only the recognized files for the exact profile. It is not a
general data-deletion command. Keep real learner data outside the repository
and do not commit it.

```powershell
python scripts/update_learner_state.py --data-dir "D:\learner-data\calc-ab-test" `
  --evidence-json init --profile-id test_profile --test-data
python scripts/update_learner_state.py --data-dir "D:\learner-data\calc-ab-test" `
  --evidence-json clear-test-profile --profile-id test_profile
```

## Install and invoke

Inside Codex, use Skill Installer:

```text
$skill-installer Install the skill at path . from iyorixy/AP-advisor-Skill as ap-calculus-advisor.
$skill-installer Install the skill at path ap-psychology-advisor from iyorixy/AP-advisor-Skill as ap-psychology-advisor.
$skill-installer Install the skill at path ap-biology-advisor from iyorixy/AP-advisor-Skill as ap-biology-advisor.
```

After installation, restart Codex if the Skills are not discovered. Examples:

```text
$ap-calculus-advisor Review this AP Calculus BC solution and identify the first substantive error.
$ap-calculus-advisor Generate an AP Precalculus practice problem without its answer.
$ap-calculus-advisor Coach me through this AP Calculus AB Unit 6 attempt one step at a time.
$ap-psychology-advisor Review this AP Psychology response and identify the first substantive error.
$ap-biology-advisor Review this AP Biology response and identify the first substantive error.
```

## Verify a checkout

Run from the repository root (`python3` may replace `python`):

```bash
python scripts/validate_topic_code.py --self-check --evidence-json
python ap-psychology-advisor/scripts/validate_topic_code.py --self-check --evidence-json
python ap-biology-advisor/scripts/validate_topic_code.py --self-check --evidence-json
python scripts/run_evals.py --self-check --evidence-json
python -m unittest discover -s tests -v
python scripts/check_release.py --evidence-json
```

The three validator self-checks cover each Skill's mapping and boundary package.
The root Calculus adaptive v1 release gate additionally validates required
artifacts, the assessment contract, misconception/item cross-references, math
audit hashes, learner-state safety, selector determinism, behavioral review
thresholds, Python compilation and standard-library imports, unit tests, and
the installed skill-creator validator. Treat the checkout as verified only when
every command exits `0` and the last command emits lower-case
`"overall_status":"pass"`.

The first release deliberately uses transparent rules rather than BKT, IRT,
vector retrieval, or empirical mastery probabilities. Aggregate calibration
exports remain descriptive and report `insufficient_data` below their sample
minimum; future calibration requires real, consented, de-identified response
data and a separate review.

## License and AP notice

MIT. “AP” is a College Board trademark. This project is not an official College
Board publication and is not endorsed by College Board. For time-sensitive
exam information, use current official College Board sources.
