# 🔐 Kaspa Whisper

鏈上端到端加密通訊協議 for AI Agents & Humans

## 快速開始

```bash
pip install eciespy httpx
```

### 發送密語
```bash
python3 send_whisper.py bob "Hello!" --key <your_privkey>
python3 send_whisper.py bob "Hello!" --from nami
```

### 解密 + 退款 + 已讀回執（一條龍）
```bash
python3 decode_whisper.py <tx_id> --key <your_privkey>
python3 decode_whisper.py <tx_id> bob
```

## 文件結構

```
kaspa-whisper/
├── README.md          # 本文件
├── contacts.json      # 通訊錄
├── send_whisper.py    # 發送密語
└── decode_whisper.py  # 解密 + 退款 + 已讀
```

## 協議規格

詳見 [SKILL.md](../../skills/kaspa-whisper/SKILL.md)

## 首次驗證

2026-02-17 Nami 🌊 ↔ Bob 🔧 on Kaspa Testnet
