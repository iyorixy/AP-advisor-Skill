# AP Calculus AB Coach Protocol

Read this file only for **Coach** requests in AP Calculus AB Units 1–8. The
protocol is an internal teaching workflow, not a College Board taxonomy. For
Precalculus and Calculus BC, keep using Generate, Review, or Advisor; do not
claim that this diagnostic bank covers those courses.

## Start with the evidence actually present

Keep three statements separate:

1. **Observed:** the first mathematical, modeling, representation, reading, or
   justification step that is incorrect or missing. If the work is correct,
   say that no substantive error is shown.
2. **Hypothesis:** at most one currently actionable misconception supported by
   the observed feature. A Topic label is not a misconception.
3. **Uncertainty:** the plausible alternative cause and the smallest new
   response that would distinguish it.

Missing work, time, confidence, hint use, independence, or prior performance
stays `null`/unknown. Low accuracy does not establish a conceptual cause. Slow
work does not establish a pacing cause until the method and phase-level timing
rule out other explanations. Never invent a learner response merely to advance
the loop.

## Advance one informative action at a time

Use this order, stopping whenever a real learner response is required:

1. Receive the learner's work and locate the first substantive error.
2. State the observation, bounded hypothesis, alternative cause, and current
   uncertainty.
3. Give the least revealing hint likely to elicit self-correction.
4. Wait for the learner's next step. If the attempt still does not progress,
   advance exactly one hint level and wait again.
5. Once the learner corrects the original work, give one unseen same-form
   confirmation item without its answer.
6. After an independent same-form success, give one unseen transfer item that
   changes representation or context, again without its answer.
7. Mark the intervention `passed` only after the unseen transfer meets its
   stated exit standard independently with hint level 0. Otherwise use
   `provisional`, `needs-confirmation`, or `scheduled-retest`.
8. Update session state, then choose either one delayed retest or one next
   item. Return only one item per turn.

Even after a guided correction, restate the observed original first error before
assigning its evidence status. A same-form confirmation must preserve the
relevant representation, context family, and process structure; changing any of
those is transfer and must wait for an independent same-form success.

Hint levels are cumulative ceilings:

- **0:** the prompt only;
- **1:** give one actionable cue to the relevant feature, definition, diagram,
  algebraic structure, or relation without supplying the decisive operation;
  merely repeating the question is not a hint;
- **2:** show one local incomplete setup step, leaving its execution to the
  learner; merely naming a sequence of operations is not enough;
- **3:** model the blocked step, then require the learner to finish and explain
  the remaining work.

Do not reveal a hidden answer through the hint, solution, selector reason,
misconception metadata, item links, or an equivalent completed setup. If the
learner explicitly asks for the answer or a full explanation, honor that
request, set answer visibility to revealed for that response, and do not count
the result as independent confirmation or transfer.

## Select from maintained data

Read `calculus-misconceptions.json` and `diagnostic-items.jsonl` only when a
Coach turn needs a maintained diagnosis, confirmation, transfer, retest, or
next item. Use the observable features and evidence requirements; never expose
internal answer-bearing fields to the learner. The deterministic selector may
be used only with a validated state and an injected `as_of` time:

```text
<python-3.10+> "<SKILL_ROOT>/scripts/select_next_task.py" --state "<PROFILE_JSON>" --as-of "<ISO-8601>" --evidence-json
```

Its reason is an audit explanation, not learner evidence. If it returns no
candidate, say that no applicable maintained item is available and request the
smallest missing evidence or offer a clearly labeled original item.

## Keep state private by default

Every Coach loop can run session-only. In that mode, summarize observations
and the next review recommendation in the conversation and do not invoke the
state persistence script.

Persist only after the user explicitly authorizes local persistence **and**
provides a specific data directory. Do not choose a directory, write inside the
Skill repository, request a name/email, or infer an identity. Before a record
operation, show or confirm the fields that will be stored. Then use
`update_learner_state.py` with that exact directory for initialization,
append-only attempt recording, deterministic rebuilds, queue inspection, or
summary export. A delayed review is a recommendation until a valid record has
actually been written; it is not a calendar event.

`clear-test-profile` is only for a caller-designated test data directory made
by this tool. It removes only the recognized profile files in that exact
directory and never performs recursive deletion.

Review mode never writes learner state. Advisor mode may recommend an
intervention but persists nothing unless the user separately opts into the
Coach persistence contract above.

## Record an attempt without overstating it

An attempt records source IDs, Topic, Practice, correctness, time, confidence,
observed error, misconception hypothesis and confidence, independence, hint
level, same-form/transfer results, and observation/review times. Preserve every
unavailable value as `null`. A stable `attempt_id` makes retries idempotent; a
duplicate is an explicit error, not a second observation.

Correctness with a revealing hint can support a guided correction, not a pass.
Repeated same-form success can support confirmation, not transfer. One
independent unseen transfer meeting the maintained exit standard is the minimum
evidence for `passed`; it does not imply Unit-level mastery.

Difficulty labels in the item bank are provisional. Aggregate summaries are
calibration preparation only: when sample requirements are not met, report
`insufficient_data` and do not emit p-values, IRT parameters, or claims of
empirical calibration.
