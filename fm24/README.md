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
| `data/fm24.sqlite` | 產出物（未進版控） |
| `dist/index.html` | 產出物（未進版控） |

## 目前涵蓋範圍

五個視圖：王朝總覽、賽季檔案、陣容名冊（可排序、含六維能力雷達）、編年史、檔案完整性報告。
資料範圍聚焦巴塞隆納 2023/24 – 2034/35，其餘 90 餘張表已在 SQLite 中，尚未接進前端。

## 下一步候選

- 身分解析控制台：把 437 筆 `UNRESOLVED_IDENTITY` 做成可互動比對、一鍵確認並寫回
- 全世界視圖：接上其他聯賽的 `Domestic_League_Standings` 與各國獎項表
- Time travel 查詢：利用 append-only + `Snapshot_Date` 重現「某個時間點所知的世界」
