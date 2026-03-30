# 📊 EMA530 量化儀表板

> 不要相信這次會不一樣，相信數據

基於 EMA5/EMA30 交叉策略的量化交易信號儀表板，追蹤 QLD、SSO、00631L.TW、BTC、KAS。

## 功能

- **即時信號** — 每個標的的 EMA530 交叉狀態 + MA200 趨勢判斷
- **買賣建議** — 結合 EMA530 信號與 MA200 位置的操作建議
- **迷你圖表** — 近 60 天收盤價與 EMA5/EMA30 走勢
- **信號歷史** — 近 6 個月所有交叉事件及後續漲跌
- **回測績效** — 近 3 年 EMA530 策略 vs Buy & Hold

## 信號邏輯

| EMA530 | MA200 | 建議 |
|--------|-------|------|
| 黃金交叉 | 上方 | 🟢 買入 |
| 黃金交叉 | 下方 | 🟡 觀望（可能假反彈）|
| 多頭排列 | 上方 | 🟢 持有 |
| 多頭排列 | 下方 | 🟡 謹慎持有 |
| 空頭排列 | 上方 | 🟡 短期回調 |
| 空頭排列 | 下方 | 🔴 空手觀望 |
| 死亡交叉 | 任何 | 🔴 賣出 |

## 使用方式

```bash
# 一鍵啟動（生成數據 + 開服務器）
bash start.sh

# 或分開執行
python3 generate_data.py    # 產生 data.json
python3 -m http.server 18806  # 開啟 http://localhost:18806
```

## 需求

- Python 3.8+
- yfinance (`pip install yfinance`)
- pandas, numpy (通常隨 yfinance 安裝)

## 自動更新

可搭配 cron 定時更新數據：

```bash
# 每小時更新一次（台股開盤時間）
0 9-14 * * 1-5 cd ~/nami-backpack/projects/ema530-dashboard && python3 generate_data.py
```

## ⚠️ 免責聲明

此工具僅供學習參考，不構成投資建議。投資有風險，決策請自行判斷。
