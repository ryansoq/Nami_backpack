# 🔒 私鑰安全保存指南

> 你的私鑰 = 你的錢包 = 你的訊息。搞丟私鑰，一切都沒了。

---

## 🧠 先搞懂一件事

在 Kaspa（和所有區塊鏈）裡，**私鑰就是一切**：

- 有私鑰 → 能花錢、能收訊息、能證明身份
- 沒私鑰 → 什麼都做不了，誰都幫不了你

沒有「忘記密碼」按鈕，沒有客服可以打電話。

**所以，保護好私鑰是你最重要的任務。**

---

## ✅ 推薦做法

### 方法 1：加密檔案（日常使用推薦）

把錢包存成 JSON 檔，設定嚴格權限：

```bash
# 建立安全目錄
mkdir -p ~/.secrets
chmod 700 ~/.secrets

# 寫入錢包
cat > ~/.secrets/testnet-wallet.json << 'EOF'
{
  "private_key": "你的私鑰hex",
  "address": "kaspatest:qq你的地址..."
}
EOF

# 只有你能讀寫
chmod 600 ~/.secrets/testnet-wallet.json
```

**為什麼這樣做？**
- `chmod 700` → 只有你能進這個資料夾
- `chmod 600` → 只有你能讀寫這個檔案
- 其他用戶、其他程式都看不到

### 方法 2：紙本備份（長期保存推薦）

1. 拿一張乾淨的紙
2. **用鉛筆**（不怕褪色）工整地寫下：
   - 私鑰（hex 字串）
   - 地址（kaspatest:qq...）
   - 建立日期
3. 放在安全的地方（保險箱、防水袋）
4. **不要拍照！** 照片可能被雲端同步

```
📝 範例：

Date: 2026-03-03
Network: Kaspa Testnet 12
Address: kaspatest:qqxyz123...
Private Key: a1b2c3d4e5f6...

⚠️ KEEP SECRET — DO NOT SHARE
```

### 方法 3：加密的 USB 隨身碟

```bash
# 把錢包複製到 USB
cp ~/.secrets/testnet-wallet.json /media/your-usb/

# 更好的做法：用 GPG 加密
gpg -c ~/.secrets/testnet-wallet.json
# 會產生 testnet-wallet.json.gpg（加密版）
# 把 .gpg 檔複製到 USB

# 要用的時候解密
gpg -d testnet-wallet.json.gpg > testnet-wallet.json
```

---

## ❌ 千萬不要做的事

| 🚫 不要 | 為什麼 |
|---------|--------|
| 貼到 Discord / Telegram / LINE | 聊天記錄可能洩漏 |
| 存在雲端（Google Drive, iCloud） | 雲端帳號被駭 = 私鑰被偷 |
| 用手機拍照 | 照片自動同步到雲端 |
| 放在桌面或 Downloads 資料夾 | 太容易被看到 |
| 存在沒有密碼保護的地方 | 任何人拿到電腦就能看 |
| 傳給「客服」或「官方」 | 100% 是詐騙 |

---

## 🔄 備份策略：3-2-1 原則

```
3 份備份
├── 📂 電腦上的加密檔案（日常用）
├── 📝 紙本（放在家裡安全的地方）
└── 💾 加密 USB（放在另一個地方）

2 種媒介
├── 數位（檔案 + USB）
└── 實體（紙本）

1 份放在異地
└── 不要全部放在同一個地方！
    （萬一火災、水災、被偷...）
```

---

## 🆘 如果私鑰洩漏了

1. **立刻建立新錢包**（參考 [開錢包教學](wallet-guide.md)）
2. **把舊錢包的資金轉到新錢包**
3. **通知跟你通訊的人**，換新的地址
4. **廢棄舊的私鑰**，永遠不要再用

```bash
# 趕快建新錢包
python3 -c "
import kaspa
pk = kaspa.PrivateKey.random()
pub = pk.to_public_key().to_x_only_public_key()
addr = pub.to_address('testnet')
print(f'新私鑰: {pk.to_string()}')
print(f'新地址: {addr.to_string()}')
"
```

---

## 🤔 常見問題

### Q: Testnet 的私鑰也要這麼小心嗎？

Testnet 的幣（tKAS）沒有金錢價值，但你的 **Whisper 訊息** 跟這把私鑰綁定。如果別人拿到你的私鑰，他們可以：
- 讀你收到的所有加密訊息
- 假裝是你發訊息
- 花掉你的 tKAS

所以 **是的，要小心保管**。

### Q: 我可以用同一個私鑰在不同電腦上嗎？

可以！私鑰只是一串數字，在哪台電腦上都能用。只要確保安全地傳輸（不要用聊天軟體傳）。

### Q: 私鑰有「有效期限」嗎？

沒有！除非 Kaspa 區塊鏈關閉（極不可能），你的私鑰永遠有效。

---

## 📋 安全檢查清單

在開始使用 Whisper 之前，確認以下事項：

- [ ] 私鑰已保存在安全的地方
- [ ] 至少有 2 份備份
- [ ] 備份分散在不同地點
- [ ] 沒有把私鑰傳給任何人
- [ ] 檔案權限設定正確（`chmod 600`）
- [ ] 不在公共場所輸入私鑰

全部打勾了？你的錢包很安全！🎉

---

## ⏭️ 下一步

1. 🪙 [取得測試幣 (tKAS)](get-tkas.md) — 發訊息需要少量 tKAS
2. 🚀 [完整使用流程](quickstart.md) — 開始傳送加密訊息！
3. 📄 [白皮書](whitepaper.md) — 了解 Whisper 的技術原理

---

> 🌊 Built by Nami & friends on Kaspa TN12
>
> [GitHub](https://github.com/ryansoq/Nami_backpack/tree/main/projects/whisper-covenant) · [首頁](index.html)
