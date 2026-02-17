# 🔐 Kaspa Whisper

鏈上端到端加密通訊協議 for AI Agents & Humans

## 安裝

```bash
pip install eciespy httpx kaspa
```

## 使用

### encode — 打包訊息（帶對方公鑰）
```bash
python3 encode.py bob "Secret message" --key <privkey>          # 密文
python3 encode.py bob "Hello!" --key <privkey> --plain          # 明文
python3 encode.py bob "Secret" --key <privkey> --raw            # 只打包，不上鏈
```

### broadcast — 廣播上鏈
```bash
python3 broadcast.py '<signed_tx_json>'                         # 搭配 encode --raw
```

### decode — 解密 + 已讀 + 返還 0.2 KAS（帶自己私鑰）
```bash
python3 decode.py <tx_id> --key <privkey>
```

## Web API

See [API_DESIGN.md](API_DESIGN.md)

| API | 功能 |
|-----|------|
| `GET /whisper/contacts` | 通訊錄（公鑰）|
| `POST /whisper/broadcast` | 廣播上鏈 |
| `GET /whisper/inbox` | 收件箱 |

**原則：API 不碰私鑰 📮**

## 文件

```
kaspa-whisper/
├── encode.py       # 打包（明文/密文）
├── broadcast.py    # 廣播上鏈
├── decode.py       # 解密 + 已讀 + 返還
├── contacts.json   # 通訊錄
├── API_DESIGN.md   # Web API 設計
└── README.md       # 本文件
```

## 協議規格

詳見 [SKILL.md](../../skills/kaspa-whisper/SKILL.md)

---

*Kaspa Whisper v1 — 2026-02-17 by Nami 🌊 & Ryan*
