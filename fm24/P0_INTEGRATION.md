# P0 接入與驗收

基準：FM24_World_Master_v6.4.0_award_delta_2034_35.final，122 表、27,124 列。
主檔只讀；原始資料不回寫。八張 P0 均已接入，P1/P2 仍保留於 `PENDING_INTEGRATION`。

| 工作表 | 原始列數 | 讀者入口與採用界線 |
|---|---:|---|
| Source_Index | 198 | 來源與期間頁、各事實的可展開來源面板；不輸出 Local_Path |
| Period_Dim | 78 | 期間別名合為 54 個唯一期間，保留年／賽季區別；賽季與證據依受控 ID 關聯 |
| Award_Fact_Source_Links | 1,186 | 榮譽殿堂、球員名錄詳情；多份來源不增加獎項次數 |
| Award_Index | 45 | 榮譽殿堂獎項目錄，保留資料狀態、粒度、原表與限制說明 |
| Season_Master_Field_Provenance | 108 | 12 季各欄位群組的來源日期、涵蓋範圍與採用狀態 |
| Barcelona_Player_Season_Honours | 178 | 巴薩生涯頁／球員名錄詳情；原樣呈現 A1、出場與五項歸屬，不推算世俱盃 |
| Barcelona_Player_Season_Stats | 179 | 178 筆逐季核對與 1 筆說明列；不再次加進生涯總計 |
| Barcelona_Transfer_Totals | 24 | 各賽季來源顯示的轉入、轉出總額；與淨支出分開，不重算或補差額 |

## 關聯方法與邊界

`Canonical_Award_Facts` 仍有 1,132 筆正式事實。每筆保留原始名次、身分狀態與主來源，
來源關聯另放於 `evidence`。目前 1,186 筆關聯全部連至 1,099 筆正式事實；
33 筆 European Golden Shoe 事實沒有關聯表列，仍顯示自己的主來源。

關聯支援主檔中兩種已觀察到的 Fact_Key 格式。舊 key 無法重建時，只在
Source_ID、Origin_Sheet、Origin_Row 同時唯一的情況下連接，並明示關聯方式。
共享 key 或模糊定位不猜測，轉列來源頁的未能唯一關聯證據。
Excel 列號不冒充原始 TXT 行號。

獎項頁可分別篩選第一名、其餘名次、最佳陣容入選。SELECTION 編號不是排名或先發。
目錄中的 45 個名稱不自動當成 45 種完整展示的事實：精確名稱缺少正式事實列時顯示 0，
保留原表資訊，沒有把同表的不同獎項混在一起。

178 筆巴薩逐季統計與正式採用總表的可比欄位一致。出場 0 的主檔成員仍可有 A1 冠軍歸屬，
網站不另訂出場門檻。未在 30 人巴薩生涯主表中的球員，仍能從完整球員名錄查看證據。
所有缺值保留未知；差異或非唯一採用列有專用狀態，絕不覆寫正式統計。

來源名冊的引用數只量測畫面列出的五張事實表，不能拿來宣稱其他來源從未使用。
用途標籤可重疊；`coverage.py` 僅驗證查詢有沒有讀取，欄位與畫面契約由新增測試及瀏覽器驗收補足。

## 重現

2026-09-23 實跑結果：**134 passed in 33.48s，0 skipped**。
覆蓋率宣告與讀取檢查無矛盾；剩餘清單為 P1 11 張、P2 13 張，共 707 列，P0 為 0。

在 `fm24/` 中執行：

```bash
python -m pip install -r requirements-dev.txt
python etl.py <主檔.xlsx>
python -m pytest test_resolver.py test_evidence.py -q
python build_site.py --standalone -o archive.html
python build_site.py --json dist/fm24-data.json
python coverage.py
python audit_brief.py -o dist/audit-brief.md
```

已驗證：整份工作簿重新匯入、逐列證據保存、重複與歧義 key、名次／入選粒度、
多日期欄位、官方轉會原文、零與未知、數據差異不覆蓋、私有路徑不輸出、
缺 OpenCC 的 API 拒絕與明確降級標記，以及嵌入資料不能結束 script 標籤。

瀏覽器驗收包含獎項篩選、多來源展開、賽季切換、官方總額、名錄外球員與逐欄核對；
15 個導覽頁均可渲染，驗收期間沒有瀏覽器 JavaScript 錯誤。
測試套件須在實際匯入工作簿後執行；沒有資料庫時跳過的測試不能稱為完整通過。
