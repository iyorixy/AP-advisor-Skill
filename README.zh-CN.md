[English](./README.md) | **简体中文**

# AP Advisor

一个不依赖第三方 Python 包的 Codex Skill，支持 AP Precalculus、AP Calculus
AB 和 AP Calculus BC。它可以生成原创学习内容、审阅学生作答，并根据学习证据给出
少量、可衡量的学习干预建议。

本 Skill 会分开处理 Topic 映射、课程范围、考试任务元数据和数学正确性。内置
validator 只检查内部 Topic 标签和部分 AP 边界，不等于数学认证，也不保证考试结果。

## 运行要求

- Codex
- Python 3.10 或更高版本；无需第三方 Python 包

## 安装

### 使用 Skill Installer（推荐）

在 Codex 中输入：

```text
$skill-installer Install the skill at path . from iyorixy/AP-advisor-Skill as ap-advisor.
```

Codex 通常会自动发现新安装的 Skill；如果没有显示，请重启 Codex。

### 手动安装到用户目录

PowerShell：

```powershell
New-Item -ItemType Directory -Force "$HOME\.agents\skills" | Out-Null
git clone https://github.com/iyorixy/AP-advisor-Skill.git "$HOME\.agents\skills\ap-advisor"
```

macOS 或 Linux：

```bash
mkdir -p "$HOME/.agents/skills"
git clone https://github.com/iyorixy/AP-advisor-Skill.git "$HOME/.agents/skills/ap-advisor"
```

如果只想在某个仓库中使用，请把该目录放到
`<repository>/.agents/skills/ap-advisor`。

更新手动安装的用户级 Skill：

```bash
git -C "$HOME/.agents/skills/ap-advisor" pull --ff-only
```

## 验证与使用

在 Codex 中打开 `/skills`，确认列表里有 `ap-advisor`；也可以直接调用：

```text
$ap-advisor 请审阅这份 AP Calculus AB 解答，并指出第一个实质性错误。
```

可选的 validator 冒烟检查：进入已安装的 Skill 目录后运行以下命令；必要时把
`python` 改为 `python3`。

```bash
python scripts/validate_topic_code.py --course calc-ab --evidence-json \
  "Unit 3, Topic 3.1 — The Chain Rule"
```

成功时退出码为 `0`，输出包含 `"overall_status":"pass"`。

## 许可证与 AP 声明

MIT。“AP” 是 College Board 的商标。本项目不是 College Board 官方出版物，也未获
其认可。涉及考试的时效性信息应以 College Board 当前官方资料为准。
