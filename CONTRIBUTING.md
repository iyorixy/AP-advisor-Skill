# Contributing to AP Advisor

Thanks for considering a contribution. This project is intentionally small
and dependency-free — please keep changes in that spirit.

## Ways to contribute

### 1. Propose support for another AP subject

Adding a framework file alone does not add subject support. Treat a new subject
as a coordinated integration: define its course and exam boundaries, then
update Skill routing, validator course configuration, machine-readable schemas,
tests, behavior evals, and documentation together. Do not reuse
Calculus-specific planning assumptions without subject-specific review. A
catalog-only contribution must not claim that the subject is supported.

Document the source and effective school year for any catalog data. Keep the
catalog limited to the labels and scope metadata needed by the Skill; do not
copy a complete Course and Exam Description into the repository.

### 2. Correct or refine the existing outline

If you spot a unit/topic name that's wrong, out of order, or missing,
open a PR editing `references/ap-calc-framework.md` directly. Keep the
existing two-space/four-space indentation style — `scripts/validate_topic_code.py`
parses the file structurally, so formatting matters. After editing, re-run
the validator's test cases (see below) to make sure parsing still works.

### 3. Improve the validator script

`scripts/validate_topic_code.py` is standard-library-only Python 3.10+ — please
keep it that way (no `pip install` dependencies). Before submitting a
change, run the test suite:

```bash
# macOS/Linux
python3 -m unittest discover -s tests -v
python3 scripts/run_behavior_evals.py

# Windows
py -3 -m unittest discover -s tests -v
py -3 scripts/run_behavior_evals.py
```

If you change the matching or parsing logic, add a test case covering the
edge case you're fixing to `tests/test_validate_topic_code.py` — it's plain
`unittest`, no extra dependencies.

### 4. Change Skill behavior

When changing routing, scope, output, review, or advisor instructions, add or
update a case in `evals/cases.jsonl`. Keep automated assertions limited to
stable invariants; put semantic judgments that need human review in
`manual_checks`. `must_contain` and `must_not_contain` are literal,
case-insensitive substring checks, so do not use them to judge semantic
negation (for example, "not equally weak").

Text cases with `validator_call: true` must also declare
`validator_course` and `validator_ap_oriented`. Every JSON success case must
declare a `json_contract` containing the prompt-fixed course, type, difficulty,
style, primary topic/scope, and exact supporting-topic list. The runner compares
both the returned object and validator evidence against that case contract; it
must not let the model redefine its own expected values. When a prompt forbids
optional JSON content keys such as `solution` or `final_answer`, declare them in
`forbidden_content_fields`; do not put JSON key names in `must_not_contain`,
which searches all string values as well as keys. Do not weaken the
evidence checks to command-name or keyword detection: only completed
`--evidence-json` runs with a matching staged-script path, course, mode, input
multiset, exit code, and output envelope may support
`citation_validation.automated_status=pass`. All citations for one case share
one course/style group and must be covered by one successful grouped run.

For plain-text cases this proves the command course/mode and exact visible-text
occurrences under the runner's conservative parser, not the semantics of
surrounding free-form prose or the final renderer. Raw HTML and Markdown links,
images, or reference definitions are rejected; the runner automatically appends
a manual course/style/scope and rendered-visibility check to these cases. JSON
`not_run` may follow only strictly recognized shell-level failures for every
supported launcher family before Python starts.

The completed-command payload is a Codex CLI compatibility boundary: if its
field shape changes, update the parser and fixtures together and keep the
default fail-closed. Add adversarial tests for any event-field or
command-parsing change.

`scripts/run_behavior_evals.py` validates the corpus only and does not invoke a
model by default. To run one live case deliberately, use an installed,
authenticated Codex CLI:

```bash
python scripts/run_behavior_evals.py --run --case CASE_ID
```

Live runs may consume account usage and write ignored results under
`eval-results/`. They use a temporary read-only repository and ignore the
user's `config.toml` by default; pass `--use-user-config` only when a custom
provider or model configuration is required. Live runs are not part of CI.

## Style

- Keep all Python scripts standard-library-only. The optional live behavior
  eval may call the external Codex CLI; the installed Skill does not depend on
  it.
- Keep `SKILL.md` instructions concise and imperative — it's read by an AI
  agent, not a human end user.
