[English](./README.md) | **简体中文**

# AP Advisor Skills

本仓库包含三个不依赖第三方 Python 包的 Codex Skill：

- `ap-calculus-advisor`（仓库根目录）支持 AP Precalculus、AP Calculus AB 和 AP Calculus BC。
- `ap-psychology-advisor` 支持当前五单元框架下的 AP Psychology。
- `ap-biology-advisor` 支持当前 Fall 2025 八单元框架下的 AP Biology。

三个 Skill 都是基于 AP 课程框架的学习辅助工具，帮助 Codex 生成原创学习内容、
审阅学生作答，并根据学习证据给出可衡量的学习干预建议。内置 validator 只检查
内部 Topic 映射和部分 AP 边界。

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

进入 Codex 后，按需发送以下任意安装消息：

```text
$skill-installer Install the skill at path . from iyorixy/AP-advisor-Skill as ap-calculus-advisor.
$skill-installer Install the skill at path ap-psychology-advisor from iyorixy/AP-advisor-Skill as ap-psychology-advisor.
$skill-installer Install the skill at path ap-biology-advisor from iyorixy/AP-advisor-Skill as ap-biology-advisor.
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
Copy-Item -Recurse `
  "$HOME\.agents\skills\ap-calculus-advisor\ap-biology-advisor" `
  "$HOME\.agents\skills\ap-biology-advisor"
```

macOS 或 Linux：

```bash
mkdir -p "$HOME/.agents/skills"
git clone https://github.com/iyorixy/AP-advisor-Skill.git "$HOME/.agents/skills/ap-calculus-advisor"
cp -R "$HOME/.agents/skills/ap-calculus-advisor/ap-psychology-advisor" \
  "$HOME/.agents/skills/ap-psychology-advisor"
cp -R "$HOME/.agents/skills/ap-calculus-advisor/ap-biology-advisor" \
  "$HOME/.agents/skills/ap-biology-advisor"
```

以上命令会安装三个 Skill；不需要某个子 Skill 时，可跳过对应的复制命令。如果只在
某个仓库中使用，请把需要的每个 Skill 直接放到
`<repository>/.agents/skills/` 下。

更新手动克隆的微积分 Skill：

```bash
git -C "$HOME/.agents/skills/ap-calculus-advisor" pull --ff-only
```

手动更新后，需要再次把 `ap-psychology-advisor` 和
`ap-biology-advisor` 复制到各自的同级安装目录；使用 Skill Installer 时，也可以
直接重新安装新版 Skill。

## 验证与使用

在 Codex 中打开 `/skills`，确认列表里有已安装的 Skill；也可以直接调用：

```text
$ap-calculus-advisor 请审阅这份 AP Calculus AB 解答，并指出第一个实质性错误。
$ap-psychology-advisor 请审阅这份 AP Psychology 作答，并指出第一个实质性错误。
$ap-biology-advisor 请审阅这份 AP Biology 作答，并指出第一个实质性错误。
```

可选的 validator 冒烟检查：在仓库检出目录中运行以下命令；必要时把 `python`
改为 `python3`。

```bash
python scripts/validate_topic_code.py --course calc-ab --evidence-json \
  "Unit 3, Topic 3.1 — The Chain Rule"
python ap-psychology-advisor/scripts/validate_topic_code.py \
  --self-check --evidence-json
python ap-biology-advisor/scripts/validate_topic_code.py \
  --self-check --evidence-json
```

成功时退出码为 `0`，输出包含 `"overall_status":"pass"`。

## 维护者：一次性 `/goal` 过夜执行提示词

如需无人值守地完成一次上线前检查，请先在 Codex 的界面或配置中选择支持
`xhigh`（极高）的模型并把推理强度设为该档位；下面的提示词本身不会切换模型。
该写法按照 OpenAI 的建议，为 `/goal` 提供单一持久目标、权限边界、验证方法和
可验证的停止条件。参见官方
[Follow a goal 指南](https://learn.chatgpt.com/use-cases/follow-goals)。

在 Codex 中打开本仓库，然后把下面整段作为一条消息发送：

在 Windows 上，如果 `quick_validate.py` 继承了旧版控制台编码，请为该命令设置
`PYTHONUTF8=1`；这只会改变该次检查的 Python 文本解码方式。

```text
/goal 在 ap-biology-advisor 中完成可直接发布的 AP Biology Advisor Skill，并持续工作，直到下面所有停止条件均已验证。首先完整阅读仓库中现有的 AP Calculus 与 AP Psychology Skill、已安装的 skill-creator 指令，以及 ap-biology-advisor 下已有的全部文件；保留无关的用户改动。只使用 College Board 官方来源核对当前 AP Biology 框架：现行 CED、CED clarifications/corrections、AP Biology 课程页、考试页、课程变更页和已发布试题页。随后以最小但完整的范围实现或修正：SKILL.md、agents/openai.yaml、精简的现行 Topic 与 Science Practice 目录、带核对日期和来源元数据且只保留决策性内容的边界文件、当前 MCQ/FRQ 任务合约、Advisor 协议，以及仅使用 Python 3.10+ 标准库、支持精确 Topic/边界校验并带有实质性 --self-check 的 validator。Topic 映射与 Science Practice 映射必须分开；区分 instructional、assessed-topic 和 exam-oriented 声明；识别 Fall 2025 之前的旧框架材料；禁止无依据的“官方风格”或评分声称，也不得捏造研究和数据。同步更新 README.md 与 README.zh-CN.md，确保两个语言版本中的 Skill 数量、安装路径、手动复制与更新步骤、调用示例、冒烟检查和本 /goal 章节完全一致。运行 Biology validator 自检、有针对性的 CLI 正向与负向用例、Python 编译检查，并使用已安装 skill-creator 的 quick_validate.py 校验 ap-biology-advisor。逐个检查所有改动文件和 git diff，排除矛盾、过期数量、无效 JSON/YAML、TODO、占位符、生成的缓存文件和无关改动。不要 commit、push、发布、全局安装、删除用户工作，也不要改变现有 Skill 的行为。若某个官方来源暂时无法访问，应使用其他当前 College Board 官方来源并明确说明未核实点，绝不编造。只有在全部必需文件存在、每项验证均按预期退出、适用的成功回执都包含小写 overall_status pass、双语 README 相互一致，且最终报告列出改动文件、核对过的官方来源、运行过的命令和任何剩余限制后，才停止执行。如果同一外部阻塞连续三个 goal turn 都无法解决，应报告准确阻塞原因，不要无限重试。
```

如果命令列表里没有 `/goal`，先运行
`codex features enable goals`，再按需重启或重新打开 Codex。

## 许可证与 AP 声明

MIT。“AP” 是 College Board 的商标。本项目不是 College Board 官方出版物，也未获
其认可。涉及考试的时效性信息应以 College Board 当前官方资料为准。
