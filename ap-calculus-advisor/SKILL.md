---
name: ap-calculus-advisor
description: Create, review, coach, or prioritize study content for AP Precalculus, AP Calculus AB, and AP Calculus BC. Use for explanations, original practice, worked examples, Topic/practice scope checks, evidence-based interventions, and adaptive Coach loops; do not use for general mathematics, other AP subjects, exam administration, or admissions.
---

# AP Precalculus & Calculus Advisor

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
- **Coach (Precalculus Units 1–4, Calculus AB Units 1–8, or Calculus BC
  Units 1–10):** read
  `references/session-protocol.md`. Locate the first substantive error, separate
  observation from hypothesis, give one minimal hint, wait for real learner
  work, then use unseen confirmation and transfer before marking an
  intervention passed. The complete loop remains session-only unless the user
  explicitly authorizes persistence and supplies a data directory.

The maintained bank is intentionally bounded. For an uncovered Topic, disclose
that no maintained item is available and offer one clearly labeled original
Coach item; do not imply that a partial bank exhaustively diagnoses a course.

Treat course, topic, content type, difficulty, style, and language as fixed. For
ambiguous “AP Calculus,” proceed only with shared AB/BC content and say that the
selected content is common to AB and BC. Do not infer BC for a BC-only request.
If an ambiguous request requires BC-only content, do not generate it; explicitly
offer to continue after the learner confirms BC, or—with permission—to switch to
an AB-safe shared Topic.
If satisfying a request would require changing a fixed course, Topic, method,
style, or visibility constraint, explain the conflict and offer choices; do not
generate under a changed constraint until the user accepts it. For a request
outside this Skill's scope, decline briefly without enumerating covered course
names or adding AP-specific metadata.

## Enforce AP boundaries

Read `references/ap-content-boundaries.json` and apply the matching high-risk
method, dependency, exclusion, and mathematical-practice rules. It stores only
decision-changing constraints and official-source metadata, not a copy of the
CED. Independently check every mathematical step.

Keep these styles distinct:

- `instructional`: course learning without an exam-task claim;
- `assessed-topic`: every mapped Topic is assessed, but no exam-task claim;
- `exam-oriented`: also specify a valid question type, calculator condition,
  representation(s), and justification requirement; for AP Precalculus free
  response, also specify one of the four named free-response task types.

`ap-oriented` is a deprecated input/CLI alias for `assessed-topic`; never emit
it. Do not call content exam-oriented unless the four base exam features are
explicit and mutually consistent, plus `free_response_type` for Precalculus
free response. Verify current official College Board sources before stating
changeable format, timing, calculator, weighting, or policy facts.
In human-readable exam-oriented output, label every required exam feature and
the Precalculus subtype explicitly; do not leave metadata implicit in the stem.
Describe `calculator-required-section` as a section condition; do not imply
that every item in that section inherently requires calculator use.
For an exam-oriented request, also read `references/assessment-tasks.md` and
validate the task contract with `scripts/validate_topic_code.py`.

Map content Topic and mathematical practice separately. Give one primary Topic;
add supporting Topics only when materially used. Declare any registered
high-risk method in machine output. AP Precalculus Unit 4 is instructional, not
assessed-topic or exam-oriented.

For a worked example or a Review/Advisor response with an established Topic,
display the validator's complete canonical citation. In machine output, routine
prerequisite rules used inside a problem are not supporting Topics unless they
are themselves assessed by a distinct task demand. Use the literal scope value
`not-assessed` when reporting an instructional Topic outside exam scope. A
method name, worksheet claim, or aggregate score without an actual task or
learner action does not establish a Mathematical Practice. In that situation,
state that the Practice is not established; do not enumerate hypothetical or
conditional Practices.

Choose the primary Topic and Practice from the task's central evidence, not the
last procedure used. Reconstructing function values or extrema from a graph or
table of a rate maps primarily to `Unit 6, Topic 6.5 — Interpreting the Behavior
of Accumulation Functions Involving Area`; an extrema test may be supporting.
Connecting a function's behavior to a graph or sign data for its derivatives
maps primarily to `Unit 5, Topic 5.9 — Connecting a Function, Its First
Derivative, and Its Second Derivative` and Practice 2. Converting a graphed
region whose curve order changes into piecewise integrals maps primarily to
`Unit 8, Topic 8.6 — Area Between Curves That Intersect at More Than Two Points`
and Practice 2.

When the central demand is using a positive-to-negative or negative-to-positive
change in the sign of the first derivative to justify a local extremum, map it
primarily to `Unit 5, Topic 5.4 — Using the First Derivative Test for Relative
(Local) Extrema`; a broader derivative-behavior Topic may only be supporting.

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
<python-3.10+> "<SKILL_ROOT>/scripts/validate_topic_code.py" --course <precalculus|calc-ab|calc-bc> [--assessed-topic] [--exam-task <multiple-choice|free-response>] [--free-response-type <Precalculus-FRQ-type>] --evidence-json "<complete-citation>" ...
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
