[English](./README.md) | **简体中文**

# AP Advisor Skills

本仓库包含两个不依赖第三方 Python 包的 Codex Skill：

- `ap-advisor`（仓库根目录）支持 AP Precalculus、AP Calculus AB 和 AP Calculus BC。
- `ap-psychology-advisor` 支持当前五单元框架下的 AP Psychology。

两个 Skill 都可以生成原创学习内容、审阅学生作答，并根据学习证据给出少量、可衡量的
学习干预建议。内置 validator 只检查内部 Topic 映射和部分 AP 边界，不等于学科正确性
认证，也不保证考试结果。

## 运行要求

- Codex
- Python 3.10 或更高版本；无需第三方 Python 包

## 安装

### 使用 Skill Installer（推荐）

在 Codex 中按需输入以下一条或两条指令：

```text
$skill-installer Install the skill at path . from iyorixy/AP-advisor-Skill as ap-advisor.
$skill-installer Install the skill at path ap-psychology-advisor from iyorixy/AP-advisor-Skill as ap-psychology-advisor.
```

Codex 通常会自动发现新安装的 Skill；如果没有显示，请重启 Codex。

### 手动安装到用户目录

PowerShell：

```powershell
New-Item -ItemType Directory -Force "$HOME\.agents\skills" | Out-Null
git clone https://github.com/iyorixy/AP-advisor-Skill.git "$HOME\.agents\skills\ap-advisor"
Copy-Item -Recurse `
  "$HOME\.agents\skills\ap-advisor\ap-psychology-advisor" `
  "$HOME\.agents\skills\ap-psychology-advisor"
```

macOS 或 Linux：

```bash
mkdir -p "$HOME/.agents/skills"
git clone https://github.com/iyorixy/AP-advisor-Skill.git "$HOME/.agents/skills/ap-advisor"
cp -R "$HOME/.agents/skills/ap-advisor/ap-psychology-advisor" \
  "$HOME/.agents/skills/ap-psychology-advisor"
```

以上命令会安装两个 Skill；如果只需要数学 Skill，可以跳过复制命令。如果只在某个仓库
中使用，请把需要的每个 Skill 直接放到 `<repository>/.agents/skills/` 下。

更新手动克隆的数学 Skill：

```bash
git -C "$HOME/.agents/skills/ap-advisor" pull --ff-only
```

手动更新后，需要再次把 `ap-psychology-advisor` 复制到同级安装目录；使用 Skill
Installer 时，也可以直接重新安装新版 Skill。

## 验证与使用

在 Codex 中打开 `/skills`，确认列表里有已安装的 Skill；也可以直接调用：

```text
$ap-advisor 请审阅这份 AP Calculus AB 解答，并指出第一个实质性错误。
$ap-psychology-advisor 请审阅这份 AP Psychology 作答，并指出第一个实质性错误。
```

可选的 validator 冒烟检查：在仓库检出目录中运行以下命令；必要时把 `python`
改为 `python3`。

```bash
python scripts/validate_topic_code.py --course calc-ab --evidence-json \
  "Unit 3, Topic 3.1 — The Chain Rule"
python ap-psychology-advisor/scripts/validate_topic_code.py \
  --self-check --evidence-json
```

成功时退出码为 `0`，输出包含 `"overall_status":"pass"`。

## 许可证与 AP 声明

MIT。“AP” 是 College Board 的商标。本项目不是 College Board 官方出版物，也未获
其认可。涉及考试的时效性信息应以 College Board 当前官方资料为准。
