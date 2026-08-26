[English](./README.md) | **简体中文**

# AP Advisor

一个用于诊断、生成、审阅和安排 AP Precalculus、AP Calculus AB、AP Calculus BC 学习内容优先级的 Codex Skill。

Advisor 的首要目标是根据学习者的作答证据定位最主要、可干预的弱点，并给出一至三个有理由、可执行、可测量的干预任务。内部 Topic 目录和校验器只是安全护栏，不是产品目标本身。

安装后的 Skill 及其确定性检查不需要 API 密钥或网络。可选的实时行为评测会调用已安装并完成认证的 Codex CLI，也可能消耗账户用量。Skill 本身包括：

- 一份规则文档（`SKILL.md`），由 Codex 读取并遵循，
- 一份仅在 Advisor 模式读取的诊断与干预协议，
- 一份 AP 课程结构的内部 Topic 映射目录，以及
- 一个小巧、无外部依赖的 Python Topic 映射校验脚本。

## 为什么做这个

单看正确率不能解释学习者为什么出错。AP Advisor 会结合书面作答、错误模式、耗时、信心、目标和可用时间，区分概念理解、建模、程序或计算、表示转换、数学论证、读题和时间管理问题；再给出带理由和可测退出标准的最小干预，并用未见迁移题复测。没有复测结果时，不声称已经掌握。

Topic 元数据还需要防范两类问题：

1. **Topic 层级目录范围混用** —— BC-only 或不计入考试的 Topic 可能被错误地当成符合用户所选课程与目标的内容。
2. **目录标签凭空捏造** —— 模型可能展示一个看似合理、实际不存在于内部目录中的 Unit/Topic 标签。

AP Advisor 会把每条展示的课程 Topic 映射与内部标签目录、所请求课程的兼容性及 Topic 层级目录范围核对，以降低这些映射元数据风险。内部标签不是官方来源引用。正常路径使用仓库内的校验脚本；如果 Python 不可用，Skill 要求在目录中精确查找，并把自动校验明确标为 `NOT RUN`。如果标签不匹配，脚本会打印相近的目录候选项；只有目标条目明确时，Codex 才可以据此修正。

在 Skill 工作流中，校验器固定使用 `--evidence-json`，输出一个带版本号的 JSON 对象，把命令中的课程、兼容 token `ap-oriented`、每个输入映射、精确匹配标签、Topic 范围和校验状态绑定在一起。直接运行校验器时，默认的人类可读输出保持不变。

校验器执行支持 Unicode 的规范化精确匹配，只检查内部目录标签和 Topic 层级目录范围。它允许大小写、空白和合理标点差异，但不会吞掉附加的中文、日文、西里尔文或其他文字。校验通过**不代表**数学推导正确、内容确实属于所映射 Topic、教学质量合格，也不代表内容符合当前 Learning Objectives、排除项、题型、计算器条件、表示形式、rubric、计分方式或完整考试对齐。考试关键细节必须查阅当前 College Board 官方来源。

面向用户的文案使用 `exam-oriented`（面向考试）。现有 CLI 参数 `--ap-oriented`、JSON 值 `ap-oriented` 和字段名 `citation_validation` 作为兼容 token/字段保留。面向考试只表示所有映射 Topic 都标记为 `assessed`，不增加上面列出的任何考试对齐保证。

难度按可观察要求划分，而不是凭语感：`foundational` 提供或回顾直接前置、推理路径短且无需表示转换；`standard` 假定常规前置、包含多个相连步骤，并可能要求熟悉的表示转换；`challenge` 需要选择并组合多个前置、作出非例行的多步决策，并把关键表示转换或数学论证作为解题的一部分。

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
│   ├── advisor.md                    # 仅 Advisor 模式读取的诊断协议
│   ├── ap-calc-framework.md          # 内部 Unit/Topic 映射目录
│   ├── output-schema.json            # 生成内容的 JSON Schema
│   └── machine-error-schema.json      # 不兼容请求的错误 JSON Schema
├── scripts/
│   ├── validate_topic_code.py        # 校验映射是否存在于内部目录中
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

第二条命令可能输出 `VALID`，但这只表示评测语料结构有效，不是模型行为 `PASS`。没有显式执行的实时行为评测是 `NOT RUN`；实时执行要求已安装且完成认证的 Codex CLI：

```bash
python scripts/run_behavior_evals.py --run --case CASE_ID
```

实时结果写入 Git 已忽略的 `eval-results/`。状态语义必须分开：自动 shape、字面和 validator receipt 合同检查通过是 `CONTRACT-PASS`；只要还有未裁决的 `manual_checks`，整体就是 `MANUAL REVIEW REQUIRED`；自动合同失败是 `FAIL`；未执行实时模型是 `NOT RUN`。行为级 `PASS` 只保留给“自动合同和全部人工项都已裁决通过”的结果；当前 runner 没有人工裁决入口，因此不会自行发出行为级 `PASS`。Topic 映射校验器的小写 `pass` 是另一层合同。旧结果字段 `automated_passed` 和 `automated_pass` 作为已弃用的兼容别名保留，只表示自动合同布尔值，不表示整体行为 `PASS`。

runner 使用临时只读仓库，并默认忽略用户的 `config.toml`，以减少本地配置造成的差异；只有依赖自定义 provider 或模型配置时才传入 `--use-user-config`。只有同一课程/风格组的一条命令已完成、状态与整数退出码齐全且机器证据有效时，才可声明 Topic 映射校验器为 `pass`。对于 JSON case，证据还必须与结构化课程、风格、主映射、辅助映射、范围及语料固定 contract 完全一致；自由 JSON 内容中疑似目录映射的文本会被拒绝，不能冒充已校验映射。对于自由文本，runner 核对 case 预期课程/模式，并要求每条有证据的标准映射恰好出现一次且无额外目录映射；原始 HTML 和 Markdown 链接、图片或引用定义会被拒绝。其他自然语言中的课程、风格、范围陈述以及最终渲染可见性仍须人工检查。仅观察到命令或 `item.started` 不算通过；只有所有受支持 launcher 家族都出现严格识别的 shell 启动失败时，才可支持 JSON `not_run`，单个别名缺失不够。退出码 `2`、复合 shell 命令、框架覆写、输出缺失或证据矛盾都会闭锁失败。这属于受控隔离，并非完全密闭环境。GitHub Actions 不运行实时模型评测。

## 许可证

MIT —— 详见 [LICENSE](LICENSE)。

[references/ap-calc-framework.md](references/ap-calc-framework.md) 中的目录由本项目整理，用于检查内部课程 Topic 映射。它不是 College Board 官方出版物，也未获得 College Board 认可或与其存在关联；部分标签为了识别需要保留 College Board 的课程术语，但这些标签不是官方原文或来源引用，该目录也不声称复现或完整代表当前 Course and Exam Description（CED）。"AP" 是 College Board 的注册商标。任何涉及考试的关键内容，请务必以当前 College Board 官方来源为准。
