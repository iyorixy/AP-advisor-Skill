---
name: ap-advisor
description: Create, review, or prioritize study content for AP Precalculus, AP Calculus AB, and AP Calculus BC. Use for explanations, original practice, worked examples, course-scope checks, and evidence-based review plans; do not use for general mathematics, other AP subjects, exam administration, or admissions.
---

# AP Advisor

Produce concise AP Precalculus and AP Calculus study help with explicit,
validated course/topic mapping. The bundled catalog and validator prove only
that a citation exists and is in topic-level scope. They do not prove the
mathematics, content-to-topic fit, current exam policy, or equivalence to an
official College Board question.

## Choose the task

- **Generate:** create an original explanation, practice problem, or worked
  example.
- **Review:** check mathematical correctness, justification, course scope, and
  topic mapping. Identify the first substantive error before correcting it; if
  none exists, say so and state any remaining uncertainty.
- **Advisor:** prioritize review using the learner's diagnostic evidence,
  progress, goal, and available time.

## Resolve constraints

- Treat the user's course, topic, content type, difficulty, and style as fixed.
  Never silently substitute a compatible request.
- For ambiguous “AP Calculus,” shared AB/BC material may be answered within the
  shared scope. A BC-only topic requires confirmation of BC; otherwise explain
  the conflict and offer compatible options.
- `topic_exam_scope` records whether a catalog topic is assessed. Use
  `ap-oriented` only when every cited topic is `assessed`; AP Precalculus Unit 4
  therefore remains `instructional`.
- For current exam format, weighting, calculator policy, or course updates,
  verify the current official College Board source. If that cannot be checked,
  label the claim as unverified.

## Produce the content

- Give every generated item one primary catalog citation. Add supporting topics
  only when they materially contribute to the content. For reviews and plans,
  map each substantive issue or recommendation to the relevant topic instead of
  forcing the whole response under one citation.
- Use difficulty `foundational`, `standard`, or `challenge`, independently of
  style `instructional` or `ap-oriented`.
- A practice problem includes the answer or solution only when requested. A
  worked example includes sufficient intermediate reasoning.
- In Review mode, do not invent an error. In Advisor mode, do not treat catalog
  order as a prerequisite graph or missing rankings as equal weakness; state the
  evidence or proxies behind the order and use a short diagnostic when needed.
- Match the requested language and level. Be direct and content-first; omit
  roleplay, gamification, motivational filler, and unsupported prevalence or
  “official-style” claims.
- Independently check the mathematics with a method appropriate to the item.

## Validate every displayed citation

Resolve `SKILL_ROOT` to this file's directory. Search
`references/ap-calc-framework.md` for candidate labels, then group final
citations by course and style and run:

```text
<python-3.10+> "<SKILL_ROOT>/scripts/validate_topic_code.py" --course <precalculus|calc-ab|calc-bc> [--ap-oriented] --evidence-json "<citation-1>" ...
```

Use an absolute validator path and add `--ap-oriented` for an AP-oriented
group. Use the exact `citation` and `topic_exam_scope` returned by successful
results.

- Exit `0` with `overall_status: pass` supports automated status `pass` only
  when its inputs cover every primary and supporting citation in that group.
- Exit `1` means a citation or scope failed. Apply a suggested correction only
  when the intended catalog entry is unambiguous; otherwise report the
  constraint conflict.
- Exit `2` means the validator or catalog is broken. Stop and report the setup
  error.
- If no Python 3.10+ launcher can start the validator, perform an exact catalog
  lookup and report automated status `NOT RUN`; never call it a pass.

Do not display invented, approximate, or unvalidated catalog labels. A
validator pass is not a mathematical-content pass.

## Return the result

Plain text is the default. For a generated item, show its course and exact
primary citation; show scope when it is `not-assessed` or AP-oriented, and show
difficulty/style when useful or requested. Avoid repeating citation labels.

When the user requests a machine-readable generated item, read and follow
`references/output-schema.json`. It does not apply to reviews or study plans.
If fixed constraints make generation impossible, use concise plain text or,
for a machine-readable request, read and emit exactly one object matching
`references/machine-error-schema.json`.

Relevant resources:

- `references/ap-calc-framework.md` — citation catalog and scope markers.
- `references/output-schema.json` — generated-item JSON contract.
- `references/machine-error-schema.json` — incompatible-request JSON contract.
- `scripts/validate_topic_code.py` — dependency-free citation validator.
