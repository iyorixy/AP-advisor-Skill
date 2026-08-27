# Contributing

Keep AP Advisor small and standard-library-only.

## Scope and data

Adding a catalog file does not add subject support. A subject integration must
cover routing, Topic/practice boundaries, schemas, tests, and behavior cases.

Keep `ap-calc-framework.md` to concise internal labels. Put only
decision-changing high-risk methods, dependencies, exclusions, and official
source metadata in `ap-content-boundaries.json`; do not copy the CED. Record
source URL, check date, school year, applicable exam administration, and a
useful locator. Internal labels are not official quotations.

`ap-oriented` is accepted only at compatibility inputs. New code and corpus data
use `assessed-topic`. Reserve `exam-oriented` for an item that explicitly fixes
question type, calculator condition, representation(s), and justification.

## Tests

```bash
python -m unittest discover -s tests -v
python scripts/run_behavior_evals.py
python -m json.tool references/output-schema.json
python -m json.tool references/machine-error-schema.json
python -m json.tool references/ap-content-boundaries.json
```

Add a focused `unittest` for every matching or boundary change. The runtime
must remain compatible with Python 3.10+ and have no third-party dependency.

Behavior cases belong in `evals/cases.jsonl`. Automated expectations should be
stable final-output invariants. Semantic checks—including mathematical
correctness—belong in `manual_checks`; every check is adjudicated separately.
The runner itself invokes the validator, so do not add command-event, shell, or
launcher assertions.

Default corpus validation never invokes a model. Live evaluation is deliberate,
may consume usage, and is never part of CI:

```bash
python scripts/run_behavior_evals.py --run --case CASE_ID
```

Saved responses and adjudications can close the loop without rerunning a model;
see `README.md` for their JSONL shapes. Behavior `PASS` requires
`CONTRACT-PASS` plus a traced pass for every manual check. A missing or failed
manual mathematics check can never produce behavior `PASS`.
