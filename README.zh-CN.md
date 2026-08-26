[English](./README.md) | **简体中文**

# AP Advisor

一个用于生成、审阅和规划 AP Precalculus、AP Calculus AB、AP Calculus BC 学习与备考内容的 Codex Skill。

安装后的 Skill 及其确定性检查不需要 API 密钥或网络。可选的实时行为评测会调用已安装并完成认证的 Codex CLI，也可能消耗账户用量。Skill 本身包括：

- 一份规则文档（`SKILL.md`），由 Codex 读取并遵循，
- 一份 AP 课程结构的参考大纲，以及
- 一个小巧、无外部依赖的 Python 校验脚本。

## 为什么做这个

让一个普通的 AI 助手"帮我出几道 AP Calc 练习题"，通常会遇到两种失败模式：

1. **课程范围混用** —— BC-only 或不计入考试的 Topic 可能被错误地当成符合用户所选课程与目标的内容。
2. **引用凭空捏造** —— 模型会说"这是 Unit 11，Topic 11.2 的题目"，但根本不存在这个知识点，因为它只是在模仿 AP unit/topic 引用"看起来应该是什么样子"，而不是真的去核对一个真实的来源。

AP Advisor 使用内部标签目录，将每条引用与用户指定课程及 Topic 层级的考试范围进行核对，以降低这些引用元数据风险。正常路径使用仓库内的校验脚本；如果 Python 不可用，Skill 要求在目录中精确查找，并把自动校验明确标为 `NOT RUN`。如果标签不匹配，脚本会打印相近的目录候选项；只有目标条目明确时，Codex 才可以据此修正。

在 Skill 工作流中，校验器固定使用 `--evidence-json`，输出一个带版本号的 JSON 对象，把命令中的课程、AP-oriented 模式、每个输入引用、精确匹配标签、Topic 范围和总体状态绑定在一起。直接运行校验器时，默认的人类可读输出保持不变。

校验器只检查目录精确匹配和 Topic 层级范围。校验通过**不代表**数学推导正确、内容确实属于所引 Topic，也不代表内容符合当前 Learning Objectives、排除项、题型或计算器条件。请审阅生成内容，并对任何考试关键细节查阅官方 CED。

## 安装

把 `ap-advisor/` 文件夹复制到 Codex 的 skills 目录下：

```
mkdir -p ~/.agents/skills
cp -r ap-advisor ~/.agents/skills/ap-advisor
# 或者，作为项目本地技能：
mkdir -p .agents/skills
cp -r ap-advisor .agents/skills/ap-advisor
```

运行 AI 助手的机器上需要 Python 3.10+（仅用标准库，不需要 `pip install`），用于运行校验脚本。

## 目录结构

```
ap-advisor/
├── SKILL.md                          # AI 助手遵循的规则
├── references/
│   ├── ap-calc-framework.md          # 内部 Unit/Topic 引用目录
│   ├── output-schema.json            # 生成内容的 JSON Schema
│   └── machine-error-schema.json      # 不兼容请求的错误 JSON Schema
├── scripts/
│   ├── validate_topic_code.py        # 校验引用是否存在于大纲中
│   └── run_behavior_evals.py          # 校验或显式运行行为评测
├── evals/
│   └── cases.jsonl                    # 路由与行为回归语料
├── tests/
│   ├── test_validate_topic_code.py   # 校验器单元测试
│   └── test_behavior_evals.py         # 离线 eval runner 测试
├── .github/workflows/test.yml         # 仅运行确定性 CI
├── README.md
├── LICENSE
└── CONTRIBUTING.md
```

## 开发检查

以下命令只运行确定性检查，不调用模型：

```bash
python -m unittest discover -s tests -v
python scripts/run_behavior_evals.py
```

第二条命令只校验评测语料。实时行为评测必须显式启用，并要求已安装且完成认证的 Codex CLI：

```bash
python scripts/run_behavior_evals.py --run --case CASE_ID
```

实时结果写入 Git 已忽略的 `eval-results/`。runner 使用临时只读仓库，并默认忽略用户的 `config.toml`，以减少本地配置造成的差异；只有依赖自定义 provider 或模型配置时才传入 `--use-user-config`。只有同一课程/风格组的一条命令已完成、状态与整数退出码齐全且机器证据有效时，才可声明自动引用校验为 `pass`。对于 JSON case，证据还必须与结构化课程、风格、主引用、辅助引用、范围及语料固定 contract 完全一致；自由 JSON 内容中疑似目录引用的文本会被拒绝，不能冒充已校验引用。对于自由文本，runner 核对 case 预期课程/模式，并要求每条有证据的标准引用恰好出现一次且无额外目录引用；原始 HTML 和 Markdown 引用定义会被拒绝。其他自然语言中的课程、风格、范围陈述以及最终渲染可见性仍须人工检查。仅观察到命令或 `item.started` 不算通过；只有所有受支持 launcher 家族都出现严格识别的 shell 启动失败时，才可支持 JSON `not_run`，单个别名缺失不够。退出码 `2`、复合 shell 命令、框架覆写、输出缺失或证据矛盾都会闭锁失败。这属于受控隔离，并非完全密闭环境。GitHub Actions 不运行实时模型评测。

## 许可证

MIT —— 详见 [LICENSE](LICENSE)。

[references/ap-calc-framework.md](references/ap-calc-framework.md) 中的目录由本项目整理，用于检查引用标签。它不是 College Board 官方出版物，也未获得 College Board 认可或与其存在关联；部分标签为了识别需要保留 College Board 的课程术语，但该目录不声称复现或完整代表当前 Course and Exam Description（CED）。"AP" 是 College Board 的注册商标。任何涉及考试的关键内容，请务必以当前官方 CED 为准。
