**English** | [简体中文](./README.zh-CN.md) | [繁體中文](./README.zh-TW.md)

# AP Advisor Skills

This repository contains three independently installable Codex Skills. Their
runtime scripts use Python 3.10+ and the standard library only:

| Skill | Path | Repository scope |
| --- | --- | --- |
| `ap-calculus-advisor` | `ap-calculus-advisor/` | AP Precalculus, AP Calculus AB, and AP Calculus BC, including adaptive Coach support |
| `ap-psychology-advisor` | `ap-psychology-advisor/` | AP Psychology study support and adaptive Coach under the current five-unit framework |
| `ap-biology-advisor` | `ap-biology-advisor/` | AP Biology study support and adaptive Coach under the current Fall 2025 framework |

These are workflow Skills, not standalone tutoring apps or replacements for a
subject expert. They guide the host model through an evidence-first AP workflow,
load course-specific references only when needed, and use local validators for
claims that can be checked mechanically.

## GPT-6 Astra support

All three Skills include an Astra-aware interaction contract: complete the
requested deliverable, ask only decision-changing questions, honor corrections
and mode changes, and keep Coach turns to one action awaiting real learner work.
This follows the [official Astra prompting guidance](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-6-astra),
checked September 5, 2026. The instructions also work with other capable hosts.

Select `gpt-6-astra` in a host that offers it. A Skill does not switch models or
grant account access. For Codex configuration, set these keys in your chosen
`config.toml`, updating existing values rather than duplicating them:

```toml
model = "gpt-6-astra"
model_reasoning_effort = "medium"
```

See the [Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).
`medium` is this project's starting suggestion, not a measured optimum. Preserve
an existing suitable effort when migrating; use `low` for routine follow-ups
or `high` for difficult reviews if your host supports them. Astra's documented
efforts exclude `none` and `minimal`; available controls depend on the host.
See the [model specification](https://developers.openai.com/api/docs/models/gpt-6-astra).

Each course now has an on-demand evidence-review reference for images, source
or model interpretation, and item quality. It separates readable evidence from
uncertain transcription, checks subject reasoning before Topic metadata, and
checks generated questions for sufficient givens and a defensible answer.
Coach protocols preserve affected versus unaffected evidence after corrections
and keep compact session checkpoints without exposing hidden keys. Responses
preserve English, Simplified Chinese, or Traditional Chinese as requested.

## What the Skills actually do

| Mode | Behavior |
| --- | --- |
| **Generate** | Create an original explanation, practice item, stimulus, data set, or worked example within the requested course, Topic, task type, difficulty, language, and answer-visibility constraints. |
| **Review** | Check the supplied work and name the first substantive error and its downstream consequence; if no substantive error is present, say so instead of inventing one. |
| **Advisor** | Use the learner's evidence to prioritize one to three bounded tasks, each with a reason, a practice action, and an observable exit standard. |
| **Coach** | Run an interactive one-item loop: diagnose, give one minimal hint, wait for real learner work, confirm the correction, and test transfer before passing the intervention. |

The primary users are AP students who can share an actual attempt and want
targeted feedback, one-hint-at-a-time coaching, or original AP-aligned practice.
The Skills preserve the requested language, so they also fit bilingual learning
settings. Teachers, tutors, and content reviewers can use Generate, Review, and
scope checks as a second-pass aid. They are not an official scoring service, an
AP Classroom substitute, a general admissions advisor, or—especially for
Psychology—a personal clinical tool.

The three implementations deliberately differ:

| Skill | Course-specific implementation |
| --- | --- |
| Mathematics | A maintained original bank of 96 items across 32 diagnostic patterns: 8 patterns for Precalculus, 16 for Calculus AB, and 8 selected BC-only patterns. Every pattern has a diagnostic, same-form confirmation, and transfer item. AB covers two maintained patterns per unit across Units 1–8; Precalculus does the same across Units 1–4; BC reuses shared AB content and adds selected coverage in Units 6–10. The bank is not exhaustive Topic coverage. |
| Psychology | Original items generated on demand across the current five Units, including concept application, research design, data/statistics, AAQ, and EBQ work. There is no claimed static bank or cross-session learner profile. |
| Biology | Original items generated on demand across the current eight Units, including mechanisms, models, investigations, data/statistics, MCQ, and the six current FRQ task families. There is no claimed static bank or cross-session learner profile. |

Framework baselines were checked for the 2026–27 school year against the
[College Board course-change table](https://apcentral.collegeboard.org/courses/how-ap-develops-courses-and-exams/course-changes-overview):

| Course | Repository baseline |
| --- | --- |
| AP Precalculus | Fall 2026 CED and clarifications |
| AP Calculus AB/BC | Fall 2020 CED with Fall 2026 clarifications |
| AP Psychology | Fall 2025 five-unit CED with October 2025 clarifications |
| AP Biology | Fall 2025 CED with June 2025 and June 2026 clarifications |

Exam-oriented AP Precalculus support covers Units 1–3 for the May 2027 MCQ and
all four named FRQ models—Function Concepts, Modeling a Non-Periodic Context,
Modeling a Periodic Context, and Symbolic Manipulations. Unit 4 remains
instructional-only.

Source metadata was last checked August 28–September 3, 2026. Exam-format and policy
facts remain time-sensitive and are rechecked against current official sources.

## End-to-end workflow

1. **Route:** select Generate, Review, Advisor, or Coach from the user's intent.
2. **Freeze constraints:** keep the requested course, Topic, task type, difficulty,
   language, answer visibility, and supplied evidence fixed; surface a conflict
   instead of silently changing one.
3. **Load only the needed contract:** use the course catalog and boundary package,
   plus the assessment-task reference for exam-oriented work or the session
   protocol for Coach; load the evidence-review reference for visual or complex
   source work and generated assessment items.
4. **Reason, map, and validate:** solve or review the subject matter independently,
   map content and Practice separately, then run the course validator for every
   displayed Topic and declared exam-task contract.
5. **Respond at the requested horizon:** return the content, first-error review,
   one-to-three-task Advisor plan, or exactly one Coach action. Keep state in the
   conversation unless the separate mathematics opt-in persistence contract is
   satisfied.

## Adaptive Coach loop

Coach is evidence-adaptive rather than score-adaptive. It does not infer a
misconception from a low score, a wrong option, slow work, or a Topic label
alone. The loop is:

1. Start from the complete prompt/stimulus and the learner's real work. If the
   necessary evidence is missing, request only the missing artifact or offer one
   original diagnostic item, then wait.
2. Identify the earliest substantive break. Keep the observation, one bounded
   cause hypothesis, a plausible alternative, and the remaining uncertainty
   separate.
3. Give the least revealing useful hint. Hint level 0 is the prompt only; levels
   1–3 progress from a feature cue to an incomplete local setup to one modeled
   blocked step. Give only one level at a time and never invent the next learner
   response.
4. After self-correction, give one unseen same-form confirmation without its
   answer. After an independent success at hint level 0, give one unseen transfer
   that changes a meaningful context, representation, or task form.
5. Mark only the specific intervention `passed` after an independent unseen
   transfer at hint level 0 meets its stated exit standard. Guided work remains
   provisional, and one passed intervention never establishes Unit or course
   mastery.

Mathematics can use its audited bank and deterministic selector for the next
maintained item. Biology and Psychology generate original confirmation and
transfer items on demand. Every implementation returns at most one new Coach
item per turn.

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

## Course validation and hallucination guardrails

The repository combines model instructions with machine-checkable controls:

- Exact Topic citations are normalized with Unicode NFKC and must match the
  internal framework catalog in full. The validators return the canonical
  citation and assessment scope; malformed, invented, or wrong-course mappings
  fail.
- Content Topic and Mathematical/Science Practice are separate claims. When the
  evidence establishes only a cross-course Practice, the Skills leave the Topic
  `not established` instead of guessing one.
- Boundary packages check assessed versus instructional scope, registered
  exclusions and high-risk methods, legacy framework markers, and exam-task
  contracts. Full-task validation checks the required Practice/representation
  families rather than treating a Topic match as proof of an AP task.
- Evidence rules forbid invented learner work, timing, confidence, independence,
  studies, data, procedures, statistics, citations, scoring guides, and mastery
  claims. Synthetic practice stimuli and data must be labeled synthetic.
- Tasks are original and do not reproduce secure AP Classroom, Progress Check,
  or Practice Exam material. Numeric scoring of released work requires the
  matching prompt and official scoring guide for the same administration and
  question; otherwise feedback stays explicitly unscored.
- Hidden answers, solutions, distractor diagnoses, item links, and selector
  rationales stay out of learner-facing Coach turns. Asking for a full solution
  is allowed, but that assisted response cannot count as independent evidence.
- Self-checks, unit tests, schemas, math-audit hashes, behavioral cases, and the
  release gate check that these contracts remain internally consistent.

These controls reduce common hallucination paths; they do not make model output
infallible. A validator `pass` confirms mapping and declared boundary metadata,
not the subject-matter reasoning, teaching quality, official rubric alignment,
or the current truth of time-sensitive exam policy. The Skills therefore require
independent subject checking and a fresh official-source check for changeable
exam facts.

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

Codex detects newly installed Skills automatically. If one does not appear,
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

These are local checks, including consistency checks on recorded behavioral
reviews; they do not run a fresh Astra evaluation or measure learning gains.
Historical review records remain historical evidence; Astra-specific behavior
has not yet been evaluated with fresh model outputs.

The mathematics selector deliberately uses transparent rules rather than BKT,
IRT, vector retrieval, or empirical mastery probabilities. Aggregate
calibration exports remain descriptive and report `insufficient_data` below
their sample minimum; future calibration requires real, consented,
de-identified response data and a separate review.

## License and AP notice

MIT. “AP” is a College Board trademark. This project is not an official College
Board publication and is not endorsed by College Board. For time-sensitive
exam information, use current official College Board sources.
