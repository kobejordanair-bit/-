# 藍紅檔案館 — FM24 World Master 資料管線

把 `FM24_World_Master_v6.4.0_award_delta_2034_35.final` 的 122 張工作表、27,124 列資料轉成可查詢的 SQLite，
再產出一個單檔的靜態檔案館網站。

新增 **總教練互動中心**：王朝實驗室、球員對決、足壇時光機、德比劇場、PNG／SVG 戰績海報、王朝夢幻 XI 與全站快速搜尋。
使用方式、資料口徑與驗收見 [互動功能交付](INTERACTIVE_FEATURES.md)。
`experience.js`、`experience.css` 是可維護的來源模組，建置時全部嵌入 `archive.html`，開啟網站不需要額外 JavaScript 套件。

目前原定 P0／P1／P2 的 32 張表均已完成接入，待接入清單為 0。
最新全站 26 頁核對、榮譽比較與 240 項測試見 [全頁檢查報告](ALL_PAGES_REVIEW.md)。
前一輪完整性修正見 [完整性修正報告](INTEGRITY_REPAIR.md)。
P0／P1／P2 交付見 [接入完成報告](INTEGRATION_COMPLETE.md)，
來源關聯與逐季核對的設計見 [P0 接入驗收](P0_INTEGRATION.md)。
這不表示 122 張表的全部欄位都已採用為正式統計。下方比對器研究中的舊統計屬歷史開發紀錄；
目前數字以重新建置的輸出與 `coverage.py` 為準。工作簿是正式主檔，網站是衍生閱讀介面。

## 為什麼不直接開 Excel

這份工作簿實際上是一個塞在 `.xlsx` 裡的資料倉儲：

- **維度表**：`Player_Dim`、`Club_Dim`、`Nation_Dim`、`Period_Dim`、`Competition_Dim`
  （注意：每列是一個「別名」，不是一個實體 — 332 名球員攤成 369 列）
- **事實表**：`Player_Club_Season_Totals`、`Canonical_Award_Facts`、`Domestic_League_Standings` …
- **來源血緣**：依表格保留 `Source_ID` / `Verification_Status` / `Observation_ID` / `Fact_ID`
- **身分解析**：`Record_Identity_Map` 10,444 列
- **資料品質**：`Data_Issues`、`Award_Resolution_Status`

Excel 保留正式主檔，SQLite 與網站提供跨表查詢、來源追溯及互動閱讀。

## 用法

```bash
pip install -r requirements.txt
python3 etl.py path/to/FM24_World_Master_v6.4.0.xlsx    # -> data/fm24.sqlite
python3 build_site.py                                    # -> dist/index.html（Artifact 用）
python3 build_site.py --standalone \
    -o dist/blaugrana-archive.html                       # -> 可離線開啟的完整文件
```

給程式或模型讀的純資料：

```bash
python3 build_site.py --json dist/fm24-data.json      # 無網頁外殼，含來源與歷史資料
```

**三種產出的差別**：預設輸出是**片段**，交給 Artifact 平台包上它自己的文件外殼。
用 `file://` 直接開的話沒有那層外殼，瀏覽器會自己猜編碼——**整頁中文會變亂碼**。
`--standalone` 會補上 `<!doctype>`、`<meta charset="utf-8">` 與 viewport，可直接雙擊開啟。
`--json` 則完全不產生網頁，只輸出資料本身（開頭附 `_readme` 說明各區塊），
適合餵給另一個工具或模型——它們不需要穿過一整個檢視器才讀得到檔案。

## 儲存後端：一套 API，兩種實作

`db` 與 `downloads` 是 claude.ai 的執行時能力，在 GitHub Pages 或 `file://` 上都取不到。
但控制台的價值就在「記下決定」，所以那不能降級。`getDb()` 會偵測環境並回傳對應後端：

| 環境 | 儲存 | 匯出 |
|---|---|---|
| claude.ai Artifact | 平台共用文件庫，跨裝置可見 | 平台 download 能力 |
| GitHub Pages / `file://` | `localStorage`（本機瀏覽器） | Blob 連結下載 |
| 停用網站資料的瀏覽器 | 無（誠實告知，不假裝有） | 無 |

`createLocalDb()` 實作了呼叫端已在用的那一小塊介面（`collection().orderBy().limit().get()`、
`doc().set()`、`doc().delete()`），所以上層程式碼一行都沒改。

Blob 下載這點值得說明：**Artifact 檢視器的沙箱會擋掉頁面自己發起的下載**，平台才需要提供
download 能力。離開那個沙箱後，一般的 `<a download>` 就能用，所以沒有東西需要降級。

頁面會顯示目前用的是哪個後端，不會讓你以為決定存到了別的地方。

## 部署到 GitHub Pages

`fm24/archive.html` 是已建置的完整文件，直接 commit 進版本庫供 Pages 服務。

1. 將已驗證的程式與建置產物提交至預設分支 `main`
2. GitHub → Settings → Pages → Source 選 **Deploy from a branch**，分支選預設分支、資料夾選 **/ (root)**
3. 幾分鐘後開 `https://<帳號>.github.io/<repo>/fm24/archive.html`

根目錄的 `.nojekyll` 是空檔案，作用是讓 Pages 跳過 Jekyll 前處理、原樣提供檔案。

更新內容時重跑：

```bash
python3 etl.py <你的 xlsx>
python3 build_site.py --standalone -o archive.html
git add fm24/archive.html && git commit && git push
```

`archive.html` 是唯一需要進版控的產出物（約 6 MB，隨主檔資料量變動）；`dist/` 與 `data/*.sqlite` 仍在 `.gitignore` 裡。


`opencc` 在建置時必須可用。CLI 和直接呼叫建置 API 都預設拒絕缺少簡繁轉換的環境。
僅明確使用 `--allow-degraded`（API 為 `allow_degraded=True`）時允許降級，
HTML、JSON、稽核報告與覆蓋率結果會保留警示；降級数字不能與完整環境比較。

回流（從站台匯出的 JSON 併回資料庫）：

```bash
python3 ingest.py fm24-imports-2035-06-02.json                       # 預演
python3 ingest.py fm24-imports-2035-06-02.json --commit              # 資料批次
python3 ingest.py fm24-identity-decisions-*.json --identity --commit # 身分決定
```

`ingest.py` 以 `Observation_ID` 做內容雜湊，同一份匯出重跑是 no-op 而不是重複插入。
資料落在 `Ingest_*` 系列表（刻意與工作簿自己的 `Import_Observations` 分表），
`etl.py` 重建資料庫時會把它們原樣搬過去，不會被 xlsx 覆蓋掉。

`dist/index.html` 為 Artifact 片段；部署至 GitHub Pages 使用 `--standalone` 產生的 `archive.html`。

## 設計原則

**ETL 不做型別轉換。** 所有欄位一律存成 TEXT。工作簿裡 `Apps` 同時出現 `0(2)` 和 `2`，
`PassPct_Raw` 是 `85%`，強制轉型會靜默破壞來源原形。解析留給 `build_site.py` 的 `num()`。

**完整性報告由資料自己生成。** `Archive.integrity()` 每次建置重新檢查來源。
逐季只採明示 ADOPTED 的觀測；舊快照與問題紀錄保留查證，不相加重算正式總計。
完整性頁區分網站已處理、主檔待核對與來源保留未知，最新範圍見全頁檢查報告。

## 檔案

| 檔案 | 用途 |
|---|---|
| `etl.py` | xlsx → SQLite，1:1 鏡射輸入工作簿 |
| `resolver.py` | 三種實體的比對：簡繁正規化、球員姓氏否決制、俱樂部綴詞剝除、賽事層級否決、分群與重複偵測 |
| `test_resolver.py` / `test_evidence.py` | 身分解析、資料採用與 P0 來源關聯回歸測試 |
| `evidence.py` | P0 來源關聯、期間別名、逐季核對與讀者頁補充資料 |
| `build_site.py` | SQLite → 網站資料負載（JSON）並注入模板 |
| `template.html` | 前端：無框架，手繪 SVG 圖表，深／淺色主題 |
| `ingest.py` | 匯出的 JSON → SQLite，append-only 且冪等；`--identity`／`--clubs`／`--competitions` |
| `data/fm24.sqlite` | 產出物（未進版控） |
| `dist/index.html` | 產出物（未進版控） |

## 視圖

**世界** — 世界總覽（五大聯賽冠軍版圖、歐冠決賽、國際賽）、聯賽積分榜（含快照切換）、
榮譽殿堂（37 種獎項、1,636 筆去重展示紀錄）、編年史（1,346 筆來源事件可搜尋與逐批載入）

**檔案** — 球員名錄（332 個受控身分）、巴薩王朝／賽季／陣容（含六維能力雷達）

**工具** — 球員身分、俱樂部身分、賽事身分三個控制台，匯入資料、檔案完整性報告

## 身分解析（歷史開發紀錄）

445 筆獎項列分屬 212 個未解析姓名。比對在 build time 跑（`resolver.py`），不在瀏覽器：
需要 OpenCC 做簡繁正規化，也需要把檔案已接受的每一筆「原始名→ID」關聯攤開成索引。

索引來源：`Player_Dim` 的正名與別名、`Record_Identity_Map` 一萬多列已確認關聯、
`Canonical_Award_Facts` 已綁定的列。共 351 組索引鍵。

**比對規則：姓氏否決制。** 中文譯名的「名」重複率極高——路易斯、多米尼克、亞歷山德羅
滿街都是——所以名不能承擔配對，姓才是鑑別點。姓氏相似度低於 0.5 直接否決整個配對，
分數為 `姓 × 0.7 + 名 × 0.3`。

**字串相似度取三種量度的最大值**：bigram Dice、字元集重疊、編輯距離比。前兩者對
「只差一個字的長名字」嚴重低估——`馬克安德雷特爾施特根` vs `馬克安德烈特爾施特根`
在 bigram 下只有 0.78，但那顯然是同一個人——編輯距離把這類救回來（0.90）。

**聯賽與賽季加權。** 獎項所屬聯賽優先取自該列的 `Club_ID`（315/437 列有），
其次才由工作表名推斷（`Bundesliga_Elf_des_Jahres` → Bundesliga；跨聯賽獎項如
European Golden Shoe 刻意不推斷）。候選人的聯賽由 `Player_League_Career.League_Raw`
與其效力俱樂部推得，目前覆蓋 181 名球員、90 間俱樂部。

聯賽相符 +0.10，賽季在檔 +0.06。聯賽不符時**不是一律扣分**：姓名證據已達 0.90 以上者
只標註「可能為轉會」而不動分數，否則扣 0.14。沒有這個豁免，`特爾施特根` 這個真配對
會因為獎項掛在法甲俱樂部而被扣到 weak。

實際結果（刻意保守）：

| 判定 | 數量 | 意義 |
|---|---|---|
| 正規化後完全相同 | 2 | 可直接確認 |
| 高可信候選 | 5 | 維尼修斯·儒尼奧爾、特爾施特根、維卡里奧、范佩西、霍伊倫 |
| 需人工判斷 | 13 | 多為同姓不同人（利桑德羅 vs 安東尼·馬丁內斯） |
| 查無候選 | 192 | **這才是大宗** |

加上下文前是 2 / 4 / 19 / 187。淨效果是把 7 個同姓不同人的假配對降級，
同時因為編輯距離救回 `馬泰斯·德里赫特`（de Ligt）這個先前被完全濾掉的真配對。

**已知限制**：`路易斯·迪亞斯` vs `路易斯·蘇亞雷斯` 的姓氏相似度恰為 0.50，剛好通過閘門，
會以 71% 出現在 weak 待審清單。同樣的門檻放行了 de Ligt 的真配對，所以保留現狀——
weak 本來就是要人判斷的桶子，不是宣稱配對成功。

那 187 個不是比對失敗，是這些球員從來沒被收錄過——德甲、義甲年度最佳陣容裡的名字，
工作簿只控制 332 個身分。所以控制台的工作是**分流與建檔**，不是全部配對。

控制台也會先把積欠名單**彼此**分群（避免同一人拿到多個新 ID），目前偵測到 1 組
（`阿瑙德·卡里姆恩多` / `阿瑟德·卡里姆恩多`，一字之差）。

決定存進站台的 `db`，匯出後由 `ingest.py --identity` 寫入 `Ingest_Identity_Decisions`，
`new` 會自動分配下一個可用的 `P-nnnn`。**工作簿本身不會被改寫。**

## 俱樂部身分

與球員是**不同性質的問題**，所以用不同的比對法。俱樂部名的差異來自綴詞而非音譯：
`里爾` 與 `里爾足球俱樂部` 是同一隊、`VfB斯圖加特` 與 `斯圖加特` 是同一隊。
`club_key()` 先剝掉 `足球俱樂部`／`竞赛俱乐部` 等後綴與 `FC`／`VfB`／`RC` 等前綴，再比對。
來源還會用刪節號截斷長名（`多特蒙德足球俱...`），這種以**前綴比對完整名**處理。

控制台分兩個分頁：

**重複身分（12 組）** — 去綴詞後指向同一隊的 Club_ID 配對。每組列出兩邊各有幾列資料、
分別來自哪些表、屬於哪個聯賽，讓你決定保留哪一個。其中 **3 組兩邊都有資料**
（波爾圖二隊 25/6、南安普頓 20/5、多特蒙德 11/5）——這幾組不處理的話，
依 `Club_ID` 分組就會把同一間俱樂部算成兩間。

**未解析引用（64 個字串、438 列）** — 7 個有高可信候選，56 個是從未建檔的球隊
（萊斯特城、水晶宮、門興格拉德巴赫、朗斯…）。

決定同樣匯出後由 `ingest.py --clubs` 寫入 `Ingest_Club_Decisions`，`new` 自動分配下一個
`C-nnnn`，`merge` 記下保留哪個 ID 與併入來源。**`Club_Dim` 本身不會被改寫。**

## 賽事身分

第三種實體，第三種變異模式。賽事名稱的差異來自：

| 類型 | 例子 |
|---|---|
| 贊助商 | `LaLiga EA Sports` / `LaLiga`、`Serie A TIM`、`Ligue 1 Uber Eats` |
| 中英並列 | `西甲 LaLiga`、`英超 Premier League`、`英格蘭足總盃 FA Cup` |
| 淘汰賽輪次 | `Copa del Rey決賽`、`Copa del Rey半決賽第1回合` |

`competition_keys()` 把一個名稱拆成多個索引鍵（原字串、去贊助商、中文半、拉丁半、去輪次），
任一種寫法都能找到同一個賽事。

**但層級數字絕對不能剝。** 第一版分群跑出這種結果：

```
['2. Bundesliga', 'Bundesliga', '德甲 Bundesliga']        ← 2. Bundesliga 是德乙
['LaLiga', 'LaLiga 2', 'LaLiga EA Sports', '西甲 LaLiga']  ← LaLiga 2 是西乙
['Copa del Rey决赛', 'FIFA Club World Cup决赛', 'Supercopa决赛']  ← 靠「决赛」合併的
```

這跟球員「同名不同人」是同一類錯誤：**共用的 token 不帶身分**。所以加了兩道守則——
`tier_signature()` 抽出層級標記（數字、羅馬數字、`1ª`/`2ª` 序數），不同就直接否決；
`strip_stage()` 在比對前把輪次剝掉。修好後 11 組分群全部正確。

### 結果

74 個賽事名稱，`Competition_Dim` 只收錄 13 個，**61 個未受控涵蓋 2,429 列**。
其中 11 組是同一賽事的不同寫法，**光是收斂這 11 組就能處理 2,041 列**。最大一組：
`LaLiga EA Sports`(287) + `LaLiga`(257) + `西甲 LaLiga`(33) = 577 列。

### 出賽分類不是賽事

`Player_Club_Competition_Stats.Competition_Raw` 同時存放賽事名稱**和出賽分類**，
而分類有中英兩套寫法：

| 分類 | 寫法 | 列數 |
|---|---|---|
| 聯賽 | `联赛` 265 / `League` 173 | 438 |
| 洲際 | `洲际级别` 265 / `Continental` 166 | 431 |
| 盃賽 | `杯赛` 265 / `Cup` 161 | 426 |
| 非正式 | `非正式比赛` 253 | 253 |

依此欄分組會把每個分類拆成兩半。`CompetitionResolver.candidates()` 對分類值直接回傳空陣列——
分類永遠不該被配對成賽事。

## 國家：幾乎不用做

60 個國家字串、49 個已建檔，只有兩個問題，規模小到用完整性報告處理即可：

- `N-0001「3國聯辦」` 與 `N-0002「三國聯合主辦」` 描述的是世界盃多國共同主辦，
  **既不是國家隊，彼此也是同一件事的兩種寫法**，卻各佔一個身分編號。
- 5 個 `Host` 值把國家與球場寫在同一欄：`英格蘭；維拉球場（倫敦,英格蘭）`。

## 踩到的坑（二）：SQLite 的雙引號會退化成字串常值

掃描賽事欄位時，`UCL_Knockout_Results.Competition_Raw` 跑出 268 列值為字串 `"Competition_Raw"`，
看起來像標題列被寫進資料。**其實是我自己的 bug**——那張表根本沒有這個欄位，而 SQLite
在雙引號識別字解析不到欄位時**會退化成字串常值而不是報錯**：

```sql
SELECT "Competition_Raw" FROM UCL_Knockout_Results   -- 回傳 268 個字串 'Competition_Raw'
SELECT Competition_Raw   FROM UCL_Knockout_Results   -- 這才會報 no such column
```

差點把這當成資料缺陷回報。現在 `Archive.has()` 會先驗證欄位存在，所有動態欄位查詢都經過它，
並有測試把這個 SQLite 行為釘住。

## 踩到的坑（一）：OpenCC s2t 不是冪等的

`to_trad('里爾')` 會得到 `裏爾`——OpenCC 把已經是繁體的 `里` 當成簡體，轉成「裏面」的裏
（`托` → `託` 同理）。結果是**簡體來源與繁體維度表會正規化成不同字串**：

```
'里尔足球俱乐部' → 里爾足球俱樂部
'里爾足球俱樂部' → 裏爾足球俱樂部      ← 同一隊，對不起來
```

這個 bug 從第一版就存在，靜默地把索引鍵拆成兩份。修法是**迭代到不動點**而不是硬編變體對照表：
兩邊都會收斂到同一個形式，且對任何 OpenCC 這樣處理的字元都有效。修好後球員索引鍵從 351 併成 346，
判定結果未變（確認它是在拆索引而非給錯答案），俱樂部這邊則直接救回 `里尔足球俱乐部` 的 41 列。

## 認知史（time travel）

工作簿的 append-only 模型換來一件一般球員資料庫做不到的事：每個過去的認知狀態都還原得回來。

`timetravel()` 從七張表的 `Snapshot_Date` / `Snapshot` 欄位抽出 16 個觀測日
（2035-01-03 → 2035-06-02），算出每一天檔案「學到了什麼」、哪些球員首次進檔、累計已知多少。
`Player_Attribute_Changes` 再補上兩次快照之間的實際能力值變動。

看得出真實的作業節奏：2035-03-27 一天灌進 1,161 筆（五大聯賽積分榜全量回填），
2035-06-02 是季末定版。

## 匯入流程

站台的匯入頁面走 append-only：**不會覆寫任何既有資料**，只會記下一筆新觀測。

1. 選資料類型（賽季數據／球員檔案／聯賽積分榜／獎項名次／自由欄位）
2. 貼上 Tab 分隔、逗號分隔，或「欄位：值」逐行格式
3. 自動對應欄位（中英文同義詞表），可手動改
4. 對每列比對現有 `Player_ID`：精確 → 模糊（字元重疊率，處理譯名漂移）→ 多候選 → 新身分
5. 寫入待併入區（存在 artifact 的 `db`）
6. 匯出 JSON → `python3 ingest.py <檔案> --commit`

每列都保留原始姓名與比對結論（`exact` / `fuzzy` / `ambiguous` / `new`），
所以之後併入工作簿時可以稽核比對，而不是照單全收。

## 資料採用與已知缺口

目前檢查結果見 [完整性修正報告](INTEGRITY_REPAIR.md) 與 [全頁檢查報告](ALL_PAGES_REVIEW.md)。
季中／季末快照分開展示；只採明示 ADOPTED 的球員逐季觀測。缺值保持未知，俱樂部、賽事及球員身份歧義仍列待核對。
球員榮譽明細、巴薩個人頁與榮譽比較共用同一份去重結果；全站目錄保留未綁定原始姓名，沒有按近似度猜測入帳。
匯入的 `fuzzy` 僅是候選，不能寫入已確認 Player_ID；`ingest.py --commit` 只寫待審表，不自動改寫 Excel。

## 測試

```bash
pip install -r requirements-dev.txt
python3 etl.py <最新版工作簿.xlsx>
python3 -m pytest test_resolver.py test_evidence.py test_history.py test_integrity.py test_experience.py test_player_awards.py -q
node --test test_experience.js
python3 coverage.py
```

每個案例都是看真實資料決定的，其中好幾個記錄著實際出過的 bug——包含 OpenCC 冪等性、
SQLite 雙引號行為、以及那個 `路易斯·迪亞斯` / `路易斯·蘇亞雷斯` 的已知限制。
它們存在的目的是：評分邏輯可以改，但不能無聲地把這些推論撤銷掉。

## 三種實體，三種比對法

同一套字串相似度，但每種實體的「什麼算同一個」規則完全不同：

| 實體 | 變異來源 | 否決規則 |
|---|---|---|
| 球員 | 音譯漂移 | 姓氏相似度過低 → 否決（名重複率太高） |
| 俱樂部 | 公司綴詞 | 剝除綴詞後比對；來源截斷改用前綴比對 |
| 賽事 | 贊助商、中英並列、輪次 | 層級標記不同 → 否決 |

三者共用 `normalise()`／`similarity()`，差異在鍵函式與否決條件。這不是重複程式碼，
是同一個問題在三個領域的不同答案。

## 下一步候選

- 把匯入的觀測與身分決定直接併回 .xlsx，讓工作簿與 SQLite 雙向同步
- 認知史加上「以當日認知重算排行榜」，而不只是統計當日學到什麼
- 把 `Ingest_*` 的決定實際套用回 `.xlsx`，完成雙向同步
- 用已收斂的賽事身分重算聯賽視圖，取代目前寫死的 `league_key()` 對照

