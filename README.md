**English** | [简体中文](./README.zh-CN.md)

# AP Advisor Skills

This repository contains two Codex Skills that require no third-party Python
packages:

- `ap-calculus-advisor` (repository root) supports AP Precalculus, AP Calculus
  AB, and AP Calculus BC.
- `ap-psychology-advisor` supports AP Psychology under the current five-unit
  framework.

Both Skills are study aids built around the AP course frameworks. They are
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

Once inside Codex, send one or both of these installer messages:

```text
$skill-installer Install the skill at path . from iyorixy/AP-advisor-Skill as ap-calculus-advisor.
$skill-installer Install the skill at path ap-psychology-advisor from iyorixy/AP-advisor-Skill as ap-psychology-advisor.
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

After a manual update, copy `ap-psychology-advisor` again into the sibling
installation directory. Skill Installer users can instead reinstall the updated
Skill.

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

MIT. “AP” is a College Board trademark. This project is not an official College
Board publication and is not endorsed by College Board. For time-sensitive exam
information, refer to current official College Board sources.
