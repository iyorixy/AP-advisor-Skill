**English** | [简体中文](./README.zh-CN.md)

# AP Advisor Skills

This repository contains three independently installable Codex Skills. Their
runtime scripts use Python 3.10+ and the standard library only:

| Skill | Path | Repository scope |
| --- | --- | --- |
| `ap-calculus-advisor` | `ap-calculus-advisor/` | AP Precalculus, AP Calculus AB, and AP Calculus BC, including adaptive Coach support |
| `ap-psychology-advisor` | `ap-psychology-advisor/` | AP Psychology study support and adaptive Coach under the current five-unit framework |
| `ap-biology-advisor` | `ap-biology-advisor/` | AP Biology study support and adaptive Coach under the current Fall 2025 framework |

All supported courses now provide Generate, Review, Advisor, and Coach modes.
The mathematics Skill includes a maintained, original diagnostic bank, optional
local learner state, and a deterministic next-item selector for selected
misconceptions in AP Precalculus Units 1–4, AP Calculus AB Units 1–8, and AP
Calculus BC. BC reuses shared AB content and adds selected BC-only coverage in
Units 6–10. The bank currently contains 96 items across 32 diagnostic patterns;
these are maintained samples, not exhaustive Topic coverage. Biology
and Psychology instead create original items on demand and keep their Coach
state in the conversation; they do not claim a static bank or persistent
profile.

Framework baselines were checked for the 2026–27 school year against the
[College Board course-change table](https://apcentral.collegeboard.org/courses/how-ap-develops-courses-and-exams/course-changes-overview):

| Course | Repository baseline |
| --- | --- |
| AP Precalculus | Fall 2026 CED and clarifications |
| AP Calculus AB/BC | Fall 2020 CED with Fall 2026 clarifications |
| AP Psychology | Fall 2025 five-unit CED with October 2025 clarifications |
| AP Biology | Fall 2025 CED with June 2025 and June 2026 clarifications |

Source metadata was last checked August 28–31, 2026. Exam-format and policy
facts remain time-sensitive and are rechecked against current official sources.

## Adaptive Coach loop

In Coach mode, the Skill uses the learner's actual work to identify the first
substantive error, separate observations from a bounded misconception
hypothesis, give one minimal hint, and wait for the learner's response. A
corrected attempt advances to one unseen same-form confirmation; an independent
success advances to one unseen cross-representation or cross-context transfer.
Only an independent unseen transfer at hint level 0 can pass the specific
intervention. It never establishes Unit-wide mastery.

Examples:

```text
$ap-calculus-advisor Coach me on this AP Precalculus Unit 2 solution, one hint at a time.
$ap-calculus-advisor Coach me on this AP Calculus BC Unit 10 attempt, one hint at a time.
$ap-psychology-advisor Coach me from this AP Psychology response, one hint at a time.
$ap-biology-advisor Coach me from this AP Biology response, one hint at a time.
```

Maintained and on-demand items are original practice, not AP Classroom,
Progress Check, Practice Exam, or other secure College Board material. Hidden
answers stay out of learner-facing responses. Mathematics-bank difficulty
labels are `provisional` until real, de-identified learner data support
calibration.

## Privacy and optional local state

Every Coach is session-only by default and writes no local files. The Biology
and Psychology Coaches remain session-only. For the three mathematics courses,
local persistence requires both explicit authorization and a caller-supplied
data directory outside this repository. The state stores a pseudonymous profile
ID, course, attempts, evidence, hint/independence fields, and a review queue; it
does not request names or email addresses.

Use an explicit external directory (replace the examples below with paths
chosen by the caller). Replace `calc-ab` with `precalculus` or `calc-bc` when
initializing another mathematics course:

```powershell
python ap-calculus-advisor/scripts/update_learner_state.py --data-dir "D:\learner-data\calc-ab-demo" `
  --as-of "2026-08-31T12:00:00Z" --evidence-json init --profile-id demo_profile --course calc-ab
python ap-calculus-advisor/scripts/update_learner_state.py --data-dir "D:\learner-data\calc-ab-demo" `
  --as-of "2026-08-31T12:10:00Z" --evidence-json record --attempt-file attempt.json
python ap-calculus-advisor/scripts/update_learner_state.py --data-dir "D:\learner-data\calc-ab-demo" `
  --as-of "2026-08-31T12:10:00Z" --evidence-json queue
```

`clear-test-profile` works only for a directory initialized with `--test-data`
and removes only the recognized files for the exact profile. It is not a
general data-deletion command. Keep real learner data outside the repository
and do not commit it.

```powershell
python ap-calculus-advisor/scripts/update_learner_state.py --data-dir "D:\learner-data\calc-ab-test" `
  --evidence-json init --profile-id test_profile --course calc-ab --test-data
python ap-calculus-advisor/scripts/update_learner_state.py --data-dir "D:\learner-data\calc-ab-test" `
  --evidence-json clear-test-profile --profile-id test_profile
```

## Install and invoke

Inside Codex, use Skill Installer:

```text
$skill-installer Install the skill at path ap-calculus-advisor from iyorixy/AP-advisor-Skill as ap-calculus-advisor.
$skill-installer Install the skill at path ap-psychology-advisor from iyorixy/AP-advisor-Skill as ap-psychology-advisor.
$skill-installer Install the skill at path ap-biology-advisor from iyorixy/AP-advisor-Skill as ap-biology-advisor.
```

The repository root contains development-only tests and release evidence, so it
is intentionally not an installable Skill. The three paths above keep those
files out of user installations.

The Skills are available on the next turn. If the Codex UI does not refresh,
restart Codex. Examples:

```text
$ap-calculus-advisor Review this AP Calculus BC solution and identify the first substantive error.
$ap-calculus-advisor Coach me through this AP Precalculus Unit 3 attempt one step at a time.
$ap-calculus-advisor Coach me through this AP Calculus AB Unit 6 attempt one step at a time.
$ap-calculus-advisor Coach me through this AP Calculus BC Unit 9 attempt one step at a time.
$ap-psychology-advisor Coach me from this AP Psychology response, one hint at a time.
$ap-biology-advisor Coach me from this AP Biology response, one hint at a time.
```

These commands cover standalone GitHub installation. For distribution through
the universal plugin directory, current [OpenAI documentation](https://developers.openai.com/codex/skills)
recommends packaging reusable multi-skill products as a plugin; that is a
separate release channel.

## Verify a checkout

Run from the repository root (`python3` may replace `python`):

```bash
python ap-calculus-advisor/scripts/validate_topic_code.py --self-check --evidence-json
python ap-psychology-advisor/scripts/validate_topic_code.py --self-check --evidence-json
python ap-biology-advisor/scripts/validate_topic_code.py --self-check --evidence-json
python scripts/run_evals.py --self-check --evidence-json
python -m unittest discover -s tests -v
python scripts/check_release.py --evidence-json
```

The three validator self-checks cover each Skill's mapping and boundary package.
The release gate additionally validates all Coach protocol artifacts, the
mathematics assessment contract, misconception/item cross-references, math
audit hashes, learner-state safety, selector determinism, behavioral review
thresholds, Python compilation and standard-library imports, unit tests, and
the installed skill-creator validator. Treat the checkout as verified only when
every command exits `0` and the last command emits lower-case
`"overall_status":"pass"`.

The mathematics selector deliberately uses transparent rules rather than BKT,
IRT, vector retrieval, or empirical mastery probabilities. Aggregate
calibration exports remain descriptive and report `insufficient_data` below
their sample minimum; future calibration requires real, consented,
de-identified response data and a separate review.

## License and AP notice

MIT. “AP” is a College Board trademark. This project is not an official College
Board publication and is not endorsed by College Board. For time-sensitive
exam information, use current official College Board sources.
