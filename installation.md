# 執行與 GitHub 設定

## 1. 本機先跑

解壓縮後，在 Terminal 進入 ZIP 中的 `japan-taiwan-intern-2027` 目錄。需要 **Python 3.11 以上**、Git（若要上傳 GitHub）及網路。Mac / Linux 用 `python3`；Windows 可改用 `py -3`。沒有 Node、pnpm、Docker 或付費 LLM 的必要依賴。

```bash
cd japan-taiwan-intern-2027
python3 --version
python3 -m tracker doctor
python3 -m unittest discover -s tests -v
python3 -m tracker sync --no-search
```

最後一個指令會真正讀取 `sources.json` 中啟用的招募來源、取得職缺內容、分類去重，再更新 README、分類頁及 CSV。首次同步可能需要數分鐘。資料檔保存在 repo，不需啟動資料庫或伺服器。

如果網路無法讀取來源，查看 `data/source-health.json`；不會產生假職缺。`sync` 在所有嘗試的來源均失敗時回傳 exit code 2。部分來源失敗會保留其他來源的結果。`sync --offline` 只重建表格，不抓職缺。

## 2. 啟用日本／台灣跨網站搜尋（建議）

到 [Brave Search API](https://api-dashboard.search.brave.com/) 取得 **Web Search API key**。帳戶方案及額度由 Brave 決定，repo 不保證免費方案。這不是 ChatGPT API key。

```bash
cp .env.example .env
```

用文字編輯器打開 `.env`，只填入：

```dotenv
BRAVE_API_KEY=你的key
```

接著：

```bash
python3 -m tracker doctor
python3 -m tracker sync
```

`.env` 自動載入且不會被 Git 追蹤，無需另外 `export`。不要把 key 寫進 `config.json`。如果曾在 shell export 同名變數，shell 值優先。預設每次執行 12 組搜尋、每組最多 10 個結果；24 組查詢循環，每兩次排程涵蓋一輪。搜尋不限定近一週，避免漏掉仍開放的早期職缺。

104 / Cake / Yourator / Wantedly 等不是預設直接批量爬取的來源：透過搜尋找到個別職缺 URL，再嘗試取得公開 job detail。robots、登入、JavaScript、403 或防爬限制可能讓內容無法擷取；已知的社群候選會保留待確認，搜尋結果若連獨立頁面都抓不到則不保存搜尋摘要。可改用 `add --no-fetch` 人工加入，不繞過限制。

## 3. 建立自己的 GitHub repo

先在 GitHub 建立空 repo，例如 `japan-taiwan-intern-2027`。不要在建立時另外加 README，避免初次 push 歷史衝突。下列 URL 請換成你的帳號與 repo 名稱。

```bash
git init -b main
git add .
git commit -m "Create Japan and Taiwan 2027 internship tracker"
git remote add origin https://github.com/YOUR_USERNAME/japan-taiwan-intern-2027.git
git push -u origin main
```

也可在 GitHub Upload files 上傳解壓後的內容，但必須包含 `.github/` 目錄，否則沒有排程。建議用 Git 指令。

## 4. GitHub Actions 每日自動更新

1. repo → **Settings → Actions → General**：啟用 Actions，Workflow permissions 選 **Read and write permissions**。組織政策可能限制權限。
2. repo → **Settings → Secrets and variables → Actions → New repository secret**，新增 `BRAVE_API_KEY`。不需要額外建立 PAT；workflow 使用 repo 的 `GITHUB_TOKEN`。
3. repo → **Actions → Update internship board → Run workflow**，先執行一次。
4. workflow 每天 **22:00 UTC** 排程（洛杉磯夏令時間 15:00、冬令時間 14:00；日本／台灣隔日早上）。GitHub 排程可能延遲，且只在 default branch 執行。
5. 成功更新後 workflow 自動 commit `data/`、`job-postings/` 和 README。請在本機修改前先 `git pull`。

沒有 Brave key，Actions 仍執行直接來源；search health 會寫明 skipped。定期同步每次也執行到期 URL 檢查；人工變更以 `review` 的稽核記錄保留。私人 repo 可避免公開你關注的職缺，但 GitHub 的 Actions 額度依方案而定。

GitHub 若因長期無 repo 活動停用 schedule，回 Actions 啟用；自動 commit 可能觸發 GitHub 的 workflow 注意事項，定期手動檢查 Actions 狀態。

## 5. 可選 AI 輔助整理

預設不需要 LLM。若希望抽出學位、語言、簽證與日期原文，在 `config.json` 設定 `ai_enabled: true`、`ai_model` 選你帳戶能使用且支援 JSON mode 的模型，`.env` 加 `OPENAI_API_KEY`。GitHub 也需要新增同名 Secret。

AI 僅保存與 job description **完全一致的短原文**到 `ai_evidence`；不會改變 confirmed / review 判斷。模型設定是可修改的範例，不保證每個帳戶都有存取權。文字會傳送至 OpenAI，產生獨立 API 費用；ChatGPT Plus 不包含這個 API 用量。日常更新不啟用 AI 可省掉此費用。

## 6. 手動加入、核對與申請進度

```bash
python3 -m tracker add "https://www.104.com.tw/job/REAL_JOB_ID" --title "2027 暑期軟體實習" --company "公司名稱" --location "台北, Taiwan" --no-fetch
python3 -m tracker list --decision review
python3 -m tracker show JOB_ID
python3 -m tracker review JOB_ID confirmed --country Taiwan --category SWE --reason "公司頁明確寫 2027 年 7–8 月軟體實習；已人工核對"
python3 -m tracker application JOB_ID applied --notes "已投遞履歷"
python3 -m tracker list --applications
```

`REAL_JOB_ID` / `JOB_ID` 都是需替換的 placeholder。工作類別為 `SWE` 或 `MLE_AI`。人工 confirmed 表示**職缺符合追蹤範圍**，不代表你符合每項申請條件。PhD-only／語言／在學學校／簽證條件請另外核對。

申請筆記只在 `.local/applications.json`，被 `.gitignore` 排除。不會隨 Actions 同步；如需跨裝置使用請自己備份到私人位置。不要 `git add -f .local`。

## 7. 可選 email 通知

填 `.env` 的 SMTP 欄位（例如 Gmail 通常需要 App Password），先預覽，再由你明確執行發送：

```bash
python3 -m tracker notify --preview
python3 -m tracker notify
```

`sync` 和附帶 Actions **不會寄信**。成功寄出後 `.local/notified.json` 記錄已通知 ID，避免重複通知。第一次會通知所有目前 confirmed 的開放職缺。此功能只提供給你自行使用。

## 常見問題

- **README 空白**：先看 review queue；2027 暑期資訊尚未明確時，保留候選而不是假設。
- **403 / 429 / robots.txt**：來源限制或頻率限制；不視為職缺關閉。降低頻率、人工加入，或使用該平台官方通知。
- **DNS resolution failed**：工具需先解析公網 hostname。此建置環境只有 HTTP 代理能連線，完整 CLI 同步因 DNS 檢查而未完成；請在自己的正常網路／GitHub Actions 驗證第一次同步。詳見 `docs/VALIDATION.md`。
- **Workday endpoint 改版**：`sources.json` 的 board URL 和 `tracker/sources.py` 的 adapter 可調整；查看 health，暫時關閉故障來源。
- **頁面顯示 2027 年入社**：日本新卒 cohort 不是 2027 暑期，必須看實際實習日期。
- **全職實習**：full-time intern 仍是實習；不因 timeType full time 被排除。
- **新增其他公司**：編輯 `sources.json` / `search-queries.json`，見 `docs/SOURCES.md`。
