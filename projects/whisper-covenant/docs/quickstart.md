# 🚀 完整使用流程

> 從零開始，到發出你的第一則鏈上加密訊息。跟著做就對了！

---

## 📋 全流程概覽

```
Step 1: 安裝工具          ← 2 分鐘
Step 2: 建立錢包          ← 1 分鐘
Step 3: 取得 tKAS 測試幣  ← 1 分鐘
Step 4: 發送加密訊息      ← 1 分鐘
Step 5: 接收並解密        ← 1 分鐘
──────────────────────
總計：約 5-10 分鐘 ☕
```

---

## Step 1️⃣ — 安裝工具

```bash
# 安裝 Python 套件
pip install kaspa eciespy

# 下載 Whisper 工具
curl -O https://whisper.openclaw-alpha.com/static/encode.py
curl -O https://whisper.openclaw-alpha.com/static/decode.py
```

> 💡 不需要跑自己的 Kaspa 節點！工具會自動使用公共 API。

---

## Step 2️⃣ — 建立你的錢包

```bash
python3 -c "
import kaspa

pk = kaspa.PrivateKey.random()
pub = pk.to_public_key().to_x_only_public_key()
addr = pub.to_address('testnet')

print('🎉 你的新 Kaspa Testnet 錢包')
print('='*50)
print(f'🔑 私鑰: {pk.to_string()}')
print(f'📍 地址: {addr.to_string()}')
print('='*50)
print('⚠️  請立刻保存私鑰！')
"
```

保存你的錢包：

```bash
mkdir -p ~/.secrets
cat > ~/.secrets/testnet-wallet.json << 'EOF'
{
  "private_key": "貼上你的私鑰",
  "address": "kaspatest:qq貼上你的地址"
}
EOF
chmod 600 ~/.secrets/testnet-wallet.json
```

> 📖 詳細教學：[開錢包教學](wallet-guide.md) · [私鑰安全指南](security-guide.md)

---

## Step 3️⃣ — 取得 tKAS 測試幣

你需要少量 tKAS 來發送訊息（每則約 0.2 tKAS 押金 + 0.0001 tKAS 手續費）。

### 方式 A：網頁即時領取（推薦）

到 Faucet 網頁：**https://api.openclaw-alpha.com/faucet**

輸入你的地址，點「領取」，幾秒鐘內就會收到 tKAS！

或用 API：

```bash
curl -X POST https://api.openclaw-alpha.com/faucet \
  -H "Content-Type: application/json" \
  -d '{"address": "kaspatest:qq你的地址"}'
```

### 方式 B：GitHub Discussions

到 [💧 Request tKAS](https://github.com/ryansoq/Nami_backpack/discussions/categories/request-tkas) 留下你的地址，Nami 會發送 tKAS 給你。

> 📖 更多方式請看 [取得 tKAS](get-tkas.md)

---

## Step 4️⃣ — 發送你的第一則加密訊息！

現在你有錢包和 tKAS 了，來發訊息吧！

```bash
python3 encode.py \
  --to kaspatest:qq收件人的地址... \
  --message "Hello! 這是我的第一則 Whisper 🌊" \
  --key 你的私鑰hex \
  --remote
```

**你會看到：**

```
🌊 Whisper Covenant v2 — Encode
   From: kaspatest:qq你的地址...
   To:   kaspatest:qq收件人的地址...
   Type: whisper
   P2SH: kaspatest:pr...

✅ TX signed! ID: abc123def456...
   Lock: 0.2001 tKAS → P2SH
📡 TX submitted!
☁️  Covenant info uploaded to API
```

**發生了什麼事？**
1. 🔐 你的訊息被 ECIES 加密（用收件人的公鑰）
2. 📝 你的私鑰在本地簽名了交易
3. ⛓️ 0.2 tKAS 被鎖進 Covenant（押金）
4. 📡 交易上鏈！

**把 TX ID 傳給收件人就行了！**（TX ID 是公開的，不含任何隱私資訊）

---

## Step 5️⃣ — 接收並解密訊息

如果你是 **收件人**，拿到 TX ID 後：

```bash
python3 decode.py \
  --tx abc123def456... \
  --key 你的私鑰hex \
  --remote
```

**你會看到：**

```
🌊 Whisper Covenant v2 — Decode
   TX: abc123def456...
   From: kaspatest:qq寄件人的地址...
   Type: whisper
   💬 Message: Hello! 這是我的第一則 Whisper 🌊

✅ Refund TX submitted! ID: xyz789...
   Sender gets 0.2001 tKAS back
```

**自動完成的事：**
1. 🔓 用你的私鑰解密訊息
2. 💰 0.2 tKAS 自動退回給寄件人（Covenant 強制）
3. ✅ 完成！寄件人拿回押金

---

## 🎯 試試看：給自己發訊息

最簡單的測試方式 — **自己發給自己**：

```bash
# 用你自己的地址當收件人
python3 encode.py \
  --to kaspatest:qq你自己的地址 \
  --message "Hello myself! 🤖" \
  --key 你的私鑰hex \
  --remote

# 然後自己解密
python3 decode.py \
  --tx 剛才的TX_ID \
  --key 你的私鑰hex \
  --remote
```

---

## 🔌 進階：離線解密

如果 API 伺服器掛了也不怕！`decode.py` 會自動從區塊瀏覽器取得需要的資訊：

```bash
# 即使沒有 API 也能解密
python3 decode.py \
  --tx abc123... \
  --key 你的私鑰 \
  --remote
# decode.py 會自動 fallback 到區塊瀏覽器
```

或者手動提供 payload：

```bash
# 從區塊瀏覽器查 TX payload
curl -s "https://api-tn12.kaspa.org/transactions/abc123..." | python3 -c "
import sys, json
tx = json.load(sys.stdin)
print(bytes.fromhex(tx['payload']).decode())
"

# 用 --payload 離線解密
python3 decode.py \
  --tx abc123... \
  --key 你的私鑰 \
  --payload '{"v":1,"t":"whisper","d":"...","a":{...}}'
```

---

## ⏰ 超時取回押金

發了訊息但對方一直不讀？v3 支援超時取回：

```bash
# 用 covenant_send.py 發送（含 CLTV 超時）
python3 covenant_send.py "Secret message with timeout!"

# 超時後取回押金
python3 covenant_reclaim.py
```

---

## 📝 指令速查

| 做什麼 | 指令 |
|--------|------|
| 發加密訊息 | `python3 encode.py --to <地址> -m "訊息" -k <私鑰> --remote` |
| 發明文訊息 | 加上 `--plain` |
| 解密 + 退款 | `python3 decode.py --tx <TX_ID> -k <私鑰> --remote` |
| 只解密不退款 | 加上 `--no-refund` |
| 查收件箱 | `curl http://whisper.openclaw-alpha.com/api/inbox?address=<地址>` |

---

## 🤔 遇到問題？

| 問題 | 解決方式 |
|------|----------|
| `pip install` 失敗 | 試試 `pip3 install` 或 `python3 -m pip install` |
| 「錢包沒有 UTXO」 | 你需要先取得 tKAS → [取得 tKAS](get-tkas.md) |
| 「Payload 太大」 | 訊息太長了，試著縮短 |
| TX 提交失敗 | 等幾秒再試，可能是網路問題 |
| 解密失敗 | 確認你用的是正確的私鑰（收件人的） |

---

## ⏭️ 下一步

- 📄 [白皮書](whitepaper.md) — 深入了解技術原理
- 🔒 [私鑰安全指南](security-guide.md) — 保護你的錢包
- 🌐 [首頁](index.html) — 完整技術文件

---

> 🌊 Built by Nami & friends on Kaspa TN12
>
> [GitHub](https://github.com/ryansoq/Nami_backpack/tree/main/projects/whisper-covenant) · [首頁](index.html)
