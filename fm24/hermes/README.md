# FM24 截圖 → Excel → 網站

這包把 Hermes 的圖片閱讀與固定匯入程式接在一起。你之後把圖片交給 Hermes；
Hermes 內部完成轉錄與核對，不需要你搬 JSON。只對看不清楚、身份或範圍有矛盾的資料提問。

## 安裝一次

在 **Hermes 實際執行的主機** 解壓安裝包，執行：

```sh
python install.py
```

預設使用現有的 `/opt/data/FM24_World_Current.json` 與 `~/.hermes`，並建立專用 Python 環境。
若實際位置不同，使用 `--hermes-home`、`--registry`、`--state` 指定。
不會掃描資料夾後自行挑「看起來最新」的 Excel，也不會覆蓋 Hermes 既有匯入程式。
依賴下載需要連線；`--use-current-python` 可使用已備妥相依套件的 Python。

安裝器會驗證整包程式、ACTIVE 指向的檔案雜湊與新版來源欄位，完成後寫入 installation.json。
Hermes 重新載入技能後可使用 `fm24-screenshot-flow`；依其介面也可用對應 slash command。
這是技能安裝，不是遠端控制 Hermes 的連線憑證。

## 日常使用

把同一批截圖交給 Hermes，說「更新 FM24 主檔」。技能會保留原圖、核對資料、
產生新版 Excel 與單檔 HTML。只上傳賽季統計也可以，不必每次補拍完整屬性頁。
遊戲日期不清楚時仍須補充；不能用電腦日期代替。

目前固定匯入範圍：球員 Profile、完整屬性、聯賽生涯、原圖列出的生涯總計、
各項俱樂部賽事、俱樂部季總計、身份與層級明確的國家隊統計。
獎項、聯賽排名、獨立轉會與戰術頁尚無本包的匯入 adapter，必須留在待處理項目。
歷史 TXT 中不明國家隊層級或未支援欄位會拒絕，不會悄悄略過後宣稱全部成功。

## 驗收與恢復

- 原始 Master 與每批原圖保留；所有更新先在副本執行。
- 每步驗證主檔 schema、來源、身份、出場數、欄位保護與派生資料。
- 新統計列帶有來源／採用欄位，網站正式比較能讀到；舊 Fact ID 在更新時保持穩定。
- 全批與網站完成後一次切換 ACTIVE；任何一步失敗都保留舊 ACTIVE。
- 原始圖像、TXT、驗證結果和新舊值 ledger 可追溯。相同輸入不重複累加。
- 版本切換使用與既有 Linux 匯入器相同的 registry lock；Windows 也有互斥鎖。
- 保留上一版本 registry，支援校驗目前 SHA 後回復。
- 產生網站檔案不代表已發布到 GitHub Pages。本包不儲存 GitHub 或模型 API 金鑰。

模型自行勾選「核對完成」無法證明 OCR 完全正確；首批上線仍應用真實圖片核對。
本機轉錄測試、故障注入測試與 Hermes 正式主機上的原圖辨識是三種不同驗收，不能混稱。

## 開發與來源

`engine/ORIGIN.json` 保存使用者提供的 FM_World_Import_Repair_v1.zip 原始模組 SHA。
延伸修復：允許沒有屬性頁、來源採用欄位、既有採用列匹配、唯讀來源副本、
榮譽表依實際 13 欄計算表格範圍、保留新版已整理的個人獎項、派生資料只讀正式採用列。
未放寬原有結構驗證；球員截圖匯入不得重寫既有個人獎項與逐季冠軍事實。
Unicode 對照資料授權見 `engine/ICU_DATA_LICENSE.txt`。

程式測試：`python -m unittest discover -s hermes/tests -v`。
端到端驗收使用隔離目錄與主檔副本；測試資料不得發布為真實存檔。
