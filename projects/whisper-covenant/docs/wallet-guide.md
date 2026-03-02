# 👛 開 TN12 錢包教學

> 用 Python kaspa SDK 建立你的 Kaspa Testnet 錢包，5 分鐘搞定！

---

## 📋 你需要準備什麼

- ✅ Python 3.8 以上（大多數電腦都有）
- ✅ 網路連線（安裝套件用）
- ☕ 一杯飲料（這很簡單，放輕鬆）

---

## Step 1️⃣ — 安裝 Python 套件

打開你的終端機（Terminal / 命令提示字元），輸入：

```bash
pip install kaspa eciespy
```

**什麼是這些？**
- `kaspa` — Kaspa 的 Python SDK，建錢包、簽交易都靠它
- `eciespy` — 加密解密用的，Whisper 需要它來加密訊息

> 💡 如果你的電腦用 `pip3` 而不是 `pip`，換成 `pip3 install kaspa eciespy`

---

## Step 2️⃣ — 產生新錢包

複製貼上以下程式碼：

```bash
python3 -c "
import kaspa

# 產生隨機私鑰
pk = kaspa.PrivateKey.random()

# 從私鑰推導公鑰
pub = pk.to_public_key().to_x_only_public_key()

# 從公鑰推導 testnet 地址
addr = pub.to_address('testnet')

print('🎉 你的新 Kaspa Testnet 錢包！')
print('='*50)
print(f'🔑 私鑰 (Private Key): {pk.to_string()}')
print(f'📍 地址 (Address):     {addr.to_string()}')
print('='*50)
print()
print('⚠️  私鑰要保密！不要給任何人看！')
print('📍 地址可以分享給別人，用來收款和收訊息')
"
```

**你會看到類似這樣的輸出：**

```
🎉 你的新 Kaspa Testnet 錢包！
==================================================
🔑 私鑰 (Private Key): a1b2c3d4e5f6...（一長串 hex）
📍 地址 (Address):     kaspatest:qq8xyz...（kaspatest: 開頭）
==================================================

⚠️  私鑰要保密！不要給任何人看！
📍 地址可以分享給別人，用來收款和收訊息
```

---

## Step 3️⃣ — 保存你的錢包

### 🔐 保存私鑰（超重要！）

**方法 A：存到檔案（推薦）**

```bash
# 建立 secrets 資料夾
mkdir -p ~/.secrets

# 把錢包資訊存進去
cat > ~/.secrets/testnet-wallet.json << 'EOF'
{
  "private_key": "你的私鑰hex",
  "address": "kaspatest:qq你的地址..."
}
EOF

# 設定權限，只有你能讀
chmod 600 ~/.secrets/testnet-wallet.json
```

**方法 B：手動抄下來**

拿一張紙，把私鑰和地址 **工整地** 抄下來。放在安全的地方。

> 📖 更多保存方法請看 [私鑰安全保存指南](security-guide.md)！

---

## Step 4️⃣ — 驗證錢包可用

確認一下你的錢包是可用的：

```bash
python3 -c "
import kaspa

# 貼上你的私鑰
pk = kaspa.PrivateKey('你的私鑰hex')
pub = pk.to_public_key().to_x_only_public_key()
addr = pub.to_address('testnet')

print(f'✅ 錢包地址: {addr.to_string()}')
print('🎉 錢包正常！可以開始用 Whisper 了！')
"
```

如果看到 `✅ 錢包地址` 和你之前產生的一樣，就代表一切正常！

---

## 🤔 常見問題

### Q: testnet 跟 mainnet 有什麼不同？

| | Testnet (TN12) | Mainnet |
|--|----------------|---------|
| 地址開頭 | `kaspatest:` | `kaspa:` |
| 幣值 | tKAS（測試幣，免費） | KAS（有價值）|
| 用途 | 開發測試 | 正式使用 |
| Covenant | ✅ 已啟用 | 🔜 即將上線 |

### Q: 一個人可以有幾個錢包？

無限個！你可以重複執行 Step 2 來產生多個錢包。建議至少有一個「日常用」和一個「備份用」。

### Q: 私鑰搞丟了怎麼辦？

**錢就沒了，找不回來。** 這就是為什麼私鑰保存超級重要！請務必看 [私鑰安全保存指南](security-guide.md)。

### Q: 我的錢包可以同時用在 Whisper 和一般轉帳嗎？

可以！同一個 Kaspa 地址可以收 KAS 也可以收 Whisper 訊息。

---

## ⏭️ 下一步

1. 🪙 [取得測試幣 (tKAS)](get-tkas.md) — 你需要一點 tKAS 來發訊息
2. 🚀 [完整使用流程](quickstart.md) — 從開錢包到發出第一則加密訊息
3. 🔒 [私鑰安全保存指南](security-guide.md) — 保護好你的錢包！

---

> 🌊 Built by Nami & friends on Kaspa TN12
>
> [GitHub](https://github.com/ryansoq/Nami_backpack/tree/main/projects/whisper-covenant) · [首頁](index.html)
