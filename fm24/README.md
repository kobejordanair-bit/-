# 藍紅檔案館 — FM24 World Master 資料管線

把 `FM24_World_Master_v6.4.0` 這份 116 張工作表的 Excel 檔，轉成可查詢的 SQLite，
再產出一個單檔的靜態檔案館網站。

## 為什麼不直接開 Excel

這份工作簿實際上是一個塞在 `.xlsx` 裡的資料倉儲：

- **維度表**：`Player_Dim`、`Club_Dim`、`Nation_Dim`、`Period_Dim`、`Competition_Dim`
  （注意：每列是一個「別名」，不是一個實體 — 332 名球員攤成 369 列）
- **事實表**：`Player_Club_Season_Totals`、`Canonical_Award_Facts`、`Domestic_League_Standings` …
- **來源血緣**：每列都帶 `Source_ID` / `Verification_Status` / `Observation_ID` / `Fact_ID`
- **身分解析**：`Record_Identity_Map` 10,444 列
- **資料品質**：`Data_Issues`、`Award_Resolution_Status`

Excel 能存這些，但不能查。這個管線讓 Excel 降級成「輸入格式」。

## 用法

```bash
pip install openpyxl
python3 etl.py path/to/FM24_World_Master_v6.4.0.xlsx    # -> data/fm24.sqlite
python3 build_site.py                                    # -> dist/index.html
```

匯入回流（從站台匯出的 JSON 併回資料庫）：

```bash
python3 ingest.py fm24-imports-2035-06-02.json           # 預演，不寫入
python3 ingest.py fm24-imports-2035-06-02.json --commit  # 實際寫入
```

`ingest.py` 以 `Observation_ID` 做內容雜湊，同一份匯出重跑是 no-op 而不是重複插入。
資料落在 `Ingest_*` 系列表（刻意與工作簿自己的 `Import_Observations` 分表），
`etl.py` 重建資料庫時會把它們原樣搬過去，不會被 xlsx 覆蓋掉。

`dist/index.html` 是完全自足的單一檔案（約 240 KB，資料內嵌為 JSON），
可直接丟 GitHub Pages 或任何靜態主機。

## 設計原則

**ETL 不做型別轉換。** 所有欄位一律存成 TEXT。工作簿裡 `Apps` 同時出現 `0(2)` 和 `2`，
`PassPct_Raw` 是 `85%`，強制轉型會靜默破壞來源原形。解析留給 `build_site.py` 的 `num()`。

**完整性報告由資料自己生成。** `Archive.integrity()` 裡的 findings 不是人工清單，
是每次 build 重新從資料驗證出來的。目前抓到四項，最嚴重的一項：

> 15 名球員在 `PER-S-2034-35` 下同時有 `2034/35` 與 `2034-35` 兩種 `Season_Display`，
> 且 `Club_Raw` 分別寫成「巴塞隆納」與「巴塞罗那」。任何 SUM 都會重複計算。

球員頁面在該球員逐季表格上方會直接掛警告，讓缺陷出現在它真正造成傷害的地方。

## 檔案

| 檔案 | 用途 |
|---|---|
| `etl.py` | xlsx → SQLite，1:1 鏡射 116 張表 |
| `build_site.py` | SQLite → 網站資料負載（JSON）並注入模板 |
| `template.html` | 前端：無框架，手繪 SVG 圖表，深／淺色主題 |
| `ingest.py` | 匯出的 JSON → SQLite，append-only 且冪等 |
| `data/fm24.sqlite` | 產出物（未進版控） |
| `dist/index.html` | 產出物（未進版控） |

## 視圖

**世界** — 世界總覽（五大聯賽冠軍版圖、歐冠決賽、國際賽）、聯賽積分榜（含快照切換）、
榮譽殿堂（金球獎完整前三名 + 21 種獎項歷屆得主）、編年史（1,334 筆事件可搜尋）

**檔案** — 球員名錄（332 個受控身分）、巴薩王朝／賽季／陣容（含六維能力雷達）

**工具** — 匯入資料、檔案完整性報告

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

## ETL 偵測到的缺陷

每次 build 由 `Archive.integrity()` 重新從資料驗證，不是人工清單。目前六項，兩項高風險：

> **2034/35 同一球員存在兩筆賽季總計** — 15 名球員在 `PER-S-2034-35` 下同時有
> `2034/35` 與 `2034-35` 兩種 `Season_Display`，`Club_Raw` 分別寫成「巴塞隆納」與「巴塞罗那」。
> 任何 SUM 都會重複計算。球員頁面在逐季表格上方直接掛警告。

> **聯賽積分榜同賽季存在多份快照** — 部分聯賽賽季同時有 `PROVISIONAL_AS_OF_*`（賽季中）
> 與 `FINAL_SOURCE_ADOPTED_*`（賽季末）兩份表。不看 `Season_Status` 直接查會得到
> 兩倍隊伍數與錯誤的冠軍。本站只採 FINAL，並提供快照切換。

其餘：轉會方向欄位混用中英文編碼、630 列以字串 `'NULL'` 表示空值、
同一 `Club_ID` 對應多種原始寫法、賽季主表的來源空值。

## 下一步候選

- 身分解析控制台：把 437 筆 `UNRESOLVED_IDENTITY` 批次比對、一鍵確認並寫回
- Time travel 查詢：利用 append-only + `Snapshot_Date` 重現「某個時間點所知的世界」
- 把匯入的觀測直接併回 .xlsx，讓工作簿與 SQLite 雙向同步
