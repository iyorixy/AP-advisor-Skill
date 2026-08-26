**English** | [简体中文](./README.zh-CN.md)

# AP Advisor

A Codex Skill for diagnosing, generating, reviewing, and prioritizing AP
Precalculus, AP Calculus AB, and AP Calculus BC study work.

Its primary Advisor goal is to use a learner's response evidence to locate the
main actionable weakness and recommend one to three justified, executable, and
measurable interventions. The internal Topic catalog and validator are safety
guardrails, not the product goal.

The installed Skill and its deterministic checks require no API key or network
access. The optional live behavior eval uses an installed, authenticated Codex
CLI and may consume account usage. The Skill itself consists of:

- a rules document (`SKILL.md`) that Codex reads and follows,
- an Advisor-only evidence and intervention protocol,
- an internal Topic-mapping outline of the AP course structure, and
- a small, dependency-free Python Topic-mapping validator.

## Why this exists

Accuracy alone does not explain why a learner is struggling. AP Advisor uses
work, error patterns, timing, confidence, goals, and available time to separate
likely conceptual, modeling, procedural, representation, justification,
reading, and pacing problems. It then assigns a small intervention with a
reason and measurable exit standard, followed by an unseen transfer retest.
Without a retest result, it does not claim mastery.

Topic metadata creates two additional failure modes that need a guardrail:

1. **Topic-level catalog scope mixups** — BC-only or non-assessed Topics may be
   presented as compatible with a request that does not support them.
2. **Invented catalog labels** — a model may present a plausible-looking Unit
   and Topic label that does not exist in the internal catalog.

AP Advisor reduces these mapping-metadata risks by checking each displayed
Topic mapping against an internal label catalog and its requested-course
compatibility and topic-level catalog scope. Internal labels are not
official-source citations. The normal path uses the bundled validator; if
Python is unavailable, the Skill requires an exact catalog lookup and reports
automated validation as `NOT RUN`. When a label does not match, the validator
prints nearby catalog candidates; Codex may correct it only when the intended
entry is unambiguous.

Inside the Skill workflow, the validator is invoked with `--evidence-json`.
This produces one versioned object tying the command's course and legacy
`ap-oriented` mode token to every input mapping, exact matched label, Topic
scope, and validator status. Human-readable output remains the validator's
default for direct use.

The validator performs a Unicode-aware normalized exact catalog match and
checks topic-level catalog scope only. It allows case, whitespace, and reasonable
punctuation differences but does not discard added Chinese, Japanese, Cyrillic,
or other letters. A passing result does **not** prove mathematical correctness,
content-to-Topic fit, teaching quality, or compliance with current learning
objectives, exclusions, question types, calculator conditions, representation
mix, rubrics, scoring, or complete exam alignment. Review generated content and
cross-check exam-critical details against the current official College Board
source.

In human-facing prose, the style is called `exam-oriented`. The existing CLI
flag `--ap-oriented`, JSON value `ap-oriented`, and field name
`citation_validation` are retained compatibility terms. Exam-oriented means
only that every mapped Topic is marked `assessed`; it does not add any of the
exam-alignment guarantees listed above.

Difficulty is based on observable demand rather than tone: `foundational`
supplies or recalls immediate prerequisites, follows a short direct reasoning
path, and requires no representation conversion; `standard` assumes routine
prerequisites, links multiple steps, and may require a familiar conversion;
`challenge` combines multiple prerequisites, requires non-routine decisions,
and makes a meaningful representation conversion or justification integral.

## Installation

Copy the `ap-advisor/` folder into your Codex skills directory:

```
mkdir -p ~/.agents/skills
cp -r ap-advisor ~/.agents/skills/ap-advisor
# or, for a project-local skill:
mkdir -p .agents/skills
cp -r ap-advisor .agents/skills/ap-advisor
```

Requires Python 3.10+ (standard library only, no `pip install` needed) on the
machine running the agent, for the validator script.

## Structure

```
ap-advisor/
├── SKILL.md                          # rules the agent follows
├── references/
│   ├── advisor.md                    # Advisor-only diagnostic protocol
│   ├── ap-calc-framework.md          # internal Unit/Topic mapping catalog
│   ├── output-schema.json            # JSON Schema for generated content
│   └── machine-error-schema.json      # JSON Schema for incompatible requests
├── scripts/
│   ├── validate_topic_code.py        # validates mappings against the outline
│   └── run_behavior_evals.py          # validates or explicitly runs eval cases
├── evals/
│   └── cases.jsonl                    # routing and behavior regression cases
├── tests/
│   ├── test_validate_topic_code.py   # validator unit tests
│   └── test_behavior_evals.py         # offline eval-runner tests
├── .github/workflows/test.yml         # deterministic CI only
├── README.md
├── LICENSE
└── CONTRIBUTING.md
```

## Development checks

Run all deterministic checks locally without invoking a model:

```bash
python -m unittest discover -s tests -v
python scripts/run_behavior_evals.py
```

The second command may print `VALID`, but that means only that the eval corpus
is structurally valid. It is not a model-behavior `PASS`. A live behavior eval
that was not explicitly run is `NOT RUN`; live execution requires an installed,
authenticated Codex CLI:

```bash
python scripts/run_behavior_evals.py --run --case CASE_ID
```

Live results are written under `eval-results/`, which is ignored by Git. Status
terms have separate meanings:

- `CONTRACT-PASS`: automated shape, literal, and validator-receipt checks passed.
- `MANUAL REVIEW REQUIRED`: at least one semantic `manual_check` remains
  unadjudicated. This is the overall status even after `CONTRACT-PASS`.
- `FAIL`: an automated contract check failed.
- `NOT RUN`: live model behavior was not executed.

Behavior-level `PASS` is reserved for a result whose automated contract and all
manual items were adjudicated successfully. The current runner has no manual
adjudication input, so it does not issue behavior-level `PASS` by itself. The
lower-case validator receipt `pass` is a separate Topic-mapping contract.

Legacy result fields `automated_passed` and `automated_pass` are retained as
deprecated compatibility aliases for the automated contract boolean. They do
not mean overall behavior `PASS`.

The runner uses a temporary read-only repository and ignores the user's
`config.toml` by default to reduce local configuration variance. Pass
`--use-user-config` only when a custom provider or model configuration is
required. A live case can claim Topic-mapping validator `pass` only when a single
completed grouped validator command reports the required status, integer exit
code, and machine-readable evidence. For JSON cases, that evidence must exactly
match the structured course, style, primary mapping, supporting mappings,
scopes, and prompt-fixed case contract; catalog-looking references embedded in
free-form JSON content are rejected instead of treated as validated. For plain
text, the runner checks the
case's expected course/mode and requires every evidenced canonical mapping to
appear exactly once with no additional catalog mapping; consistency of other
free-form course/style/scope prose and renderer-level mapping visibility remain
manual checks. Raw HTML and Markdown links, images, or reference definitions
are rejected on the automated text-evidence path because they can hide a raw
mapping. Observed or started
commands alone do not count. Tightly recognized shell-level failures for all
supported launcher families may support JSON `not_run`; one missing alias is
insufficient. Exit `2`, unsafe shell composition, framework overrides, missing
output, and contradictory evidence fail closed. This is controlled isolation,
not a fully hermetic environment.
The GitHub Actions workflow never runs live model evals.

## License

MIT — see [LICENSE](LICENSE).

The catalog in
[references/ap-calc-framework.md](references/ap-calc-framework.md) was
assembled for this project to support internal Topic-mapping checks. It is not an
official College Board publication and is not endorsed by or affiliated with
College Board. Some labels retain College Board course terminology for
identification; the catalog does not claim to reproduce or fully represent the
current Course and Exam Description (CED), and its labels are not official
source quotations or citations. "AP" is a College Board trademark.
Verify exam-critical details against the current CED.
