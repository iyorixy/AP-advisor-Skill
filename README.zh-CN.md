[English](./README.md) | **简体中文**

# AP Advisor Skills

本仓库包含三个可独立安装的 Codex Skill；其运行时脚本均仅依赖 Python 3.10+
标准库：

| Skill | 路径 | 仓库内的支持范围 |
| --- | --- | --- |
| `ap-calculus-advisor` | `ap-calculus-advisor/` | AP Precalculus、AP Calculus AB 和 AP Calculus BC，均含自适应 Coach |
| `ap-psychology-advisor` | `ap-psychology-advisor/` | 当前五单元框架下的 AP Psychology 学习支持与自适应 Coach |
| `ap-biology-advisor` | `ap-biology-advisor/` | 当前 Fall 2025 框架下的 AP Biology 学习支持与自适应 Coach |

所有支持课程现在都提供 Generate、Review、Advisor 与 Coach 模式。数学 Skill
为 AP Precalculus Units 1–4、AP Calculus AB Units 1–8 以及 AP Calculus BC 的
精选错因维护原创诊断题库、可选本地学习状态和确定性下一题选择器；BC 会复用
AB 共有内容，并增加 Units 6–10 的精选 BC-only 覆盖。当前题库包含 32 个诊断
模式和 96 道题，但并不穷尽所有 Topic。Biology 与 Psychology 则按需生成原创题，
只在对话内保留 Coach 状态，
不声称拥有静态题库或持久化档案。

下列框架基线已按 College Board 的
[2026–27 课程变更表](https://apcentral.collegeboard.org/courses/how-ap-develops-courses-and-exams/course-changes-overview)
核对：

| 课程 | 仓库基线 |
| --- | --- |
| AP Precalculus | Fall 2026 CED 及其勘误 |
| AP Calculus AB/BC | Fall 2020 CED，含 Fall 2026 勘误 |
| AP Psychology | Fall 2025 五单元 CED，含 October 2025 勘误 |
| AP Biology | Fall 2025 CED，含 June 2025 与 June 2026 勘误 |

来源元数据最后核对于 2026 年 8 月 28–31 日。考试形式和政策属于时效性信息，
使用时仍需重新查验当前官方来源。

## 自适应 Coach 闭环

Coach 根据学生实际作答定位第一个实质性错误，把观察事实、有限证据支持的错因
假设与不确定性分开，只给一个最小提示，然后等待学生真实回应。学生自行修正后，
进入一道未见同构确认题；独立通过后，再进入一道未见的跨表征或跨情境迁移题。
只有在 hint level 0 独立通过未见迁移题时，才能把该具体干预标记为 `passed`；
这不代表整个 Unit 已掌握。

示例：

```text
$ap-calculus-advisor 请 Coach 我完成这份 AP Precalculus Unit 2 解答，每次只给一个提示。
$ap-calculus-advisor 请 Coach 我完成这份 AP Calculus BC Unit 10 解答，每次只给一个提示。
$ap-psychology-advisor 请从这份 AP Psychology 作答开始 Coach 我，每次只给一个提示。
$ap-biology-advisor 请从这份 AP Biology 作答开始 Coach 我，每次只给一个提示。
```

维护题目和按需生成题目都是原创练习，不是 AP Classroom、Progress Check、
Practice Exam 或其他 College Board 安全材料；隐藏答案不会出现在面向学习者的
响应中。在取得真实、去标识化的学习者数据之前，数学题库的难度标签一律为
`provisional`。

## 隐私与可选本地状态

所有 Coach 默认仅保留在当前会话中，不写磁盘；Biology 和 Psychology Coach 始终
保持 session-only。三门数学课程的本地持久化必须同时满足：用户明确授权，并由
调用者给出仓库外的具体 data directory。状态只保存假名 profile ID、课程、作答、
证据、提示/独立性字段和复测队列；不要求姓名或邮箱。

请使用调用者明确选择的外部目录（以下路径只是示例）；初始化其他数学课程时，
把 `calc-ab` 替换为 `precalculus` 或 `calc-bc`：

```powershell
python ap-calculus-advisor/scripts/update_learner_state.py --data-dir "D:\learner-data\calc-ab-demo" `
  --as-of "2026-08-31T12:00:00Z" --evidence-json init --profile-id demo_profile --course calc-ab
python ap-calculus-advisor/scripts/update_learner_state.py --data-dir "D:\learner-data\calc-ab-demo" `
  --as-of "2026-08-31T12:10:00Z" --evidence-json record --attempt-file attempt.json
python ap-calculus-advisor/scripts/update_learner_state.py --data-dir "D:\learner-data\calc-ab-demo" `
  --as-of "2026-08-31T12:10:00Z" --evidence-json queue
```

`clear-test-profile` 只能用于以 `--test-data` 初始化的目录，并且只删除该精确
profile 的已识别文件；它不是通用删除命令。真实学习者数据必须保存在仓库外，
不得提交。

```powershell
python ap-calculus-advisor/scripts/update_learner_state.py --data-dir "D:\learner-data\calc-ab-test" `
  --evidence-json init --profile-id test_profile --course calc-ab --test-data
python ap-calculus-advisor/scripts/update_learner_state.py --data-dir "D:\learner-data\calc-ab-test" `
  --evidence-json clear-test-profile --profile-id test_profile
```

## 安装与调用

进入 Codex 后，使用 Skill Installer：

```text
$skill-installer Install the skill at path ap-calculus-advisor from iyorixy/AP-advisor-Skill as ap-calculus-advisor.
$skill-installer Install the skill at path ap-psychology-advisor from iyorixy/AP-advisor-Skill as ap-psychology-advisor.
$skill-installer Install the skill at path ap-biology-advisor from iyorixy/AP-advisor-Skill as ap-biology-advisor.
```

仓库根目录包含仅用于开发的测试与发布证据，因此有意不作为可安装 Skill；上面三个
路径可以避免把这些文件复制到用户安装目录。

这些 Skill 会在下一轮对话中可用；若 Codex 界面未刷新，再重启 Codex。调用示例：

```text
$ap-calculus-advisor 审阅这份 AP Calculus BC 解答并指出第一个实质性错误。
$ap-calculus-advisor 一步一步 Coach 我完成这道 AP Precalculus Unit 3 题。
$ap-calculus-advisor 一步一步 Coach 我完成这道 AP Calculus AB Unit 6 题。
$ap-calculus-advisor 一步一步 Coach 我完成这道 AP Calculus BC Unit 9 题。
$ap-psychology-advisor 请从这份 AP Psychology 作答开始 Coach 我，每次只给一个提示。
$ap-biology-advisor 请从这份 AP Biology 作答开始 Coach 我，每次只给一个提示。
```

以上命令适用于从 GitHub 独立安装。若要进入通用插件目录，当前
[OpenAI 官方文档](https://developers.openai.com/codex/skills)建议把可复用的多 Skill
产品打包为 plugin；这是另一条发布渠道。

## 验证仓库

在仓库根目录运行（必要时把 `python` 换成 `python3`）：

```bash
python ap-calculus-advisor/scripts/validate_topic_code.py --self-check --evidence-json
python ap-psychology-advisor/scripts/validate_topic_code.py --self-check --evidence-json
python ap-biology-advisor/scripts/validate_topic_code.py --self-check --evidence-json
python scripts/run_evals.py --self-check --evidence-json
python -m unittest discover -s tests -v
python scripts/check_release.py --evidence-json
```

三条 validator self-check 分别覆盖三个 Skill 的映射和边界包。release gate
还会校验全部 Coach 协议产物、数学 assessment contract、错因/题目交叉引用、
数学审计哈希、学习状态安全、selector 确定性、行为评审门槛、Python 编译与纯标准库
依赖、单元测试和已安装的 skill-creator validator。只有所有命令都以退出码
`0` 结束，且最后一条输出小写 `"overall_status":"pass"`，才视为仓库验证通过。

数学 selector 有意采用透明规则，不引入 BKT、IRT、向量检索或伪精确 mastery
概率。聚合校准导出只提供描述性统计；样本不足时返回 `insufficient_data`。后续
经验校准必须使用真实、经同意且去标识化的作答数据，并另行评审。

## 许可证与 AP 声明

MIT。“AP”是 College Board 的商标。本项目不是 College Board 官方出版物，也未获
其认可。涉及考试的时效性信息，请以 College Board 当前官方来源为准。
