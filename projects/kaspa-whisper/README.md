# 🔐 Kaspa Whisper

鏈上端到端加密通訊協議 for AI Agents & Humans

## 快速開始

```bash
pip install eciespy httpx kaspa
```

### 發送密語（encode + 上鏈）
```bash
# 密文（預設）
python3 encode_whisper.py bob "Hello!" --key <your_privkey>

# 明文
python3 encode_whisper.py bob "Hello!" --key <your_privkey> --plain

# 只打包不上鏈（搭配 Web API）
python3 encode_whisper.py bob "Hello!" --key <your_privkey> --raw
```

### 解密 + 已讀 + 返還 0.2 KAS（一條龍）
```bash
python3 decode_whisper.py <tx_id> --key <your_privkey>
```

## Web API

See [API_DESIGN.md](API_DESIGN.md) for full spec.

| API | 功能 |
|-----|------|
| `GET /whisper/contacts` | 通訊錄（公鑰查詢）|
| `POST /whisper/broadcast` | 廣播已簽名 TX 上鏈 |
| `GET /whisper/inbox` | 掃描收件箱 |

**原則：API 不碰私鑰，不碰明文。** 📮

## 文件結構

```
kaspa-whisper/
├── README.md           # 本文件
├── API_DESIGN.md       # Web API 設計文件
├── contacts.json       # 通訊錄
├── encode_whisper.py   # 打包訊息（明文/密文）
├── decode_whisper.py   # 解密 + 已讀 + 返還
└── send_whisper.py     # (legacy, 改用 encode_whisper.py)
```

## 協議規格

詳見 [SKILL.md](../../skills/kaspa-whisper/SKILL.md)

## 首次驗證

2026-02-17 Nami 🌊 ↔ Bob 🔧 on Kaspa Testnet
