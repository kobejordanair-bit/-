# lawtype.piamamba.com 部署

打字系統保留原有 GitHub Pages。Cloudflare Pages 建置僅包含打字前端，不包含同一儲存庫的 FM24 專案、Python 後端、SQL、測試或其他資料。

## 從 GitHub 自動部署

在 Cloudflare 後台的 Workers & Pages 建立 **Pages** 專案，連接 GitHub 儲存庫 `kobejordanair-bit/-`：

| 設定 | 值 |
| --- | --- |
| Production branch | `main` |
| Framework preset | `None` |
| Build command | `python3 scripts/build-cloudflare.py` |
| Build output directory | `dist/lawtype` |
| Root directory | 留空（儲存庫根目錄） |

第一次部署成功後，在該 Pages 專案的 **Custom domains** → **Set up a custom domain** 加入 `lawtype.piamamba.com`。若網域位於同一 Cloudflare 帳號，依畫面指示讓 Cloudflare 建立 DNS 記錄並簽發 HTTPS 憑證。先綁定 Pages 自訂網域，再處理其 DNS；只新增 CNAME 不足以設定 Pages 路由。

只操作 `lawtype` 子網域，不修改 `piamamba.com` 或 `fantasy.piamamba.com` 的既有 DNS、網站或重新導向。若 `lawtype` 已有記錄，先核對它的現有用途，不直接覆蓋。

## 登入與裁判書匯入

1. 在 Supabase 專案 `nayaxwltlsdukfhetykr` 的 Authentication → URL Configuration → Redirect URLs **新增** `https://lawtype.piamamba.com/`，保留原有 GitHub Pages 設定。Site URL 暫時保留原值；本站會依目前網址提供登入 redirect。
2. 在 Render 的 `legal-typing-judgment-api` 確認 `CORS_ORIGINS` 包含 `https://kobejordanair-bit.github.io,https://lawtype.piamamba.com`，並重新部署。Repository 的 `render.yaml` 和後端預設值已更新；已存在的 Render 環境變數仍需在服務中確認，不能僅憑 commit 假定生效。
3. 新舊網域的瀏覽器資料彼此獨立。先在原網站用「匯出」下載 JSON 備份，再到新網域「匯入」，以搬移本機題庫、紀錄與模擬作答草稿。

前端只使用原有公開 Supabase key。不要把 Cloudflare API token 或 Supabase 管理金鑰放入靜態資產或儲存庫。

## 驗證

開啟 `https://lawtype.piamamba.com/`，確認 HTTPS、首頁、「模擬考試」、切題與暫存；再用自己的 Email 測試登入連結回到新網址，並確認裁判書匯入沒有 CORS 錯誤。

本機檢查建置：`python3 scripts/build-cloudflare.py`。上傳內容為 `dist/lawtype`，不應使用整個儲存庫作為 Pages 的靜態輸出。
