**English** | [简体中文](./README.zh-CN.md)

# AP Advisor

A dependency-free Codex Skill for AP Precalculus, AP Calculus AB, and AP
Calculus BC. It can generate original study content, review learner work, and
turn learner evidence into a small, measurable study intervention.

The Skill keeps Topic mapping, course scope, exam-task metadata, and
mathematical correctness separate. Its validator checks internal Topic labels
and selected AP boundaries; it does not certify the mathematics or guarantee an
exam result.

## Requirements

- Codex
- Python 3.10 or newer; no third-party Python packages

## Install

### Skill Installer (recommended)

Ask Codex to install this GitHub repository:

```text
$skill-installer Install the skill at path . from iyorixy/AP-advisor-Skill as ap-advisor.
```

Codex detects newly installed skills automatically. If it does not appear,
restart Codex.

### Manual user installation

PowerShell:

```powershell
New-Item -ItemType Directory -Force "$HOME\.agents\skills" | Out-Null
git clone https://github.com/iyorixy/AP-advisor-Skill.git "$HOME\.agents\skills\ap-advisor"
```

macOS or Linux:

```bash
mkdir -p "$HOME/.agents/skills"
git clone https://github.com/iyorixy/AP-advisor-Skill.git "$HOME/.agents/skills/ap-advisor"
```

For repository-only use, place the folder at
`<repository>/.agents/skills/ap-advisor` instead.

To update a manual user installation:

```bash
git -C "$HOME/.agents/skills/ap-advisor" pull --ff-only
```

## Verify and use

Open `/skills` in Codex and confirm that `ap-advisor` appears, or invoke it
directly:

```text
$ap-advisor Review this AP Calculus AB solution and identify the first substantive error.
```

Optional validator smoke check, run from the installed skill directory (use
`python3` instead of `python` where needed):

```bash
python scripts/validate_topic_code.py --course calc-ab --evidence-json \
  "Unit 3, Topic 3.1 — The Chain Rule"
```

A successful check exits with code `0` and reports
`"overall_status":"pass"`.

## License and AP notice

MIT. “AP” is a College Board trademark. This project is neither published nor
endorsed by College Board. Verify current exam-critical facts against current
official College Board sources.
