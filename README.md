**English** | [简体中文](./README.zh-CN.md)

# AP Advisor Skills

This repository contains three Codex Skills that require no third-party Python
packages:

- `ap-calculus-advisor` (repository root) supports AP Precalculus, AP Calculus
  AB, and AP Calculus BC.
- `ap-psychology-advisor` supports AP Psychology under the current five-unit
  framework.
- `ap-biology-advisor` supports AP Biology under the current Fall 2025
  eight-unit framework.

All three Skills are study aids built around the AP course frameworks. They are
designed to help Codex better support students in their AP studies—for example,
by generating original study content, reviewing student responses, and
recommending measurable study interventions based on evidence of learning. The
built-in validators check only internal Topic mappings and selected AP boundaries.

## Requirements

- Codex
- Python 3.10 or newer; no third-party Python packages

## Install

### Open Codex first

> **The `$skill-installer ...` lines below are messages for Codex, not
> PowerShell, Command Prompt, or Bash commands.**

- **Desktop app:** Open the ChatGPT desktop app, choose **Codex**, start
  **New chat**, and paste the installer message into the chat box.
- **Codex CLI:** In PowerShell or another terminal, run `codex`. Paste the
  installer message only after Codex opens and shows the `›` input prompt. If
  you still see a prompt such as `(base) PS C:\...>`, you are still in
  PowerShell.

If Codex is not installed yet, follow the official
[desktop app quickstart](https://learn.chatgpt.com/docs/app) or
[Codex CLI quickstart](https://learn.chatgpt.com/docs/codex/cli).

### Skill Installer (recommended)

Once inside Codex, send any of these installer messages:

```text
$skill-installer Install the skill at path . from iyorixy/AP-advisor-Skill as ap-calculus-advisor.
$skill-installer Install the skill at path ap-psychology-advisor from iyorixy/AP-advisor-Skill as ap-psychology-advisor.
$skill-installer Install the skill at path ap-biology-advisor from iyorixy/AP-advisor-Skill as ap-biology-advisor.
```

Codex usually discovers newly installed Skills automatically. If they do not
appear, restart Codex.

If you previously installed this Skill as `ap-advisor`, replace that
installation with `ap-calculus-advisor` so Codex does not discover both names.

### Manual installation to the user directory

PowerShell:

```powershell
New-Item -ItemType Directory -Force "$HOME\.agents\skills" | Out-Null
git clone https://github.com/iyorixy/AP-advisor-Skill.git "$HOME\.agents\skills\ap-calculus-advisor"
Copy-Item -Recurse `
  "$HOME\.agents\skills\ap-calculus-advisor\ap-psychology-advisor" `
  "$HOME\.agents\skills\ap-psychology-advisor"
Copy-Item -Recurse `
  "$HOME\.agents\skills\ap-calculus-advisor\ap-biology-advisor" `
  "$HOME\.agents\skills\ap-biology-advisor"
```

macOS or Linux:

```bash
mkdir -p "$HOME/.agents/skills"
git clone https://github.com/iyorixy/AP-advisor-Skill.git "$HOME/.agents/skills/ap-calculus-advisor"
cp -R "$HOME/.agents/skills/ap-calculus-advisor/ap-psychology-advisor" \
  "$HOME/.agents/skills/ap-psychology-advisor"
cp -R "$HOME/.agents/skills/ap-calculus-advisor/ap-biology-advisor" \
  "$HOME/.agents/skills/ap-biology-advisor"
```

These commands install all three Skills. Skip either copy command for a Skill
you do not want. For a repository-only installation, place each
desired Skill directly under `<repository>/.agents/skills/`.

To update the cloned calculus Skill:

```bash
git -C "$HOME/.agents/skills/ap-calculus-advisor" pull --ff-only
```

After a manual update, copy `ap-psychology-advisor` and
`ap-biology-advisor` again into their sibling installation directories. Skill
Installer users can instead reinstall the updated Skill.

## Verify and use

Open `/skills` in Codex and confirm that the installed Skill names appear, or
invoke them directly:

```text
$ap-calculus-advisor Review this AP Calculus AB solution and identify the first substantive error.
$ap-psychology-advisor Review this AP Psychology response and identify the first substantive error.
$ap-biology-advisor Review this AP Biology response and identify the first substantive error.
```

Optional validator smoke checks, run from the repository checkout (use `python3`
instead of `python` where needed):

```bash
python scripts/validate_topic_code.py --course calc-ab --evidence-json \
  "Unit 3, Topic 3.1 — The Chain Rule"
python ap-psychology-advisor/scripts/validate_topic_code.py \
  --self-check --evidence-json
python ap-biology-advisor/scripts/validate_topic_code.py \
  --self-check --evidence-json
```

A successful check exits with code `0` and reports
`"overall_status":"pass"`.

## Maintainer: one-shot `/goal` overnight prompt

For a long unattended release pass, first select a Codex model that supports
`xhigh` (Extra High) reasoning and set that reasoning level in the UI or
configuration. The prompt below does not change model settings. It follows
OpenAI's guidance to give `/goal` one durable objective, explicit boundaries,
validation commands, and a verifiable stopping condition. See the official
[Follow a goal guide](https://learn.chatgpt.com/use-cases/follow-goals).

Open this repository in Codex, then send the following as one message:

On Windows, if `quick_validate.py` inherits a legacy console encoding, run it
with `PYTHONUTF8=1`; this changes only Python's text decoding for that check.

```text
/goal Finish a release-ready AP Biology Advisor Skill in ap-biology-advisor and keep working until every stopping condition below is verified. First read the repository's existing AP Calculus and AP Psychology Skills, the installed skill-creator instructions, and all files already present under ap-biology-advisor. Preserve unrelated user changes. Verify the current AP Biology framework only against official College Board sources: the current CED, its clarifications/corrections, the AP Biology course page, exam page, course-changes page, and released-question page. Then implement or correct the minimum complete package: SKILL.md, agents/openai.yaml, a concise current Topic-and-Practice catalog, decision-changing boundaries with dated source metadata, current MCQ/FRQ task contracts, an Advisor protocol, and a Python 3.10+ standard-library-only exact Topic/boundary validator with a meaningful --self-check. Keep Topic mapping separate from Science Practice mapping; distinguish instructional, assessed-topic, and exam-oriented claims; detect pre-Fall-2025 legacy material; prohibit unsupported official-style/scoring claims and invented studies or data. Update README.md and README.zh-CN.md so the skill count, installation paths, manual copy/update steps, invocation examples, smoke checks, and this /goal section agree in both languages. Run the biology validator self-check, targeted positive and negative CLI cases, Python compilation, and the installed skill-creator quick_validate.py against ap-biology-advisor. Inspect every changed file and git diff for contradictions, stale counts, invalid JSON/YAML, TODOs, placeholders, generated cache files, and unrelated edits. Do not commit, push, publish, install globally, delete user work, or change the existing Skills' behavior. If an official source is temporarily inaccessible, use other current official College Board sources and disclose the unverified point; never invent it. Stop only when all required files exist, every validation exits as expected, all success receipts report lower-case overall_status pass where applicable, both READMEs match, and the final report lists changed files, official sources checked, commands run, and any remaining limitation. If the same external blocker prevents progress across three consecutive goal turns, report the exact blocker instead of looping.
```

If `/goal` is not listed, enable the feature with
`codex features enable goals`, then restart or reopen Codex as needed.

## License and AP notice

MIT. “AP” is a College Board trademark. This project is not an official College
Board publication and is not endorsed by College Board. For time-sensitive exam
information, refer to current official College Board sources.
