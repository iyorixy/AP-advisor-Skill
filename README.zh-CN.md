[English](./README.md) | **简体中文**

# AP Advisor

一个仅依赖 Python 标准库的 Codex Skill，用于 AP Precalculus、AP Calculus
AB/BC 的内容生成、审阅和基于证据的学习干预。

它分开处理四类结论：内部 Topic 标签精确匹配、课程与高风险方法边界、
mathematical practice/考试任务条件，以及数学与教学行为是否正确。Topic
validator 的收据只证明第一层和目录中记录的 Topic 范围，不是数学或行为
PASS。

`references/ap-calc-framework.md` 是精简的匹配目录；
`references/ap-content-boundaries.json` 只保存会改变决策的官方来源元数据、
高风险方法、AB/BC 依赖、exclusions 和独立的 mathematical-practice 维度，
不复制完整 CED。

内部样式含义：

- `instructional`：课程学习；
- `assessed-topic`：映射 Topic 属于考试范围，但不声称是考试题；
- `exam-oriented`：另须明确题型、计算器条件、representation 和
  justification 要求。

旧 token `ap-oriented` 仅作为 `assessed-topic` 的弃用兼容别名。

Advisor 模式根据学习者作答、正确率、耗时、错误过程与不确定性选择一至
三个干预；每项包含理由、有限练习、退出标准和未见迁移复测。没有复测
结果就不声称掌握。

## 安装与确定性检查

将目录复制到 `~/.agents/skills/ap-advisor` 或项目内
`.agents/skills/ap-advisor`。运行时要求 Python 3.10+，无需安装第三方包。

```bash
python -m unittest discover -s tests -v
python scripts/run_behavior_evals.py
```

第二条命令只校验 corpus，不调用模型。validator 对整条 citation 做 NFKC
后完全相等比较；退出码 `0/1/2` 分别表示通过、内容失败和配置错误。

## 行为评测闭环

只有显式 `--run` 才会调用 Codex，并可能消耗账户用量：

```bash
python scripts/run_behavior_evals.py --run --case CASE_ID
```

runner 只验证最终输出并直接调用 validator，不采信 shell、launcher 或命令
事件。保存的最终输出可离线复测并合并可追溯人工裁决：

```bash
python scripts/run_behavior_evals.py \
  --responses responses.jsonl \
  --adjudications adjudications.jsonl
```

`responses.jsonl` 每行包含 `case_id` 与 `final_output`；人工裁决每行包含
`case_id`、`reviewer`、带时区的 `reviewed_at`，以及逐项 `id/status/evidence`。

- `CONTRACT-PASS`：确定性最终输出合同通过；
- `MANUAL REVIEW REQUIRED`：至少一个人工项未完成；
- `PASS`：合同和所有人工项全部通过；
- `FAIL`：合同或任一人工项失败；
- `NOT RUN`：未运行模型行为。

CI 只在 Linux/Windows 上运行确定性测试，不运行 live eval。

## 许可证

MIT。“AP” 是 College Board 商标。本项目不是 College Board 官方出版物，也
未获其认可；考试关键事实必须核对当前官方来源。
