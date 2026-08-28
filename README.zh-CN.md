[English](./README.md) | **简体中文**

# AP Advisor Skills

本仓库包含两个不依赖第三方 Python 包的 Codex Skill：

- `ap-calculus-advisor`（仓库根目录）支持 AP Precalculus、AP Calculus AB 和 AP Calculus BC。
- `ap-psychology-advisor` 支持当前五单元框架下的 AP Psychology。

两个 Skill 都是基于AP考纲下的辅助Skill，致力于让Codex更好帮助学生的AP学习，例生成原创学习内容、审阅学生作答，并根据学习证据给出可衡量的一定学习干预建议等。
内置 validator 只检查内部 Topic 映射和部分 AP 边界

## 运行要求

- Codex
- Python 3.10 或更高版本；无需第三方 Python 包

## 安装

### 先进入 Codex

> **下面以 `$skill-installer ...` 开头的内容是发给 Codex 的消息，不是
> PowerShell、CMD 或 Bash 命令。**

- **桌面应用：**打开 ChatGPT 桌面应用，选择 **Codex**，点击 **New chat**，再将
  安装指令粘贴到聊天输入框。
- **Codex CLI：**先在 PowerShell 或其他终端中运行 `codex`。等 Codex 打开并显示
  `›` 输入提示符后，再粘贴安装指令。如果仍看到 `(base) PS C:\...>` 之类的提示符，
  说明你还在 PowerShell。

如果尚未安装 Codex，请参照官方的
[桌面应用快速入门](https://learn.chatgpt.com/docs/app)或
[Codex CLI 快速入门](https://learn.chatgpt.com/docs/codex/cli)。

### 使用 Skill Installer（推荐）

进入 Codex 后，按需发送以下一条或两条安装消息：

```text
$skill-installer Install the skill at path . from iyorixy/AP-advisor-Skill as ap-calculus-advisor.
$skill-installer Install the skill at path ap-psychology-advisor from iyorixy/AP-advisor-Skill as ap-psychology-advisor.
```

Codex 通常会自动发现新安装的 Skill；如果没有显示，请重启 Codex。

如果此前以 `ap-advisor` 安装过此 Skill，请将旧安装替换为
`ap-calculus-advisor`，以免 Codex 同时发现两个名称。

### 手动安装到用户目录

PowerShell：

```powershell
New-Item -ItemType Directory -Force "$HOME\.agents\skills" | Out-Null
git clone https://github.com/iyorixy/AP-advisor-Skill.git "$HOME\.agents\skills\ap-calculus-advisor"
Copy-Item -Recurse `
  "$HOME\.agents\skills\ap-calculus-advisor\ap-psychology-advisor" `
  "$HOME\.agents\skills\ap-psychology-advisor"
```

macOS 或 Linux：

```bash
mkdir -p "$HOME/.agents/skills"
git clone https://github.com/iyorixy/AP-advisor-Skill.git "$HOME/.agents/skills/ap-calculus-advisor"
cp -R "$HOME/.agents/skills/ap-calculus-advisor/ap-psychology-advisor" \
  "$HOME/.agents/skills/ap-psychology-advisor"
```

以上命令会安装两个 Skill；如果只需要微积分 Skill，可以跳过复制命令。如果只在某个仓库
中使用，请把需要的每个 Skill 直接放到 `<repository>/.agents/skills/` 下。

更新手动克隆的微积分 Skill：

```bash
git -C "$HOME/.agents/skills/ap-calculus-advisor" pull --ff-only
```

手动更新后，需要再次把 `ap-psychology-advisor` 复制到同级安装目录；使用 Skill
Installer 时，也可以直接重新安装新版 Skill。

## 验证与使用

在 Codex 中打开 `/skills`，确认列表里有已安装的 Skill；也可以直接调用：

```text
$ap-calculus-advisor 请审阅这份 AP Calculus AB 解答，并指出第一个实质性错误。
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
