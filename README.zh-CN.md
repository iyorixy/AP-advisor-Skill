[English](./README.md) | **简体中文**

# AP Advisor Skills

本仓库包含三个 Codex Skill，均仅依赖 Python 3.10+ 标准库：

| Skill | 路径 | 仓库内的支持范围 |
| --- | --- | --- |
| `ap-calculus-advisor` | 仓库根目录 | AP Precalculus、AP Calculus AB 和 AP Calculus BC；另含精选的 Calculus AB 自适应 Coach 支持 |
| `ap-psychology-advisor` | `ap-psychology-advisor/` | 本仓库所记录五单元框架下的 AP Psychology |
| `ap-biology-advisor` | `ap-biology-advisor/` | 本仓库所记录 Fall 2025 框架下的 AP Biology |

根 Skill 继续支持上述三门数学课程的 Generate、Review 与 Advisor。自适应
Coach v1 的范围更窄：维护的错因图谱、诊断题库、学习状态与下一题选择器横跨
AP Calculus AB Units 1–8，但并非穷尽所有 Topic；不得据此声称 Precalculus
或 BC 已有同等的自适应覆盖。

## AP Calculus AB 自适应闭环 v1

Coach 根据学生实际作答定位第一个实质性错误，把观察事实、有限证据支持的错因
假设与不确定性分开，只给一个最小提示，然后等待学生真实回应。学生自行修正后，
进入一道未见同构确认题；独立通过后，再进入一道未见的跨表征或跨情境迁移题。
只有在 hint level 0 独立通过未见迁移题时，才能把该具体干预标记为 `passed`；
这不代表整个 Unit 已掌握。

示例：

```text
$ap-calculus-advisor 请用 Coach 模式检查这份 AP Calculus AB Unit 4 解答；
每次只给一个最小提示，等待我的作答，并保持 session-only。
```

维护题库全部为原创练习，不是 AP Classroom、Progress Check、Practice Exam
或其他 College Board 安全材料。Skill 默认不在面向学习者的响应中展示题库答案。
在取得真实、去标识化的学习者数据之前，难度标签一律为 `provisional`。

## 隐私与可选本地状态

Coach 默认仅保留在当前会话中，不写磁盘。本地持久化必须同时满足：用户明确授权，
并由调用者给出仓库外的具体 data directory。状态只保存假名 profile ID、作答、
证据、提示/独立性字段和复测队列；不要求姓名或邮箱。

请使用调用者明确选择的外部目录（以下路径只是示例）：

```powershell
python scripts/update_learner_state.py --data-dir "D:\learner-data\calc-ab-demo" `
  --as-of "2026-08-31T12:00:00Z" --evidence-json init --profile-id demo_profile
python scripts/update_learner_state.py --data-dir "D:\learner-data\calc-ab-demo" `
  --as-of "2026-08-31T12:10:00Z" --evidence-json record --attempt-file attempt.json
python scripts/update_learner_state.py --data-dir "D:\learner-data\calc-ab-demo" `
  --as-of "2026-08-31T12:10:00Z" --evidence-json queue
```

`clear-test-profile` 只能用于以 `--test-data` 初始化的目录，并且只删除该精确
profile 的已识别文件；它不是通用删除命令。真实学习者数据必须保存在仓库外，
不得提交。

```powershell
python scripts/update_learner_state.py --data-dir "D:\learner-data\calc-ab-test" `
  --evidence-json init --profile-id test_profile --test-data
python scripts/update_learner_state.py --data-dir "D:\learner-data\calc-ab-test" `
  --evidence-json clear-test-profile --profile-id test_profile
```

## 安装与调用

进入 Codex 后，使用 Skill Installer：

```text
$skill-installer Install the skill at path . from iyorixy/AP-advisor-Skill as ap-calculus-advisor.
$skill-installer Install the skill at path ap-psychology-advisor from iyorixy/AP-advisor-Skill as ap-psychology-advisor.
$skill-installer Install the skill at path ap-biology-advisor from iyorixy/AP-advisor-Skill as ap-biology-advisor.
```

安装后如未自动发现 Skill，请重启 Codex。调用示例：

```text
$ap-calculus-advisor 审阅这份 AP Calculus BC 解答并指出第一个实质性错误。
$ap-calculus-advisor 生成一道不显示答案的 AP Precalculus 练习题。
$ap-calculus-advisor 一步一步 Coach 我完成这道 AP Calculus AB Unit 6 题。
$ap-psychology-advisor 审阅这份 AP Psychology 作答并指出第一个实质性错误。
$ap-biology-advisor 审阅这份 AP Biology 作答并指出第一个实质性错误。
```

## 验证仓库

在仓库根目录运行（必要时把 `python` 换成 `python3`）：

```bash
python scripts/validate_topic_code.py --self-check --evidence-json
python ap-psychology-advisor/scripts/validate_topic_code.py --self-check --evidence-json
python ap-biology-advisor/scripts/validate_topic_code.py --self-check --evidence-json
python scripts/run_evals.py --self-check --evidence-json
python -m unittest discover -s tests -v
python scripts/check_release.py --evidence-json
```

三条 validator self-check 分别覆盖三个 Skill 的映射和边界包。根目录的 Calculus
adaptive v1 release gate 还会校验必需产物、assessment contract、错因/题目交叉
引用、数学审计哈希、学习状态安全、selector 确定性、行为评审门槛、Python 编译与
纯标准库依赖、单元测试和已安装的 skill-creator validator。只有所有命令都以退出码
`0` 结束，且最后一条输出小写 `"overall_status":"pass"`，才视为仓库验证通过。

首版有意采用透明规则，不引入 BKT、IRT、向量检索或伪精确 mastery 概率。聚合校准
导出只提供描述性统计；样本不足时返回 `insufficient_data`。后续经验校准必须使用
真实、经同意且去标识化的作答数据，并另行评审。

## 许可证与 AP 声明

MIT。“AP”是 College Board 的商标。本项目不是 College Board 官方出版物，也未获
其认可。涉及考试的时效性信息，请以 College Board 当前官方来源为准。
