**English** | [简体中文](./README.zh-CN.md)

# AP Advisor Skills

This repository contains two dependency-free Codex Skills:

- `ap-calculus-advisor` (repository root) supports AP Precalculus, AP Calculus
  AB, and AP Calculus BC.
- `ap-psychology-advisor` supports AP Psychology under the current five-unit
  framework.

Both Skills can generate original study content, review learner work, and turn
learner evidence into a small, measurable study intervention. Their validators
check internal Topic mappings and selected AP boundaries; they do not certify
subject-matter correctness or guarantee an exam result.

## Requirements

- Codex
- Python 3.10 or newer; no third-party Python packages

## Install

### Skill Installer (recommended)

Ask Codex to install either or both Skills:

```text
$skill-installer Install the skill at path . from iyorixy/AP-advisor-Skill as ap-calculus-advisor.
$skill-installer Install the skill at path ap-psychology-advisor from iyorixy/AP-advisor-Skill as ap-psychology-advisor.
```

Codex detects newly installed skills automatically. If it does not appear,
restart Codex.

If you previously installed this Skill as `ap-advisor`, replace that
installation with `ap-calculus-advisor` so Codex does not discover both names.

### Manual user installation

PowerShell:

```powershell
New-Item -ItemType Directory -Force "$HOME\.agents\skills" | Out-Null
git clone https://github.com/iyorixy/AP-advisor-Skill.git "$HOME\.agents\skills\ap-calculus-advisor"
Copy-Item -Recurse `
  "$HOME\.agents\skills\ap-calculus-advisor\ap-psychology-advisor" `
  "$HOME\.agents\skills\ap-psychology-advisor"
```

macOS or Linux:

```bash
mkdir -p "$HOME/.agents/skills"
git clone https://github.com/iyorixy/AP-advisor-Skill.git "$HOME/.agents/skills/ap-calculus-advisor"
cp -R "$HOME/.agents/skills/ap-calculus-advisor/ap-psychology-advisor" \
  "$HOME/.agents/skills/ap-psychology-advisor"
```

These commands install both Skills. Skip the copy command if you only want the
`ap-calculus-advisor` Skill. For a repository-only installation, place each
desired Skill directly under `<repository>/.agents/skills/`.

To update the cloned calculus Skill:

```bash
git -C "$HOME/.agents/skills/ap-calculus-advisor" pull --ff-only
```

After a manual update, copy `ap-psychology-advisor` to its sibling installation
again. Skill Installer users can instead reinstall the updated Skill.

## Verify and use

Open `/skills` in Codex and confirm that the installed Skill names appear, or
invoke them directly:

```text
$ap-calculus-advisor Review this AP Calculus AB solution and identify the first substantive error.
$ap-psychology-advisor Review this AP Psychology response and identify the first substantive error.
```

Optional validator smoke checks, run from the repository checkout (use `python3`
instead of `python` where needed):

```bash
python scripts/validate_topic_code.py --course calc-ab --evidence-json \
  "Unit 3, Topic 3.1 — The Chain Rule"
python ap-psychology-advisor/scripts/validate_topic_code.py \
  --self-check --evidence-json
```

A successful check exits with code `0` and reports
`"overall_status":"pass"`.

## License and AP notice

MIT. “AP” is a College Board trademark. This project is neither published nor
endorsed by College Board. Verify current exam-critical facts against current
official College Board sources.
