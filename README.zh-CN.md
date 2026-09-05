[English](./README.md) | **简体中文** | [繁體中文](./README.zh-TW.md)

# AP Advisor Skills

本仓库包含三个可独立安装的 Codex Skill；其运行时脚本均仅依赖 Python 3.10+
标准库：

| Skill | 路径 | 仓库内的支持范围 |
| --- | --- | --- |
| `ap-calculus-advisor` | `ap-calculus-advisor/` | AP Precalculus、AP Calculus AB 和 AP Calculus BC，均含自适应 Coach |
| `ap-psychology-advisor` | `ap-psychology-advisor/` | 当前五单元框架下的 AP Psychology 学习支持与自适应 Coach |
| `ap-biology-advisor` | `ap-biology-advisor/` | 当前 Fall 2025 框架下的 AP Biology 学习支持与自适应 Coach |

它们是工作流 Skill，不是独立网课产品，也不能替代学科专家。Skill 会约束宿主模型
遵循“证据优先”的 AP 工作流，只在需要时加载对应课程资料，并用本地 validator
校验可以机械判断的声明。

## GPT-6 Astra 适配

三个 Skill 都已加入适配 Astra 的交互约定：完成用户要求的交付物，只追问会改变
判断的信息，接受中途纠正与模式切换，并让 Coach 每轮只推进一个动作、等待真实
作答。这些调整依据 2026 年 9 月 5 日核对的
[Astra 官方提示指引](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-6-astra)；
这些指令也可用于其他具备相应能力的宿主模型。

在提供该模型的宿主中选择 `gpt-6-astra`。Skill 本身不会切换模型，也不提供账号
访问权限。使用 Codex 配置时，在你选用的 `config.toml` 中设置以下字段；已有
同名字段时更新原值，不要重复添加：

```toml
model = "gpt-6-astra"
model_reasoning_effort = "medium"
```

配置字段见 [Codex 官方配置参考](https://learn.chatgpt.com/docs/config-file/config-reference)。
`medium` 是本项目建议的起点，不是经过实测的最优值。迁移时可保留已有且适用的
推理强度；宿主支持时，简单追问可用 `low`，复杂审阅可用 `high`。Astra 官方列出的
推理强度不包含 `none` 和 `minimal`；实际可选项由宿主决定，见
[模型规格](https://developers.openai.com/api/docs/models/gpt-6-astra)。

各科新增按需加载的证据审阅资料，处理图片、来源或模型解读及出题质量：区分可读
证据与不确定转录，先检查学科推理，再检查 Topic 元数据，并核对原创题的条件是否
充分、答案是否成立。Coach 协议会在纠正后保留仍有效的证据，以简短的会话摘要
衔接长对话，并隐藏答案。回答会遵循用户指定的英文、简体中文或繁体中文。

## 实际功能

| 模式 | 实际行为 |
| --- | --- |
| **Generate** | 在用户指定的课程、Topic、题型、难度、语言和答案可见性约束内，生成原创讲解、练习题、stimulus、数据集或 worked example。 |
| **Review** | 检查用户提供的作答，定位第一个实质性错误及其后果；若没有实质性错误，就明确说明，而不是编造问题。 |
| **Advisor** | 只依据学习者给出的证据，排序一至三个有限任务；每个任务包含优先原因、练习动作和可观察的退出标准。 |
| **Coach** | 运行一次只推进一题的交互闭环：诊断、给一个最小提示、等待真实作答、确认修正，再用迁移题检验是否能独立应用。 |

核心用户是愿意提交真实作答、需要针对性反馈、逐级提示或 AP 对齐原创练习的
AP 学生。Skill 会保持用户指定的回答语言，因此也适合双语学习环境。教师、导师
和内容审核者可以把 Generate、Review 与课程范围校验作为第二道检查。它不是官方
评分服务、AP Classroom 替代品、通用升学顾问，也不是——尤其对 Psychology
而言——个人临床判断工具。

三个实现有意采用不同方案：

| Skill | 课程专属实现 |
| --- | --- |
| 数学 | 维护 96 道原创题、32 个诊断模式：Precalculus 8 个、Calculus AB 16 个、精选 BC-only 8 个；每个模式各有诊断题、同构确认题和迁移题。AB 在 Units 1–8 每单元维护两个模式，Precalculus 在 Units 1–4 每单元维护两个模式；BC 复用 AB 共有内容并增加 Units 6–10 的精选覆盖。题库并不穷尽全部 Topic。 |
| Psychology | 在当前五个 Units 内按需生成原创题，覆盖概念应用、研究设计、数据/统计、AAQ 与 EBQ；不声称拥有静态题库或跨会话学习档案。 |
| Biology | 在当前八个 Units 内按需生成原创题，覆盖机制、模型、实验设计、数据/统计、MCQ 与六类现行 FRQ；不声称拥有静态题库或跨会话学习档案。 |

下列框架基线已按 College Board 的
[2026–27 课程变更表](https://apcentral.collegeboard.org/courses/how-ap-develops-courses-and-exams/course-changes-overview)
核对：

| 课程 | 仓库基线 |
| --- | --- |
| AP Precalculus | Fall 2026 CED 及其勘误 |
| AP Calculus AB/BC | Fall 2020 CED，含 Fall 2026 勘误 |
| AP Psychology | Fall 2025 五单元 CED，含 October 2025 勘误 |
| AP Biology | Fall 2025 CED，含 June 2025 与 June 2026 勘误 |

AP Precalculus 的 exam-oriented 支持现已覆盖 May 2027 考试的 Units 1–3、MCQ
和四类命名 FRQ：Function Concepts、Modeling a Non-Periodic Context、
Modeling a Periodic Context、Symbolic Manipulations；Unit 4 仍仅用于
instructional 内容。

来源元数据最后核对于 2026 年 8 月 28 日至 9 月 3 日。考试形式和政策属于时效性信息，
使用时仍需重新查验当前官方来源。

## 端到端工作流

1. **路由：**根据用户意图选择 Generate、Review、Advisor 或 Coach。
2. **锁定约束：**保持用户指定的课程、Topic、题型、难度、语言、答案可见性和已提供
   证据不变；发生冲突时明确说明，不静默替换条件。
3. **只加载必要 contract：**使用对应课程的 catalog 与 boundary package；若是
   exam-oriented 任务，再读取 assessment-task reference；若是 Coach，再读取
   session protocol；图片、复杂来源解读与原创考试练习题另按需读取证据审阅资料。
4. **推理、映射、校验：**独立完成或审阅学科推理，把 content 与 Practice 分开映射，
   再用课程 validator 校验所有展示的 Topic 和已声明的考试题型 contract。
5. **按所需范围回答：**输出内容、首错 Review、一至三个任务的 Advisor 计划，或严格
   一个 Coach 动作。除非满足数学 Skill 的独立 opt-in 持久化 contract，否则状态只
   保留在对话中。

## 自适应 Coach 闭环

Coach 是“依据作答证据自适应”，不是“依据分数自适应”。它不会只凭低分、错选项、
耗时慢或 Topic 标签就推断错因。完整闭环是：

1. 从完整题目/stimulus 和学生真实作答开始。若缺少必要证据，只索取那一项材料，
   或给一道原创诊断题，然后等待。
2. 找到最早出现的实质性断点，把观察事实、一个有限的原因假设、一个合理替代解释
   和尚未确定的部分分开。
3. 给最少但有效的提示。Hint level 0 只有题目；level 1–3 依次从指向关键特征、
   局部不完整 setup，推进到示范一个卡住的步骤。每次只升一级，不虚构学生的下一步。
4. 学生自行修正后，给一道不含答案的未见同构确认题；在 hint level 0 独立通过后，
   再给一道改变关键情境、表征或题型的未见迁移题。
5. 只有 hint level 0 独立完成未见迁移题并达到已声明的退出标准，才把这个具体干预
   标为 `passed`。引导下完成仍是 provisional；一个干预通过不代表整个 Unit 或课程
   已掌握。

数学 Coach 可以从已审计题库用确定性 selector 选下一道维护题；Biology 和
Psychology 按需生成原创确认题与迁移题。所有实现每轮最多返回一道新 Coach 题。

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

## 课程校验与幻觉防护

仓库把模型行为约束与可机器检查的控制结合起来：

- Topic citation 会先做 Unicode NFKC 规范化，再与内部 framework catalog 的完整
  citation 精确匹配。Validator 返回 canonical citation 和考试范围；格式错误、
  编造或课程不匹配的映射会失败。
- Content Topic 与 Mathematical/Science Practice 是两个独立声明。若证据只能确定
  跨课程 Practice，Skill 会把 Topic 保留为 `not established`，不会为了填字段而猜。
- Boundary package 会检查 assessed 与 instructional 范围、登记过的 exclusion 和
  high-risk method、旧框架标记以及考试题型 contract。完整题型校验会检查必需的
  Practice/representation family，不会把 Topic 匹配当作“符合 AP 题型”的证明。
- 证据规则禁止虚构学生作答、用时、自信度、独立性、研究、数据、步骤、统计结果、
  引用、评分指南和掌握结论；合成的练习 stimulus 与数据必须标为 synthetic。
- 所有题目均为原创，不复现 AP Classroom、Progress Check 或 Practice Exam 等安全
  材料。给 released question 数字评分时，必须同时拥有同一考试年份、form 和题号的
  原题与官方 scoring guide；否则只能给明确标注为 unscored 的概念性反馈。
- 隐藏答案、解析、干扰项诊断、题目链接和 selector 理由不会出现在面向学生的
  Coach 回合。学生可以主动要求完整解答，但该次辅助作答不能计为独立证据。
- Self-check、单元测试、schema、数学审计哈希、行为案例和 release gate 共同检查
  这些 contract 是否保持内部一致。

这些控制会减少常见幻觉路径，但不能让模型输出绝对无误。Validator 的 `pass` 只
确认映射和已声明的边界元数据，不证明学科推理、教学质量、官方 rubric 对齐，也不
证明时效性考试政策此刻仍然有效。因此，学科内容仍需独立核查；会变化的考试信息仍
需重新查验当前官方来源。

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

Codex 会自动检测新安装的 Skill；若某个 Skill 没有出现，再重启 Codex。调用示例：

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

这些是本地检查，包含已记录行为评审的一致性校验；它们不会重新调用 Astra，
也不测量学习效果。原有评审记录仍是历史证据；Astra 专项行为尚未使用新的
模型输出进行评估。

数学 selector 有意采用透明规则，不引入 BKT、IRT、向量检索或伪精确 mastery
概率。聚合校准导出只提供描述性统计；样本不足时返回 `insufficient_data`。后续
经验校准必须使用真实、经同意且去标识化的作答数据，并另行评审。

## 许可证与 AP 声明

MIT。“AP”是 College Board 的商标。本项目不是 College Board 官方出版物，也未获
其认可。涉及考试的时效性信息，请以 College Board 当前官方来源为准。
