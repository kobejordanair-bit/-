# 法學文獻打字訓練系統

以繁體中文法律資料做輸入練習的靜態網頁，部署於 GitHub Pages。

## 跨裝置雲端同步（Supabase）

網站已具備登入、離線本機快取、同步合併與衝突副本邏輯。首次啟用需要建立一個你自己擁有的 Supabase 專案：

1. 在 Supabase 建立專案，於 SQL Editor 執行 `supabase-schema.sql`。
2. 在 Authentication 啟用 Google provider，並設定網站 redirect URL：
   `https://kobejordanair-bit.github.io/-/`
3. 在專案 Connect / API 取得 **Project URL** 與 **publishable / anon key**。
4. 將兩個公開前端設定值填入 `supabase-config.mjs`：

```js
export const SUPABASE_URL = 'https://你的專案.supabase.co';
export const SUPABASE_PUBLISHABLE_KEY = '你的 publishable 或 anon key';
```

> 絕對不要填入或提交 `service_role` key。它是伺服器管理密鑰，不能出現在瀏覽器或 GitHub。

同步採每筆資料的 `updatedAt` 與 tombstone 軟刪除；同一筆資料在不同裝置同時間修改時，會保留一份「同步衝突副本」，避免靜默遺失資料。


### 逐字練習的正確率

完成時使用**文字序列對齊**而非單純同一位置逐字比較。因此中途漏打一字、多打一字或誤按一字時，後方仍可重新對齊，不會讓後續所有字都被連鎖判錯。

- Gross CPM：輸入的非換行字元數 ÷ 分鐘
- 正確率：以對齊後的正確字數，對照較長的原文／輸入字數
- Net CPM：Gross CPM × 正確率
- 可隨時按「完成並計算」，即使尚未打到全文末端也能檢視結果

### 申論題純速度作答

按「✍️ 申論作答」→「匯入申論題」，貼上題名與題目後即可直接回答。

- 第一個字輸入後開始計時
- 顯示純速度 CPM、作答字數與作答時間
- **不計正確率、不計 Net CPM**
- 題目與作答速度紀錄保存在瀏覽器 localStorage，並納入 JSON 備份


按下「⚖️ 匯入裁判書」後可：

1. 用關鍵字、案件類型與年度搜尋公開裁判書；
2. 預覽單筆裁判書的主文、事實、理由或全文；
3. 選擇一個段落，匯入成瀏覽器本機的自訂打字文獻；
4. 保留法院、案號、日期與司法院官方來源連結。

網站本身不保存司法院帳密，也不儲存裁判書於伺服器。使用者的自訂題庫與練習紀錄仍只存在瀏覽器 localStorage。

### 後端部署

裁判書查詢由 `backend/` 的 FastAPI 服務處理；GitHub Pages 無法安全直接執行 Python MCP server。

本 repo 已附 `render.yaml`，並已指定 Render 的 **Free** web service 方案：

1. 新增 **Blueprint**，選擇本 GitHub repo；
2. 確認服務名稱與區域後建立；
3. 部署完成後，複製 Render 提供的 `https://...onrender.com` 網址；
4. 開啟 GitHub Pages 網站 → **⚖️ 匯入裁判書** → 填入該網址。

後端只允許 GitHub Pages 網址跨來源呼叫。若你使用自訂網域，請在 Render 的環境變數 `CORS_ORIGINS` 加入該 HTTPS 網址（多個網址以逗號分隔）。

### 安全與資料來源

- 使用 `lawchat-oss/mcp-taiwan-legal-db` 的 MIT 授權解析與查詢元件，並鎖定已審查的 commit。
- 不啟用其 Playwright WAF bypass；官方網站拒絕正常請求時會回傳錯誤，不會嘗試繞過防護。
- 連線仍驗證 CA、憑證效期與主機名稱；僅針對官方憑證鏈的已知缺少 SKI 問題，關閉 OpenSSL 額外 strict-extension 檢查。
- 匯入前仍應以畫面中的官方原始連結核對內容。裁判書可能修正或下架，且使用時應注意個資與資料使用規範。

## 本機開發

### 啟動 API

```bash
uv venv .venv
uv pip install --python .venv/bin/python -r backend/requirements.txt
PYTHONPATH=backend .venv/bin/python -m uvicorn app:app --reload --port 8011
```

瀏覽器開啟 `index.html`（或用 `python -m http.server 8012`）後，在裁判書匯入視窗填：

```text
http://127.0.0.1:8011
```

### 執行測試

```bash
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -q
node --test tests/legal-import.test.mjs
```
