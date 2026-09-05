[English](./README.md) | [简体中文](./README.zh-CN.md) | **繁體中文**

# AP Advisor Skills

本儲存庫包含三個可獨立安裝的 Codex Skill；其執行階段指令碼均僅依賴 Python 3.10+
標準函式庫：

| Skill | 路徑 | 儲存庫內的支援範圍 |
| --- | --- | --- |
| `ap-calculus-advisor` | `ap-calculus-advisor/` | AP Precalculus、AP Calculus AB 和 AP Calculus BC，均含自適應 Coach |
| `ap-psychology-advisor` | `ap-psychology-advisor/` | 目前五單元架構下的 AP Psychology 學習支援與自適應 Coach |
| `ap-biology-advisor` | `ap-biology-advisor/` | 目前 Fall 2025 架構下的 AP Biology 學習支援與自適應 Coach |

它們是工作流程 Skill，並非獨立的線上課程產品，也不能取代學科專家。Skill 會引導
宿主模型遵循「證據優先」的 AP 工作流程，只在需要時載入對應課程資料，並以本機
validator 驗證可以機械判定的聲明。

## GPT-6 Astra 適配

三個 Skill 都已加入適配 Astra 的互動約定：完成使用者要求的交付內容，只追問會
改變判斷的資訊，接受中途更正與模式切換，並讓 Coach 每輪只推進一個動作、等待
真實作答。這些調整依據 2026 年 9 月 5 日核對的
[Astra 官方提示指引](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-6-astra)；
這些指令也可用於其他具備相應能力的宿主模型。

在提供該模型的宿主中選擇 `gpt-6-astra`。Skill 本身不會切換模型，也不提供帳號
存取權限。使用 Codex 設定時，在你選用的 `config.toml` 中設定以下欄位；已有
同名欄位時更新原值，不要重複新增：

```toml
model = "gpt-6-astra"
model_reasoning_effort = "medium"
```

設定欄位見 [Codex 官方設定參考](https://learn.chatgpt.com/docs/config-file/config-reference)。
`medium` 是本專案建議的起點，並非經過實測的最佳值。遷移時可保留既有且適用的
推理強度；宿主支援時，簡單追問可用 `low`，複雜審閱可用 `high`。Astra 官方列出的
推理強度不包含 `none` 和 `minimal`；實際可選項由宿主決定，見
[模型規格](https://developers.openai.com/api/docs/models/gpt-6-astra)。

各科新增按需載入的證據審閱資料，處理圖片、來源或模型解讀及出題品質：區分可讀
證據與不確定轉錄，先檢查學科推理，再檢查 Topic 中繼資料，並核對原創題的條件
是否充分、答案是否成立。Coach 協議會在更正後保留仍有效的證據，以簡短的對話
摘要銜接長對話，並隱藏答案。回答會遵循使用者指定的英文、簡體中文或繁體中文。

## 實際功能

| 模式 | 實際行為 |
| --- | --- |
| **Generate** | 在使用者指定的課程、Topic、題型、難度、語言和答案可見性限制內，產生原創講解、練習題、stimulus、資料集或 worked example。 |
| **Review** | 檢查使用者提供的作答，找出第一個實質性錯誤及其後果；若沒有實質性錯誤，就明確說明，不捏造問題。 |
| **Advisor** | 只依據學習者提供的證據，排序一至三個範圍明確的任務；每個任務包含優先原因、練習動作和可觀察的通過標準。 |
| **Coach** | 執行一次只推進一題的互動循環：診斷、給一個最小提示、等待真實作答、確認修正，再用遷移題檢驗能否獨立應用。 |

核心使用者是願意提供真實作答、需要針對性回饋、逐級提示或符合 AP 範圍之原創
練習的 AP 學生。Skill 會維持使用者指定的回答語言，因此也適合雙語學習環境。
教師、導師和內容審核者可以把 Generate、Review 與課程範圍驗證作為第二道檢查。
它並非官方評分服務、AP Classroom 替代品、通用升學顧問，也不適合用於個人臨床
判斷，尤其是 Psychology Skill。

三個實作有意採用不同方案：

| Skill | 課程專屬實作 |
| --- | --- |
| 數學 | 維護 96 道原創題、32 個診斷模式：Precalculus 8 個、Calculus AB 16 個、精選 BC-only 8 個；每個模式各有診斷題、同構確認題和遷移題。AB 在 Units 1–8 每單元維護兩個模式，Precalculus 在 Units 1–4 每單元維護兩個模式；BC 重用 AB 共有內容並增加 Units 6–10 的精選涵蓋範圍。題庫並未涵蓋全部 Topic。 |
| Psychology | 在目前五個 Units 內按需產生原創題，涵蓋概念應用、研究設計、資料／統計、AAQ 與 EBQ；不宣稱擁有靜態題庫或跨對話學習檔案。 |
| Biology | 在目前八個 Units 內按需產生原創題，涵蓋機制、模型、實驗設計、資料／統計、MCQ 與六類現行 FRQ；不宣稱擁有靜態題庫或跨對話學習檔案。 |

下列架構基準已依 College Board 的
[2026–27 課程變更表](https://apcentral.collegeboard.org/courses/how-ap-develops-courses-and-exams/course-changes-overview)
核對：

| 課程 | 儲存庫基準 |
| --- | --- |
| AP Precalculus | Fall 2026 CED 及其勘誤 |
| AP Calculus AB/BC | Fall 2020 CED，含 Fall 2026 勘誤 |
| AP Psychology | Fall 2025 五單元 CED，含 October 2025 勘誤 |
| AP Biology | Fall 2025 CED，含 June 2025 與 June 2026 勘誤 |

AP Precalculus 的 exam-oriented 支援現已涵蓋 May 2027 考試的 Units 1–3、MCQ
和四類具名 FRQ：Function Concepts、Modeling a Non-Periodic Context、
Modeling a Periodic Context、Symbolic Manipulations；Unit 4 仍僅用於
instructional 內容。

來源中繼資料最後核對於 2026 年 8 月 28 日至 9 月 3 日。考試形式和政策屬於具
時效性的資訊，使用時仍須重新查驗目前的官方來源。

## 端到端工作流程

1. **路由：**依使用者意圖選擇 Generate、Review、Advisor 或 Coach。
2. **鎖定限制：**維持使用者指定的課程、Topic、題型、難度、語言、答案可見性和
   已提供的證據；發生衝突時明確說明，不擅自替換條件。
3. **只載入必要 contract：**使用對應課程的 catalog 與 boundary package；若為
   exam-oriented 任務，再讀取 assessment-task reference；若為 Coach，再讀取
   session protocol；圖片、複雜來源解讀與原創考試練習題另按需讀取證據審閱資料。
4. **推理、對應、驗證：**獨立完成或審閱學科推理，分別對應 content 與 Practice，
   再以課程 validator 驗證所有顯示的 Topic 和已聲明的考試題型 contract。
5. **依所需範圍回答：**輸出內容、首錯 Review、一至三個任務的 Advisor 計畫，或
   嚴格一個 Coach 動作。除非符合數學 Skill 的獨立 opt-in 持久化 contract，否則
   狀態只保留在對話中。

## 自適應 Coach 循環

Coach 是「依作答證據調整」，不會只依分數判定。它不會僅憑低分、錯選項、耗時慢
或 Topic 標籤就推斷錯因。完整循環如下：

1. 從完整題目／stimulus 和學生真實作答開始。若缺少必要證據，只索取缺少的那項
   資料，或給一道原創診斷題，然後等待。
2. 找出最早出現的實質性斷點，區分觀察事實、一個範圍有限的原因假說、一個合理
   的替代解釋，以及尚未確定的部分。
3. 給最少但有效的提示。Hint level 0 只有題目；level 1–3 依序從指向關鍵特徵、
   局部不完整的 setup，推進到示範一個卡住的步驟。每次只升一級，不虛構學生
   的下一步。
4. 學生自行修正後，給一道不含答案、未見過的同構確認題；在 hint level 0 獨立
   通過後，再給一道改變關鍵情境、表徵或題型、未見過的遷移題。
5. 只有在 hint level 0 獨立完成未見過的遷移題並達到已聲明的通過標準，才把這個
   具體介入標為 `passed`。在引導下完成仍為 provisional；一個介入通過，不代表
   已掌握整個 Unit 或課程。

數學 Coach 可以從已稽核題庫以確定性 selector 選出下一道維護題；Biology 和
Psychology 則按需產生原創確認題與遷移題。所有實作每輪最多提供一道新 Coach 題。

範例：

```text
$ap-calculus-advisor 請 Coach 我完成這份 AP Precalculus Unit 2 解答，每次只給一個提示。
$ap-calculus-advisor 請 Coach 我完成這份 AP Calculus BC Unit 10 解答，每次只給一個提示。
$ap-psychology-advisor 請從這份 AP Psychology 作答開始 Coach 我，每次只給一個提示。
$ap-biology-advisor 請從這份 AP Biology 作答開始 Coach 我，每次只給一個提示。
```

維護題目與按需產生的題目均為原創練習，並非 AP Classroom、Progress Check、
Practice Exam 或其他 College Board 保密資料；隱藏答案不會出現在面向學習者的
回應中。在取得真實、去識別化的學習者資料之前，數學題庫的難度標籤一律為
`provisional`。

## 課程驗證與幻覺防護

儲存庫結合模型行為指引與可機器檢查的控制措施：

- Topic citation 會先以 Unicode NFKC 正規化，再與內部 framework catalog 的完整
  citation 精確比對。Validator 回傳 canonical citation 和考試範圍；格式錯誤、
  捏造或課程不符的對應會失敗。
- Content Topic 與 Mathematical／Science Practice 是兩個獨立聲明。若證據只能
  確定跨課程 Practice，Skill 會把 Topic 保留為 `not established`，不為了填欄位
  而猜測。
- Boundary package 會檢查 assessed 與 instructional 範圍、已登錄的 exclusion
  和 high-risk method、舊架構標記及考試題型 contract。完整題型驗證會檢查必要
  的 Practice／representation family，不把 Topic 相符當作「符合 AP 題型」的證明。
- 證據規則禁止虛構學生作答、用時、信心、獨立性、研究、資料、步驟、統計結果、
  引用、評分指引和掌握程度結論；合成的練習 stimulus 與資料必須標為 synthetic。
- 所有題目均為原創，不重製 AP Classroom、Progress Check 或 Practice Exam 等
  保密資料。對 released question 給數值評分時，必須同時具備同一考試年份、form
  和題號的原題與官方 scoring guide；否則只能給明確標為 unscored 的概念性回饋。
- 隱藏答案、解析、干擾選項診斷、題目連結和 selector 理由不會出現在面向學生的
  Coach 回合。學生可以主動要求完整解答，但該次輔助作答不能計為獨立證據。
- Self-check、單元測試、schema、數學稽核雜湊、行為案例和 release gate 共同檢查
  這些 contract 是否維持內部一致。

這些控制措施能減少常見的幻覺來源，但無法確保模型輸出絕對無誤。Validator 的
`pass` 只確認對應與已聲明的邊界中繼資料，不證明學科推理、教學品質、官方 rubric
對齊，也不證明具時效性的考試政策此刻仍有效。因此，學科內容仍須獨立核查；
會變動的考試資訊仍須重新查驗目前的官方來源。

## 隱私與選用的本機狀態

所有 Coach 預設只保留在目前對話中，不寫入磁碟；Biology 和 Psychology Coach
始終維持 session-only。三門數學課程的本機持久化必須同時符合兩項條件：使用者
明確授權，且由呼叫者提供儲存庫外的具體 data directory。狀態只儲存假名 profile
ID、課程、作答、證據、提示／獨立性欄位和複測佇列；不要求姓名或電子郵件。

請使用呼叫者明確選擇的外部目錄（以下路徑僅為範例）；初始化其他數學課程時，
把 `calc-ab` 替換為 `precalculus` 或 `calc-bc`：

```powershell
python ap-calculus-advisor/scripts/update_learner_state.py --data-dir "D:\learner-data\calc-ab-demo" `
  --as-of "2026-08-31T12:00:00Z" --evidence-json init --profile-id demo_profile --course calc-ab
python ap-calculus-advisor/scripts/update_learner_state.py --data-dir "D:\learner-data\calc-ab-demo" `
  --as-of "2026-08-31T12:10:00Z" --evidence-json record --attempt-file attempt.json
python ap-calculus-advisor/scripts/update_learner_state.py --data-dir "D:\learner-data\calc-ab-demo" `
  --as-of "2026-08-31T12:10:00Z" --evidence-json queue
```

`clear-test-profile` 只能用於以 `--test-data` 初始化的目錄，且只刪除該精確
profile 的已識別檔案；它並非通用刪除命令。真實學習者資料必須保存在儲存庫外，
不得提交。

```powershell
python ap-calculus-advisor/scripts/update_learner_state.py --data-dir "D:\learner-data\calc-ab-test" `
  --evidence-json init --profile-id test_profile --course calc-ab --test-data
python ap-calculus-advisor/scripts/update_learner_state.py --data-dir "D:\learner-data\calc-ab-test" `
  --evidence-json clear-test-profile --profile-id test_profile
```

## 安裝與呼叫

進入 Codex 後，使用 Skill Installer：

```text
$skill-installer Install the skill at path ap-calculus-advisor from iyorixy/AP-advisor-Skill as ap-calculus-advisor.
$skill-installer Install the skill at path ap-psychology-advisor from iyorixy/AP-advisor-Skill as ap-psychology-advisor.
$skill-installer Install the skill at path ap-biology-advisor from iyorixy/AP-advisor-Skill as ap-biology-advisor.
```

儲存庫根目錄包含僅用於開發的測試與發布證據，因此有意不作為可安裝的 Skill；
上述三個路徑可避免將這些檔案複製到使用者的安裝目錄。

Codex 會自動偵測新安裝的 Skill；若某個 Skill 未出現，再重新啟動 Codex。
呼叫範例：

```text
$ap-calculus-advisor 審閱這份 AP Calculus BC 解答並指出第一個實質性錯誤。
$ap-calculus-advisor 一步一步 Coach 我完成這道 AP Precalculus Unit 3 題。
$ap-calculus-advisor 一步一步 Coach 我完成這道 AP Calculus AB Unit 6 題。
$ap-calculus-advisor 一步一步 Coach 我完成這道 AP Calculus BC Unit 9 題。
$ap-psychology-advisor 請從這份 AP Psychology 作答開始 Coach 我，每次只給一個提示。
$ap-biology-advisor 請從這份 AP Biology 作答開始 Coach 我，每次只給一個提示。
```

以上命令適用於從 GitHub 獨立安裝。若要加入通用外掛目錄，目前的
[OpenAI 官方文件](https://developers.openai.com/codex/skills)建議將可重用的多 Skill
產品封裝為 plugin；這是另一個發布管道。

## 驗證儲存庫

在儲存庫根目錄執行（必要時將 `python` 換成 `python3`）：

```bash
python ap-calculus-advisor/scripts/validate_topic_code.py --self-check --evidence-json
python ap-psychology-advisor/scripts/validate_topic_code.py --self-check --evidence-json
python ap-biology-advisor/scripts/validate_topic_code.py --self-check --evidence-json
python scripts/run_evals.py --self-check --evidence-json
python -m unittest discover -s tests -v
python scripts/check_release.py --evidence-json
```

三條 validator self-check 分別涵蓋三個 Skill 的對應與邊界套件。release gate
還會驗證全部 Coach 協議產物、數學 assessment contract、錯因／題目交叉參照、
數學稽核雜湊、學習狀態安全、selector 確定性、行為評審門檻、Python 編譯與純標準
函式庫依賴、單元測試，以及已安裝的 skill-creator validator。只有所有命令都以
結束代碼 `0` 完成，且最後一條輸出小寫 `"overall_status":"pass"`，才視為儲存庫
驗證通過。

這些是本機檢查，包含已記錄行為評審的一致性驗證；它們不會重新呼叫 Astra，
也不測量學習效果。原有評審記錄仍是歷史證據；Astra 專項行為尚未使用新的
模型輸出進行評估。

數學 selector 有意採用透明規則，不引入 BKT、IRT、向量檢索或看似精確的 mastery
機率。彙總校準匯出只提供描述性統計；樣本不足時回傳 `insufficient_data`。後續
經驗校準必須使用真實、經同意且去識別化的作答資料，並另行評審。

## 授權條款與 AP 聲明

MIT。「AP」是 College Board 的商標。本專案不是 College Board 官方出版物，也
未獲其認可。涉及考試的時效性資訊，請以 College Board 目前的官方來源為準。
