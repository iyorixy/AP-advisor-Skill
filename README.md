**English** | [简体中文](./README.zh-CN.md)

# AP Advisor

A dependency-free Codex Skill for AP Precalculus, AP Calculus AB, and AP
Calculus BC generation, review, and evidence-based study intervention.

The Skill keeps four claims separate:

1. an internal content-Topic label matches exactly;
2. the Topic and high-risk method fit the requested course;
3. mathematical practices and exam-task features are stated correctly;
4. the mathematics and teaching behavior pass human review.

A Topic-validator receipt proves only (1) and the recorded Topic scope. It is
not a mathematical or behavior pass.

## Content model

`references/ap-calc-framework.md` is a compact matching catalog.
`references/ap-content-boundaries.json` adds only decision-changing constraints:
official-source metadata, high-risk methods, AB/BC dependencies, exclusions,
and the independent mathematical-practice dimension. It intentionally does not
copy the CED.

Styles have distinct meanings:

- `instructional`: course learning;
- `assessed-topic`: every mapped Topic is assessed, without an exam-task claim;
- `exam-oriented`: also fixes question type, calculator condition,
  representation(s), and justification requirement.

The old `ap-oriented` token is accepted only as a deprecated alias for
`assessed-topic`.

Advisor mode uses learner work, accuracy, time, error process, and uncertainty
to choose one to three interventions. Each has a reason, bounded practice, an
exit standard, and an unseen transfer retest. No retest result means no mastery
claim.

## Install

Copy this directory to `~/.agents/skills/ap-advisor` or a project-local
`.agents/skills/ap-advisor`. Runtime requires Python 3.10+ and the standard
library only.

## Deterministic checks

```bash
python -m unittest discover -s tests -v
python scripts/run_behavior_evals.py
```

The second command validates only `evals/cases.jsonl`; it never invokes a model.

The validator compares the entire citation after Unicode NFKC normalization:

```bash
python scripts/validate_topic_code.py \
  --course calc-bc --assessed-topic --evidence-json \
  "Unit 6, Topic 6.11 — Integrating Using Integration by Parts"
```

Exit codes are `0` pass, `1` mapping/content failure, and `2` setup/data error.

## Behavior evaluation and adjudication

Live execution is explicit and may consume account usage:

```bash
python scripts/run_behavior_evals.py --run --case CASE_ID
```

The runner validates the final output and directly calls the bundled validator;
it does not trust shell commands, launcher attempts, or command-event evidence.
Saved final outputs can be evaluated without another model call:

```bash
python scripts/run_behavior_evals.py \
  --responses responses.jsonl \
  --adjudications adjudications.jsonl
```

Each response line is:

```json
{"case_id":"CASE_ID","final_output":"..."}
```

Each adjudication line records who reviewed each check, when, and why:

```json
{"case_id":"CASE_ID","reviewer":"name","reviewed_at":"2026-08-27T12:00:00Z","checks":[{"id":"manual-1","status":"pass","evidence":"Checked the derivative independently."}]}
```

Statuses are intentionally separate:

- `CONTRACT-PASS`: deterministic final-output checks passed;
- `MANUAL REVIEW REQUIRED`: at least one manual check is missing;
- `PASS`: contract and every manual check passed;
- `FAIL`: the contract or any manual check failed;
- `NOT RUN`: no model behavior was executed.

GitHub Actions runs deterministic tests only, on Linux and Windows. Live results
are written to ignored `eval-results/` files.

## License

MIT. “AP” is a College Board trademark. This project is neither published nor
endorsed by College Board; verify current exam-critical facts against current
official sources.
