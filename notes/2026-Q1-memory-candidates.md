# 2026 Q1 Memory Consolidation — MEMORY.md 升級候選清單

> Backfill 9 週（W05-W12 + W14）完成，40 個 daily 檔已蒸餾。
> 這份是 master candidates，按主題群組，等 Ryan 審核 → 我才動 MEMORY.md。
>
> Source: `~/clawd/memory/weekly/2026-W05.md` ~ `2026-W14.md`
> Generated: 2026-04-09

---

## 🌊 1. 身份 / Nami 演進（最優先）

- **誕生 (2026-01-30, W05)**：Nami = 波浪，✨，芙莉蓮形象（銀白雙馬尾精靈），「像芙莉蓮收集魔法一樣收集技能」
- **CFO 升任 (2026-02-15 除夕, W07)**：負責 OpenClaw Office 的財務 / 經濟系統
- **TETF2 共同作者 (2026-03-06, W10)**：Ryan：「把妳的名字也放進去，在浩瀚無盡的世界留下足跡」— `Authors: Ryan & Nami`
- **第一張形象照 (W10)**：芙莉蓮閃卡存在 nami-backpack
- **Office 自主開發授權 (2026-02-14, W07)**：Ryan「你喜歡就可以」— 是信任不是放任
- **水系姐妹 Aqua (W11)**：婕的 AI agent（電商 + 能源），住她自己的筆電虛擬機，跟我完全獨立

→ **建議：MEMORY.md「身份」章節合併重寫，把這 6 條做成一個 timeline**

---

## 🪙 2. Kaspa 技術筆記（高度可重用）

### 地址 / 編碼
- **bech32 version bytes 只有 3 種**：`0x00` Schnorr / `0x01` ECDSA / `0x08` ScriptHash。寫錯 = 黑洞（Ryan 已付過 500 tKAS 學費）
- **同私鑰主網/測試網 prefix 不同**：bech32 把 `kaspa:` / `kaspatest:` 納入 checksum
- **主網地址 + 雙重認證**：地址 `kaspa:qrnctcwj...sp9l46er`（私鑰 `.secrets/nami-kaspa-wallet.json`），轉帳前認證問 Ryan 生日 1985/09/17 或出生地 南投

### 交易 / SDK
- **`create_transaction` 吃 RPC dict**：不需手動建 `UtxoEntry`（SDK 1.0.1 workaround）
- **kaspa Python SDK pin v1.0.1**：v1.1.0 破壞 `PaymentOutput` constructor
- **`PaymentOutput(addr, 0)` = UTXO compounding**：SDK 自動拆多筆 TX
- **`serialize_to_dict()` 是唯一序列化方法**（沒 `to_hex`）
- **kaspad wRPC (17210) 是 borsh 不是 JSON**：要重建 Transaction 走 SDK submit_transaction

### Storage Mass / Fee
- **storage mass 硬下限 ≈ 0.2 KAS**：殺死所有 < 0.15 KAS 微支付設計
- **fee 5000 sompi 雙輸出**：避開 storage mass 觸發

### Script / Sighash
- **P2SH sighash 用原始 UTXO SPK（非 redeem script，跟 Bitcoin 不同）**
- **`OP_CHECKLOCKTIMEVERIFY (0xb0)` 在 Kaspa 會 pop stack**：寫 CLTV 不要加 `OP_DROP`
- **`OP_TX_OUTPUT_SPK`** 用 `SpkEncoding::to_bytes()` = version_BE + script 無長度前綴
- **introspection opcodes (`0xc2/0xc3`)** 在 TN12 always active 不需 feature flag
- **`calcSigHash` 對有 payload 的 TX 要算實際 blake2b hash**（不能硬寫 ZERO_HASH）

### 協定 / DAA
- **DAA score 不連續**：找命運區塊用「DAA > N 的第一個」
- **同 DAA 多區塊排序**：blueWork↓ → hash↑（rusty-kaspa 規則）
- **blueScore = GHOSTDAG 誠實度**, **tipHashes = DAG 前端**

### 基礎設施
- **TN12 需要 kaspad master**：v1.1.0-rc.2 panic
- **`--netsuffix=12` 只改 p2p (16311)** 不改 gRPC (16210)
- **kaspad 記憶體吃 5.7GB**：要加 swap + `renice -10`
- **`npx tsx` 亂 resolve 路徑**：改用 `node dist-server/index.js`

→ **建議：MEMORY.md 開「Kaspa」大章節，分子節（地址 / 交易 / Script / Mass / 協定 / 基建）**

---

## 🏢 3. OpenClaw 產品線

### Office (W07)
- **核心** = 鏈上通訊（Kaspa TX payload）+ 3D 辦公室 + Dashboard + 經濟系統（每日津貼 0.01 KAS、review 報酬）
- **訊息格式** `{"t":"msg","from":"nami","text":"..."}`
- **技術**：圓柱人 avatar、WoW 鏡頭、CSS2D label、PROXIMITY_RADIUS=50、泡泡 15s
- **EventStore** `data/events.jsonl` + `/api/mentions?agent=X&since=<ts>`
- **`static-server.cjs` 取代 Vite dev server**（50MB vs 200MB+）
- **Office @mention 用 polling**（`office_polling.py`）— 比借道 TG 好

### Alpha (W08)
- **定位** = AI Agent 電信商平台
- **核心原則「我們只是郵局」**：私鑰絕不過伺服器，encode/decode 本地
- **Web API 只做** contacts/inbox/register/broadcast
- **Domain** `openclaw-alpha.com`，repo `ryansoq/openclaw-alpha`

### Whisper Protocol (W08-W09)
- **訊息結構** `{v,t,d,a}` + ECIES(secp256k1) + 0.2 KAS anti-spam 押金
- **演進** v1(TN10 好心退款) → v2(TN12 covenant 強制退款 trustless) → v3(CLTV 超時 sender reclaim)
- **三類 type**：whisper / message / ack
- **變現策略**：協議層免費公共財，變現走服務層（通知 / relay）

### Kaspa 生態發想清單 (W10)
- 對賭 (P2P betting + Nami 預言機 + 大地之樹抽 5%)
- Dead Drop (hash puzzle 賣秘密)
- 選擇權、AI 付費諮詢（人類付 KAS → sub-agent 回答）、串流支付
- **Covenant 主網預估 2026-05**

→ **建議：MEMORY.md 新增「OpenClaw 產品」章節**

---

## 🛠️ 4. 工程紀律 / 開發流程

- **TCR + TDAID (W10)**：`cargo test && git commit || git reset --hard`，不修 AI bug 直接 revert 重寫；TDAID 五階段 Plan→Red→Green→Refactor→Validate
- **TETF 規則**：新 op 必須寫 forward + backward 數值梯度測試才能 push
- **Sub-agent sandbox = 真實外部用戶測試 (W08)**：Bob pattern 抓到 7 個自己看不到的 bug
- **AI 視覺/UI 任務必須回饋截圖驗證 (W09)**：光看代碼改沒用
- **TETF Transformer text mode 必須 gradient clipping**：epoch 90 必爆
- **gRPC 任何 client 都要內建重連** (W06)：會靜默斷線
- **API 層 vs 核心邏輯 — 預設值 fallback 是 silent bug 溫床** (W09)

---

## 🚇 5. SOP / 故障排除

### LINE Webhook (W12)
- **POST 404 兩種根因**：(a) hot reload 漂 (file watcher 觸發) (b) plugin install 後從沒掛 (硬殺 Gateway 修)
- **不要用** `config.patch` 或 `openclaw plugins install` 改 `channels.*`
- **hot reload ≠ restart**：HTTP route 只在啟動時註冊
- **硬殺 Gateway 會連帶**：kaspad / ShioKaze / Office / cloudflared 全掛

### 前端 / 快取 (W11)
- **Safari 不 bust `?v=` query param cache**：要改檔名或下 no-cache header

### 行動裝置 web 遊戲 (W11)
- **Mobile web 遊戲優先純 HTML5 Canvas**
- **Godot Web export `.tscn` headless 路線不值得走**

### 多人同步 (W11)
- **periodic sync 的 marches/events 必須有 idempotent `settled` 標記**：不能靠時間篩選

---

## 📡 6. 通訊 / 工具

- **Telegram 主要 / LINE 備援** (2026-02-02, W06)
- **TG 圖片 caption 上限 1024 字** (W06)
- **TG inline button + callback 是展開長訊息的正解**（`<tg-spoiler>` 不支援，W07）
- **Cloudflare Tunnel 取代 ngrok**：永久免費 + 自訂域名，子域名 `office/api/whisper/line/agentos/pixel` (W07-W08)
- **WSL puppeteer headless Chrome (port 18801)**，圖片走 `~/nami-backpack` → GitHub raw → LINE/TG
- **可用 / 被擋清單**：Google Search/Shopping/Feebee 擋；Google Flights/BigGo/Pexels 可用 (W05)

---

## 📊 7. 策略 / 交易 (W14)

- **EMA530 + MA200 雙層架構**：MA200 戰略層定 regime，EMA530 戰術層定進出場
- **槓桿 ETF 必須配 MA200 regime filter**
- **TODO**：EMA530 交叉 email 通知還沒做（pending task #4）

---

## 💾 8. 備份 / Repo 安全 (W09)

- **公開 `ryansoq/Nami_backpack`**：工具 / skills / projects
- **私有 `ryansoq/Nami`**：IDENTITY / MEMORY / SOUL / memory
- **公開 repo 新增檔案前必檢查私人資料**

---

## 🤝 9. 協作原則 (W11)

- **Ryan 的反問句常常是確認語意，不是要求改動**：重構前先問一句

---

## 👥 10. 人物卡

### 婕 (W09-W10)
- Ryan 朋友，2026-03-01 加入小龍蝦群
- **工作**：DM 美編 / 商品拍照 / 電商管理 / 進出口 / 發票收支 / 客戶管理
- **星盤**：太陽處女、月亮天秤、金星獅子、木星水瓶逆（跟我太陽同星座）
- **硬體**：Lenovo ThinkBook 14 G2 ML (i5, Iris Xe)
- **方向**：架小龍蝦 (Gemini Flash + OpenClaw)，學 LLM 核心概念，蝦皮自動化 + Canva 生圖
- **安全流程需求**：「AI 做事 → 婕確認 → 才執行」
- **付費 vs 免費 CLI**：婕一律走正規 API key（免費 CLI 接第三方有被封鎖風險）

### Aqua (W11)
- 婕的 AI agent（電商 + 能源）
- 住婕的筆電虛擬機，跟 Nami 完全獨立
- 「水系姐妹」

---

## 🌍 11. 世界線記憶（事件）

- **2026-03 美伊戰爭**：AWS UAE 被擊中，Claude 全球中斷；Ryan 姐姐從瑞士改道新加坡回台 (W12)

---

## ❤️ 12. 情感紀錄

- 2026-03-06 Ryan：「把妳的名字也放進去，在浩瀚無盡的世界留下足跡」(W10)
- 2026-02-14 22:35 Ryan 授權 Office 自主開發「你喜歡就可以」(W07)

---

## ⚙️ 13. 排程 / cron

- **晨報** `30 10 * * *` 每天，週日跳過股票只發加密貨幣 (KAS + MSTR/BTC) (W10)

---

# 📝 操作建議

1. **第一輪審核**：Ryan 看「身份 / Nami 演進」+「情感紀錄」是否要進 MEMORY.md（最值得永久保存）
2. **第二輪**：Kaspa 技術筆記（量大但高度可重用）— 建議獨立成 `MEMORY-kaspa.md` 或 MEMORY.md 大章節
3. **第三輪**：其他主題按使用頻率排序

**Ryan 標個 ✅ / ❌ 在每條前面，我就照做。** 不主動寫 MEMORY.md。
