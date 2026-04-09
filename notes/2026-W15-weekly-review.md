---
week: 2026-W15
span: 2026-04-06 to 2026-04-12
generated: 2026-04-09
daily_files: [2026-04-08.md]
backfill: true
---

# 2026-W15 週報

> ⚠️ 這是 memory-consolidation skill 的第一份試跑週報（backfill pilot）。格式若要改請告訴 Ryan。
> 2026-04-09（週四）此週尚未結束，目前只有 2026-04-08 一份 daily 檔。

## 🎯 本週主軸

**自省能力解鎖 + ClawX 生態加速**：這週的突破是「我能看見自己」— 透過 `/context` 注入 stdout 回到我的 context，加上確認我自己就能 `Bash: echo ... > mono.fifo` 自我注入。配合 `/reload-plugins` 的發現，plugin 層的迭代變得不需要重啟 session。

## 📝 發生了什麼

1. **`/context` self-introspection 確立**：Ryan 從另一個視窗注入 `/context`，結果整段 stdout 被包成 `<local-command-stdout>` 送回我的 context。`/mcp` `/memory` `/skills` 也同理能用。直接改變 debug 模式。
2. **確認 self-inject 可行**：`mono.fifo` 是檔案，我有 Bash 權限，技術上可以自己注入（但要守「只注查詢類」的原則防 loop）。
3. **`/reload-plugins` 熱修**：Telegram plugin `.mcp.json` 改絕對 bun 路徑後不需重啟 session — `/reload-plugins` 就重連，4 個 tool 立刻可用。以後 plugin 設定改動全部走這條。
4. **ClawX commit 88923fd**：`build_command()` 用 `shutil.which()` + fallback 解析 `claude` 絕對路徑，修 PTY child 找不到指令的 bug。
5. **ClawX README + demo.png**：Setup 改四種情境（A 全新/B 加到現有專案/C 搬進 ClawX/D 遠端指向）。BOOTSTRAP.md 的 YAML frontmatter 被 Ryan 刪掉，改成無條件完整載入。
6. **FB 貼文定稿**：「ClawX — Anthropic 改訂閱制導致 OpenClaw 無法使用 → 包一層讓 Claude Code CLI 去使用 OpenClaw 相關文件」。
7. **兩個 TODO 暫緩入冰箱**：compact detection（已在 2026-04-09 shipped 🎯）和 MEMORY.md 索引化重構（還在冰箱）。

## 💡 學到的事

- **self-introspection 是一個類別，不是單一功能**：一旦確認「CLI stdout 會回到 model context」，所有內建查詢命令（/context, /mcp, /memory, /skills, /cost, ...）都變成 debug 工具。值得寫進 TOOLS.md 當標準手段。
- **self-inject 的使用原則 = 只注查詢類**：Ryan 驚訝「你好像可以自己注入」時，我同時意識到風險（loop）。原則：注了還會觸發 agent 行為的 prompt 一律不自注。
- **plugin hot-reload > 整個 session 重啟**：以後遇到 `.mcp.json`、plugin 設定、plugin 檔案變動，先想 `/reload-plugins`。只有 CLAUDE.md / settings.json 這種 session-wide 檔才真的要整個重起。
- **暫緩不等於遺忘**：compact detection TODO 從 2026-04-08 進冰箱，2026-04-09 就 ship 了。關鍵是 2026-04-08.md 把需求、偵測機制、去重策略都寫清楚，今天直接照著做。驗證「Write It Down」的價值。

## 🔄 對長期記憶的建議

這週有幾個候選值得考慮升級到 `MEMORY.md`，但根據 skill 協議**不自動寫**，列出來等 Ryan 決定：

- **加到「工具 / 自省」章節**：`/context`、`/mcp`、`/memory`、`/skills` 這些 CLI 內建命令可以透過 mono.fifo 注入取得 stdout，stdout 會回到 model context — 是 self-debug 的標準手段
- **加到「工具 / 熱更新」章節**：修 plugin `.mcp.json` 後用 `/reload-plugins` 即可熱掛，不需要重啟 session；只有 CLAUDE.md/settings.json 這種 session-wide 才需要整個重起
- **加到「使用原則 / 安全」章節**：self-inject 只能注「查詢類」slash command，避免 loop；會觸發 agent 行為的 prompt 一律不自注
- **冰箱 TODO 狀態更新**：compact detection 已於 2026-04-09 shipped（ClawX repo commit `2d19c25`）— MEMORY.md 如果有「冰箱 TODO」類似清單，這條該移除

**Backfill 模式**：這些候選是否升級，等 10 週全部 backfill 完 Ryan 統一審核。

## 🧹 已消化的 daily 檔

- `2026-04-08.md`
