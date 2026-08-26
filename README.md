**English** | [简体中文](./README.zh-CN.md)

# AP Advisor

A Codex Skill for generating, reviewing, and planning AP Precalculus, AP
Calculus AB, and AP Calculus BC study content.

The installed Skill and its deterministic checks require no API key or network
access. The optional live behavior eval uses an installed, authenticated Codex
CLI and may consume account usage. The Skill itself consists of:

- a rules document (`SKILL.md`) that Codex reads and follows,
- a reference outline of the AP course structure, and
- a small, dependency-free Python validator script.

## Why this exists

Ask a generic AI agent to "make me some AP Calc practice problems" and you
often get two failure modes:

1. **Course-scope mixups** — BC-only or non-assessed topics may be presented
   as compatible with a request that does not support them.
2. **Fabricated citations** — the model says "this is a Unit 11, Topic 11.2
   question" when no such topic exists, because it's pattern-matching on
   what an AP unit/topic citation *looks like* rather than checking a real
   source.

AP Advisor reduces these citation-metadata risks by using an internal label
catalog and checking each cited label against the requested course and
topic-level scope. The normal path uses the bundled validator; if Python is
unavailable, the Skill requires an exact catalog lookup and reports automated
validation as `NOT RUN`. When a label does not match, the validator prints
nearby catalog candidates; Codex may correct it only when the intended entry is
unambiguous.

Inside the Skill workflow, the validator is invoked with `--evidence-json`.
This produces one versioned object tying the command's course and AP-oriented
mode to every input citation, exact matched label, topic scope, and overall
status. Human-readable output remains the validator's default for direct use.

The validator checks exact catalog matches and topic-level scope only. A
passing result does **not** prove mathematical correctness, content-to-topic
fit, or compliance with current learning objectives, exclusions, task formats,
or calculator rules. Review generated content and cross-check exam-critical
details against the official CED.

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
│   ├── ap-calc-framework.md          # internal Unit/Topic citation catalog
│   ├── output-schema.json            # JSON Schema for generated content
│   └── machine-error-schema.json      # JSON Schema for incompatible requests
├── scripts/
│   ├── validate_topic_code.py        # validates citations against the outline
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

The second command validates the eval corpus only. A live behavior eval must be
requested explicitly and requires an installed, authenticated Codex CLI:

```bash
python scripts/run_behavior_evals.py --run --case CASE_ID
```

Live results are written under `eval-results/`, which is ignored by Git. The
runner uses a temporary read-only repository and ignores the user's
`config.toml` by default to reduce local configuration variance. Pass
`--use-user-config` only when a custom provider or model configuration is
required. A live case can claim automated citation `pass` only when a single
completed grouped validator command reports the required status, integer exit
code, and machine-readable evidence. For JSON cases, that evidence must exactly
match the structured course, style, primary citation, supporting citations,
scopes, and prompt-fixed case contract; catalog-looking references embedded in
free-form JSON content are rejected instead of treated as validated. For plain
text, the runner checks the
case's expected course/mode and requires every evidenced canonical citation to
appear exactly once with no additional catalog citation; consistency of other
free-form course/style/scope prose and renderer-level citation visibility remain
manual checks. Raw HTML and Markdown links, images, or reference definitions
are rejected on the automated text-evidence path because they can hide a raw
citation. Observed or started
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
assembled for this project to support citation-label checks. It is not an
official College Board publication and is not endorsed by or affiliated with
College Board. Some labels retain College Board course terminology for
identification; the catalog does not claim to reproduce or fully represent the
current Course and Exam Description (CED). "AP" is a College Board trademark.
Verify exam-critical details against the current CED.
