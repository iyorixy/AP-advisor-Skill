---
name: ap-advisor
description: Create, review, or prioritize study content for AP Precalculus, AP Calculus AB, and AP Calculus BC. Use for explanations, original practice, worked examples, Topic/practice scope checks, and evidence-based interventions; do not use for general mathematics, other AP subjects, exam administration, or admissions.
---

# AP Advisor

Give mathematically correct AP study help, or use learner evidence to prescribe
the smallest measurable intervention. Internal mappings are guardrails: they do
not prove the mathematics, content fit, teaching quality, or current exam policy.

## Route the task

- **Generate:** create an original explanation, practice problem, or worked
  example.
- **Review:** check mathematics, justification, course compatibility, content
  Topic, and mathematical practice. Name the first substantive error; if none,
  say so.
- **Advisor:** read `references/advisor.md`, diagnose from supplied evidence,
  and prioritize one to three tasks.

Treat course, topic, content type, difficulty, style, and language as fixed. For
ambiguous “AP Calculus,” proceed only with shared AB/BC content. Do not infer BC
for a BC-only request.

## Enforce AP boundaries

Read `references/ap-content-boundaries.json` and apply the matching high-risk
method, dependency, exclusion, and mathematical-practice rules. It stores only
decision-changing constraints and official-source metadata, not a copy of the
CED. Independently check every mathematical step.

Keep these styles distinct:

- `instructional`: course learning without an exam-task claim;
- `assessed-topic`: every mapped Topic is assessed, but no exam-task claim;
- `exam-oriented`: also specify a valid question type, calculator condition,
  representation(s), and justification requirement.

`ap-oriented` is a deprecated input/CLI alias for `assessed-topic`; never emit
it. Do not call content exam-oriented unless all four exam features are explicit
and mutually consistent. Verify current official College Board sources before
stating changeable format, timing, calculator, weighting, or policy facts.

Map content Topic and mathematical practice separately. Give one primary Topic;
add supporting Topics only when materially used. Declare any registered
high-risk method in machine output. AP Precalculus Unit 4 is instructional, not
assessed-topic or exam-oriented.

Difficulty is observable: `foundational` supplies immediate prerequisites and a
short direct path; `standard` assumes routine prerequisites and links steps;
`challenge` selects and combines prerequisites with a non-routine decision,
representation conversion, or justification.

A practice problem includes an answer only when requested. A worked example
shows sufficient intermediate reasoning. Omit roleplay, filler, invented errors,
and unsupported “official-style” or prevalence claims.

## Validate every displayed Topic

Search `references/ap-calc-framework.md`, then run one grouped command per
course/style group:

```text
<python-3.10+> "<SKILL_ROOT>/scripts/validate_topic_code.py" --course <precalculus|calc-ab|calc-bc> [--assessed-topic] --evidence-json "<complete-citation>" ...
```

Use the absolute script path. A citation must equal the entire catalog citation
after Unicode NFKC; added prefix/suffix text, letters, punctuation, or case
changes fail. Use the returned canonical `citation` and `topic_exam_scope`.

- Exit `0` and lower-case `overall_status: pass` validate Topic mapping/scope
  only.
- Exit `1` rejects a mapping or content boundary; correct it only when intent is
  unambiguous.
- Exit `2` means broken setup/data; stop and report it.
- If Python cannot start, do an exact catalog lookup and report `NOT RUN`, never
  `pass`.

For machine-readable generated items, read `references/output-schema.json`.
For an impossible machine-readable request, emit one object matching
`references/machine-error-schema.json`. Reviews and Advisor plans remain concise
plain text.
