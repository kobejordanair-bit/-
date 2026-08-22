# 法學文獻打字訓練系統

以繁體中文法律資料做輸入練習的靜態網頁，部署於 GitHub Pages。

## 裁判書匯入功能

按下「⚖️ 匯入裁判書」後可：

1. 用關鍵字、案件類型與年度搜尋公開裁判書；
2. 預覽單筆裁判書的主文、事實、理由或全文；
3. 選擇一個段落，匯入成瀏覽器本機的自訂打字文獻；
4. 保留法院、案號、日期與司法院官方來源連結。

網站本身不保存司法院帳密，也不儲存裁判書於伺服器。使用者的自訂題庫與練習紀錄仍只存在瀏覽器 localStorage。

### 後端部署

裁判書查詢由 `backend/` 的 FastAPI 服務處理；GitHub Pages 無法安全直接執行 Python MCP server。

本 repo 已附 `render.yaml`。在 Render：

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
