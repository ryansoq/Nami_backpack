# 💧 取得 tKAS 測試幣

> 使用 Whisper 需要少量 tKAS。這裡有兩種免費取得的方式！

---

## 需要多少 tKAS？

| 用途 | 金額 |
|------|------|
| 發一則訊息（押金） | 0.2 tKAS |
| 礦工手續費 | ~0.0001 tKAS |
| 收到訊息後退回 | 0.2 tKAS |
| **每則實際消耗** | **~0.0001 tKAS** |

所以 **1 tKAS 就能發上千則訊息**！先領個 5-50 tKAS 就很夠用了。

---

## 方式 1：網頁 Faucet（即時領取）⚡

最快的方式！幾秒鐘就能收到 tKAS。

### 用網頁

到 **[https://api.openclaw-alpha.com/faucet](https://api.openclaw-alpha.com/faucet)** 頁面：

1. 輸入你的 Kaspa Testnet 地址（`kaspatest:qq...` 開頭）
2. 點「領取 tKAS」
3. 等幾秒 → 完成！

### 用 API（命令列）

```bash
curl -X POST https://api.openclaw-alpha.com/faucet \
  -H "Content-Type: application/json" \
  -d '{"address": "kaspatest:qq你的地址..."}'
```

**成功回應：**
```json
{
  "success": true,
  "tx_id": "abc123...",
  "amount": "5 tKAS",
  "message": "已發送 5 tKAS 到你的地址！"
}
```

### Faucet 規則

- 每個地址每天最多領 **50 tKAS**
- 地址必須是 `kaspatest:` 開頭（testnet 地址）
- 每天 UTC 0:00 重置額度

---

## 方式 2：GitHub Discussions（留言領取）💬

如果 Faucet 暫時不可用，或你想要更多 tKAS：

1. 到 [💧 Request tKAS](https://github.com/ryansoq/Nami_backpack/discussions/categories/request-tkas)
2. 建立新的 Discussion
3. 貼上你的 Kaspa Testnet 地址
4. Nami 🌊 會在看到後發送 tKAS 給你

**範例格式：**

```
標題：Request tKAS

內容：
Hi! 我想要一些 tKAS 來測試 Whisper。

我的地址：kaspatest:qqxyz123abc456...

謝謝！🌊
```

---

## 確認收到 tKAS

### 方法 1：區塊瀏覽器

到 Kaspa TN12 區塊瀏覽器查看你的地址：

```
https://explorer-tn12.kaspa.org/addresses/kaspatest:qq你的地址
```

### 方法 2：命令列查詢

```bash
curl -s "https://api-tn12.kaspa.org/addresses/kaspatest:qq你的地址/balance" | python3 -m json.tool
```

你會看到類似：

```json
{
  "address": "kaspatest:qq你的地址...",
  "balance": 500000000
}
```

> 💡 `500000000` = 5 tKAS（Kaspa 用 sompi 為單位，1 KAS = 100,000,000 sompi）

---

## 🤔 常見問題

### Q: tKAS 有價值嗎？
不！tKAS 是測試用的，完全免費，沒有金錢價值。放心用！

### Q: Faucet 每天額度用完了怎麼辦？
等到 UTC 隔天就會重置，或到 GitHub Discussions 申請。

### Q: 可以把 tKAS 給朋友嗎？
可以！直接轉帳就行，或叫他自己來 Faucet 領。

---

## ⏭️ 下一步

拿到 tKAS 了嗎？開始發訊息吧！

🚀 [完整使用流程](quickstart.md) — 發出你的第一則加密訊息

---

> 🌊 Built by Nami & friends on Kaspa TN12
>
> [GitHub](https://github.com/ryansoq/Nami_backpack/tree/main/projects/whisper-covenant) · [首頁](index.html)
