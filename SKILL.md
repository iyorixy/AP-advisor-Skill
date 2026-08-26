---
name: ap-advisor
description: Create, review, or prioritize study content for AP Precalculus, AP Calculus AB, and AP Calculus BC. Use for explanations, original practice, worked examples, topic-level catalog scope checks, and evidence-based learning interventions; do not use for general mathematics, other AP subjects, exam administration, or admissions.
---

# AP Advisor

Use learner evidence to identify the main actionable weakness and prescribe a
small, justified, measurable intervention. Also generate or review concise AP
Precalculus and AP Calculus study content. The bundled Topic catalog and
validator are a safety guardrail: they prove only a normalized exact match to
an internal label and its topic-level catalog scope. An internal label is not
an official-source citation, and a match does not prove the mathematics,
content-to-Topic fit, current exam policy, or equivalence to a College Board
question.

## Choose the task

- **Generate:** create an original explanation, practice problem, or worked
  example.
- **Review:** check mathematical correctness, justification, requested-course
  compatibility at the topic-level catalog scope, and Topic mapping. Identify
  the first substantive error before correcting it; if none exists, say so and
  state any remaining uncertainty.
- **Advisor:** read `references/advisor.md`, then diagnose and prioritize from
  the learner's evidence. Do not load that reference for Generate or Review.

## Resolve constraints

- Treat the user's course, topic, content type, difficulty, and style as fixed.
  Never silently substitute a compatible request.
- For ambiguous “AP Calculus,” shared AB/BC material may be answered within the
  shared scope. A BC-only topic requires confirmation of BC; otherwise explain
  the conflict and offer compatible options.
- Call the style `exam-oriented` in user-facing prose. The existing
  `ap-oriented` CLI and JSON spelling is a compatibility token. It means only
  that every mapped Topic is marked `assessed`; it does not establish AP Exam
  question type, calculator conditions, representation mix, rubric or scoring,
  weighting, timing, or complete exam alignment. AP Precalculus Unit 4
  therefore remains `instructional`.
- For current exam format, weighting, calculator policy, or course updates,
  verify the current official College Board source. If that cannot be checked,
  label the claim as unverified.

## Produce the content

- Give every generated item one primary catalog Topic mapping. Add supporting
  Topics only when they materially contribute to the content. For reviews and plans,
  map each substantive issue or recommendation to the relevant topic instead of
  forcing the whole response under one mapping.
- Assign difficulty from observable demand, independently of style:
  - `foundational`: immediate prerequisites are supplied or recalled, the
    reasoning path is short and direct, and no representation conversion is
    required.
  - `standard`: routine prerequisites are assumed, multiple linked steps are
    required, and a familiar representation conversion may be required.
  - `challenge`: multiple prerequisites must be selected and combined,
    non-routine multi-step decisions are required, and a meaningful
    representation conversion or mathematical justification is integral.
- A practice problem includes the answer or solution only when requested. A
  worked example includes sufficient intermediate reasoning.
- In Review mode, do not invent an error.
- Match the requested language and level. Be direct and content-first; omit
  roleplay, gamification, motivational filler, and unsupported prevalence or
  “official-style” claims.
- Independently check the mathematics with a method appropriate to the item.

## Validate every displayed Topic mapping

Resolve `SKILL_ROOT` to this file's directory. Search
`references/ap-calc-framework.md` for candidate labels, then group final
mappings by course and machine style token and run:

```text
<python-3.10+> "<SKILL_ROOT>/scripts/validate_topic_code.py" --course <precalculus|calc-ab|calc-bc> [--ap-oriented] --evidence-json "<mapping-label-1>" ...
```

Use an absolute validator path and add the compatibility flag `--ap-oriented`
for an exam-oriented group. Use the exact `citation` compatibility field and
`topic_exam_scope` returned by successful results. Matching is normalized exact:
Unicode NFKC/case folding is applied, while whitespace and Unicode punctuation
act as separators. Added letters in any script are not ignored.

- Exit `0` with `overall_status: pass` is a lower-case Topic-mapping validator
  receipt `pass`, and only when its inputs cover every primary and supporting
  mapping in that group.
- Exit `1` means a mapping or scope check failed. Apply a suggested correction
  only when the intended catalog entry is unambiguous; otherwise report the
  constraint conflict.
- Exit `2` means the validator or catalog is broken. Stop and report the setup
  error.
- If no Python 3.10+ launcher can start the validator, perform an exact catalog
  lookup and report automated status `NOT RUN`; never call it `pass`.

Do not display invented, approximate, or unvalidated catalog labels. Validator
receipt `pass` is not a mathematical-content or model-behavior pass.
Behavior-level `PASS` is a separate status that requires both automated
contract success and successful adjudication of every manual item; the current
runner has no manual-adjudication input and cannot issue it itself.

## Return the result

Plain text is the default. For a generated item, show its course and exact
primary catalog Topic mapping; show scope when it is `not-assessed` or
exam-oriented, and show difficulty/style when useful or requested. Avoid
repeating mapping labels.

When the user requests a machine-readable generated item, read and follow
`references/output-schema.json`. It does not apply to reviews or study plans.
If fixed constraints make generation impossible, use concise plain text or,
for a machine-readable request, read and emit exactly one object matching
`references/machine-error-schema.json`.

Relevant resources:

- `references/advisor.md` — read only in Advisor mode.
- `references/ap-calc-framework.md` — internal Topic-mapping catalog and scope
  markers.
- `references/output-schema.json` — generated-item JSON contract.
- `references/machine-error-schema.json` — incompatible-request JSON contract.
- `scripts/validate_topic_code.py` — dependency-free Topic-mapping validator.
