#!/usr/bin/env python3
"""
EMA530 Dashboard Data Generator
Fetches market data, calculates signals, runs backtests, outputs data.json
"""
import json
import math
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import yfinance as yf
import pandas as pd
import numpy as np
import requests


def clean_nan(obj):
    """Recursively replace NaN/Infinity with None so json.dump emits valid JSON.

    Python's json writes NaN as the literal `NaN`, which violates JSON spec and
    makes browsers' JSON.parse throw — breaking the dashboard for ALL tickers
    even if only one has a bad value. Run this before json.dump.
    """
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: clean_nan(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean_nan(v) for v in obj]
    return obj

TICKERS = ["TQQQ", "QLD", "SSO", "USD", "00631L.TW", "BTC-USD", "KAS-USD"]

# ATH overheat trim alert config
# Backtest-derived sweet spots (RSI>=75, ADX>=50, cd=0, withdrawal model)
ATH_TRIM_RULES = {
    "TQQQ":      {"trim_pct": 3, "label": "TQQQ 納指3倍"},
    "QLD":       {"trim_pct": 3, "label": "QLD 納指2倍"},
    "SSO":       {"trim_pct": 3, "label": "SSO 標普2倍"},
    "USD":       {"trim_pct": 3, "label": "USD 半導體2倍"},
    "00631L.TW": {"trim_pct": 3, "label": "元大台灣50正2"},
    "BTC-USD":   {"trim_pct": 3, "label": "比特幣"},
    "KAS-USD":   {"trim_pct": 3, "label": "Kaspa"},
}
ATH_RSI_THRESH = 75
ATH_ADX_THRESH = 50
ATH_ALERT_STATE_FILE = Path(__file__).parent / "ath-overheat-alerts.json"
RESEND_API_KEY_FILE = Path.home() / "clawd" / ".secrets" / "resend-api.json"
RESEND_FROM = "Nami <nami@openclaw-alpha.com>"
RESEND_TO = "ryansoq@gmail.com"

# EMA crossover alert config (task #4)
# When a new golden_cross or death_cross is detected, queue an alert. Send it
# 30 minutes before the NEXT market open (T+1 pre-open) for the relevant market.
CROSSOVER_STATE_FILE = Path(__file__).parent / "crossover-alerts.json"
TICKER_MARKET = {
    "TQQQ":      "US",
    "QLD":       "US",
    "SSO":       "US",
    "USD":       "US",
    "00631L.TW": "TW",
    "BTC-USD":   "CRYPTO",
    "KAS-USD":   "CRYPTO",
}
# Send windows in Asia/Taipei time. (market, hour, min_minute, max_minute, weekdays)
# weekdays: Python weekday() — 0=Mon ... 6=Sun
SEND_WINDOWS = [
    # TW market opens 09:00 TPE → flush at 08:30 ±5
    ("TW",     8,  25, 35, [0, 1, 2, 3, 4]),
    # US market opens 09:30 ET. DST: 21:30 TPE → flush at 21:00 ±5
    ("US",     21, 0,  10, [0, 1, 2, 3, 4]),
    # US non-DST: 22:30 TPE → flush at 22:00 ±5 (script handles both, only one fires per year half)
    ("US",     22, 0,  10, [0, 1, 2, 3, 4]),
    # Crypto is 24/7 — arbitrary morning ping every day at 08:00 ±10
    ("CRYPTO", 8,  0,  10, [0, 1, 2, 3, 4, 5, 6]),
]

TICKER_NAMES = {
    "TQQQ": "TQQQ 納指3倍",
    "QLD": "QLD 納指2倍",
    "SSO": "SSO 標普2倍",
    "USD": "USD 半導體2倍",
    "00631L.TW": "元大台灣50正2",
    "BTC-USD": "比特幣",
    "KAS-USD": "Kaspa",
}


def round_price(value, ticker: str | None = None) -> float | None:
    """Round price with precision aware of small-price assets like KAS.

    Sub-dollar prices (e.g. KAS at $0.034) lose meaning at 2 decimals,
    so use 6 decimals when |value| < 1. Dollar-and-up uses 2 decimals.
    """
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return round(v, 6) if abs(v) < 1 else round(v, 2)


def get_signal_action(signal: str, above_ma200: bool | None) -> dict:
    """Signal logic table → action + color + short text"""
    if signal == "golden_cross":
        if above_ma200:
            return {"action": "買入", "color": "green", "detail": "黃金交叉 + MA200上方"}
        elif above_ma200 is False:
            return {"action": "觀望", "color": "yellow", "detail": "黃金交叉但MA200下方，可能假反彈"}
        else:
            return {"action": "買入", "color": "green", "detail": "黃金交叉（MA200不足）"}
    elif signal == "death_cross":
        return {"action": "賣出", "color": "red", "detail": "死亡交叉，建議退場"}
    elif signal == "bullish":
        if above_ma200:
            return {"action": "持有", "color": "green", "detail": "多頭排列 + MA200上方"}
        elif above_ma200 is False:
            return {"action": "謹慎持有", "color": "yellow", "detail": "多頭但MA200下方"}
        else:
            return {"action": "持有", "color": "green", "detail": "多頭排列"}
    else:  # bearish
        if above_ma200 is False:
            return {"action": "空手觀望", "color": "red", "detail": "空頭 + MA200下方"}
        elif above_ma200:
            return {"action": "短期回調", "color": "yellow", "detail": "空頭但MA200上方，留意反轉"}
        else:
            return {"action": "空手觀望", "color": "red", "detail": "空頭排列"}


def find_crossovers(ema5: pd.Series, ema30: pd.Series, close: pd.Series, months: int = 6) -> list:
    """Find all EMA5/EMA30 crossovers in last N months"""
    cutoff = datetime.now() - timedelta(days=months * 30)
    crossovers = []

    for i in range(1, len(ema5)):
        date = ema5.index[i]
        if hasattr(date, 'tz') and date.tz:
            check_date = date.tz_localize(None)
        else:
            check_date = date
        if pd.Timestamp(check_date) < pd.Timestamp(cutoff):
            continue

        prev_diff = float(ema5.iloc[i - 1] - ema30.iloc[i - 1])
        curr_diff = float(ema5.iloc[i] - ema30.iloc[i])

        if prev_diff <= 0 and curr_diff > 0:
            cross_type = "golden_cross"
        elif prev_diff >= 0 and curr_diff < 0:
            cross_type = "death_cross"
        else:
            continue

        price_at_cross = float(close.iloc[i])
        # Calculate subsequent price change
        future_idx = min(i + 10, len(close) - 1)
        future_price = float(close.iloc[future_idx])
        pct_change = ((future_price - price_at_cross) / price_at_cross) * 100

        # Also get change to current
        current_price = float(close.iloc[-1])
        pct_to_now = ((current_price - price_at_cross) / price_at_cross) * 100

        crossovers.append({
            "date": date.strftime("%Y-%m-%d"),
            "type": cross_type,
            "price": price_at_cross,
            "pct_change_10d": round(pct_change, 2),
            "pct_to_now": round(pct_to_now, 2),
        })

    return crossovers


def days_since_last_crossover(ema5: pd.Series, ema30: pd.Series) -> int:
    """Find days since last crossover"""
    for i in range(len(ema5) - 1, 0, -1):
        prev_diff = float(ema5.iloc[i - 1] - ema30.iloc[i - 1])
        curr_diff = float(ema5.iloc[i] - ema30.iloc[i])
        if (prev_diff <= 0 and curr_diff > 0) or (prev_diff >= 0 and curr_diff < 0):
            last_date = ema5.index[i]
            if hasattr(last_date, 'tz') and last_date.tz:
                last_date = last_date.tz_localize(None)
            return (datetime.now() - pd.Timestamp(last_date)).days
    return -1


def run_backtest(close: pd.Series, ema5: pd.Series, ema30: pd.Series, years: int = 3) -> dict:
    """Simple EMA530 crossover backtest"""
    cutoff = datetime.now() - timedelta(days=years * 365)
    
    # Align series
    start_idx = 0
    for i in range(len(close)):
        date = close.index[i]
        if hasattr(date, 'tz') and date.tz:
            check_date = date.tz_localize(None)
        else:
            check_date = date
        if pd.Timestamp(check_date) >= pd.Timestamp(cutoff):
            start_idx = i
            break

    close_bt = close.iloc[start_idx:]
    ema5_bt = ema5.iloc[start_idx:]
    ema30_bt = ema30.iloc[start_idx:]

    if len(close_bt) < 30:
        return {"error": "insufficient data"}

    # Trading simulation
    position = False
    entry_price = 0
    trades = []
    equity = [1.0]

    for i in range(1, len(close_bt)):
        prev_diff = float(ema5_bt.iloc[i - 1] - ema30_bt.iloc[i - 1])
        curr_diff = float(ema5_bt.iloc[i] - ema30_bt.iloc[i])

        # Golden cross → buy
        if not position and prev_diff <= 0 and curr_diff > 0:
            position = True
            entry_price = float(close_bt.iloc[i])

        # Death cross → sell
        elif position and prev_diff >= 0 and curr_diff < 0:
            exit_price = float(close_bt.iloc[i])
            pnl = (exit_price - entry_price) / entry_price
            trades.append(pnl)
            position = False

        # Track equity
        if position:
            daily_ret = float(close_bt.iloc[i] / close_bt.iloc[i - 1]) - 1
            equity.append(equity[-1] * (1 + daily_ret))
        else:
            equity.append(equity[-1])

    # Close open position
    if position:
        exit_price = float(close_bt.iloc[-1])
        pnl = (exit_price - entry_price) / entry_price
        trades.append(pnl)

    equity = np.array(equity)
    total_return = equity[-1] / equity[0] - 1
    
    # CAGR
    n_days = len(close_bt)
    n_years = n_days / 252
    cagr = (equity[-1] ** (1 / max(n_years, 0.01))) - 1 if equity[-1] > 0 else -1

    # Max drawdown
    peak = np.maximum.accumulate(equity)
    drawdown = (equity - peak) / peak
    max_dd = float(np.min(drawdown)) * 100

    # Win rate
    wins = len([t for t in trades if t > 0])
    win_rate = (wins / len(trades) * 100) if trades else 0

    # Buy & hold
    bh_return = (float(close_bt.iloc[-1]) / float(close_bt.iloc[0]) - 1) * 100

    return {
        "total_return": round(total_return * 100, 2),
        "cagr": round(cagr * 100, 2),
        "max_drawdown": round(max_dd, 2),
        "win_rate": round(win_rate, 1),
        "total_trades": len(trades),
        "buy_hold_return": round(bh_return, 2),
    }


def adjust_for_splits(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Auto-detect & apply split adjustments that yfinance missed.

    Yahoo's data for some tickers (notably 00631L.TW) does not record splits
    in the .splits series or auto-adjust them in the price history. We detect
    a split as any single-day close drop of more than 50% — no legitimate
    daily move for a listed ETF/stock comes close to this (circuit breakers
    cap daily moves well below that on every major exchange), so false
    positives are extremely unlikely.

    For each detected split we divide all strictly-earlier OHLC values by the
    ratio, and multiply the volume by the same ratio, preserving dollar-
    volume continuity. Works for multiple splits by processing them in
    chronological order.
    """
    close = df['Close'].squeeze().dropna()
    if len(close) < 2:
        return df

    pct = close.pct_change()
    suspects = pct[pct < -0.5]
    if suspects.empty:
        return df

    adjusted = df.copy()
    # Volume is int64 by default; after multiplying by a float ratio the
    # values become floats, so promote the column up-front to avoid a
    # pandas FutureWarning about incompatible dtype assignment.
    if 'Volume' in adjusted.columns:
        adjusted['Volume'] = adjusted['Volume'].astype(float)
    for date in suspects.index:
        prev = close.loc[:date].iloc[-2]
        curr = close.loc[date]
        ratio = prev / curr
        mask = adjusted.index < date
        for col in ('Open', 'High', 'Low', 'Close'):
            if col in adjusted.columns:
                adjusted.loc[mask, col] = adjusted.loc[mask, col] / ratio
        if 'Volume' in adjusted.columns:
            adjusted.loc[mask, 'Volume'] = adjusted.loc[mask, 'Volume'] * ratio
        print(
            f"    [split] {ticker} {date.date()}: ratio {ratio:.2f}:1 — "
            f"adjusted {int(mask.sum())} prior rows",
            file=sys.stderr,
        )

    return adjusted


def analyze_ticker(ticker: str) -> dict:
    """Full analysis for one ticker"""
    print(f"  Fetching {ticker}...", file=sys.stderr)

    # Get 3+ years of data for backtest
    df = yf.download(ticker, period="4y", interval="1d", progress=False)
    if df.empty:
        return {"ticker": ticker, "name": TICKER_NAMES.get(ticker, ticker), "error": "NO DATA"}

    # yfinance returns MultiIndex columns ('Close', 'TICKER'); flatten for
    # plain-string column access in dropna/adjust_for_splits.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # Drop rows with NaN Close (e.g. today's bar before the session closes),
    # then auto-detect and apply any splits yfinance missed.
    df = df.dropna(subset=['Close'])
    df = adjust_for_splits(df, ticker)
    if df.empty:
        return {"ticker": ticker, "name": TICKER_NAMES.get(ticker, ticker), "error": "NO DATA"}

    close = df['Close'].squeeze()
    ema5 = close.ewm(span=5, adjust=False).mean()
    ema30 = close.ewm(span=30, adjust=False).mean()
    ma200 = close.rolling(window=200).mean()

    # RSI(14)
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(com=13, min_periods=14).mean()
    avg_loss = loss.ewm(com=13, min_periods=14).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    # ADX(14)
    high = df['High'].squeeze()
    low = df['Low'].squeeze()
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr14 = tr.ewm(span=14, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(span=14, adjust=False).mean() / atr14)
    minus_di = 100 * (minus_dm.ewm(span=14, adjust=False).mean() / atr14)
    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di))
    adx = dx.ewm(span=14, adjust=False).mean()

    # Volume
    vol = df['Volume'].squeeze()
    vol_avg20 = vol.rolling(20).mean()

    last_close = float(close.iloc[-1])
    last_ema5 = float(ema5.iloc[-1])
    last_ema30 = float(ema30.iloc[-1])
    prev_ema5 = float(ema5.iloc[-2])
    prev_ema30 = float(ema30.iloc[-2])
    last_ma200 = float(ma200.iloc[-1]) if pd.notna(ma200.iloc[-1]) else None
    last_rsi = float(rsi.iloc[-1]) if pd.notna(rsi.iloc[-1]) else None
    last_adx = float(adx.iloc[-1]) if pd.notna(adx.iloc[-1]) else None
    last_plus_di = float(plus_di.iloc[-1]) if pd.notna(plus_di.iloc[-1]) else None
    last_minus_di = float(minus_di.iloc[-1]) if pd.notna(minus_di.iloc[-1]) else None
    last_vol = float(vol.iloc[-1]) if pd.notna(vol.iloc[-1]) else None
    last_vol_avg = float(vol_avg20.iloc[-1]) if pd.notna(vol_avg20.iloc[-1]) else None
    vol_ratio = round(last_vol / last_vol_avg, 2) if last_vol and last_vol_avg and last_vol_avg > 0 else None

    # Signal detection
    if prev_ema5 <= prev_ema30 and last_ema5 > last_ema30:
        signal = "golden_cross"
    elif prev_ema5 >= prev_ema30 and last_ema5 < last_ema30:
        signal = "death_cross"
    elif last_ema5 > last_ema30:
        signal = "bullish"
    else:
        signal = "bearish"

    gap_pct = ((last_ema5 - last_ema30) / last_ema30) * 100

    above_ma200 = None
    ma200_dist = None
    if last_ma200 is not None:
        above_ma200 = last_close > last_ma200
        ma200_dist = ((last_close - last_ma200) / last_ma200) * 100

    action_info = get_signal_action(signal, above_ma200)

    # ATH
    ath = float(close.max())
    ath_dist = ((last_close - ath) / ath) * 100

    # Last 60 days for chart
    recent = close.iloc[-60:]
    recent_ema5 = ema5.iloc[-60:]
    recent_ema30 = ema30.iloc[-60:]
    chart_data = {
        "dates": [d.strftime("%m/%d") for d in recent.index],
        "close": [round_price(v, ticker) for v in recent.values],
        "ema5": [round_price(v, ticker) for v in recent_ema5.values],
        "ema30": [round_price(v, ticker) for v in recent_ema30.values],
    }

    # Crossovers in last 6 months
    crossovers = find_crossovers(ema5, ema30, close, months=6)

    # Days since last crossover
    days_cross = days_since_last_crossover(ema5, ema30)

    # Backtest
    backtest = run_backtest(close, ema5, ema30, years=3)

    return {
        "ticker": ticker,
        "name": TICKER_NAMES.get(ticker, ticker),
        "close": round_price(last_close, ticker),
        "ema5": round_price(last_ema5, ticker),
        "ema30": round_price(last_ema30, ticker),
        "gap_pct": round(gap_pct, 2),
        "signal": signal,
        "ma200": round_price(last_ma200, ticker),
        "above_ma200": above_ma200,
        "ma200_dist": round(ma200_dist, 2) if ma200_dist else None,
        "action": action_info["action"],
        "action_color": action_info["color"],
        "action_detail": action_info["detail"],
        "ath": round_price(ath, ticker),
        "ath_dist": round(ath_dist, 2),
        "rsi": round(last_rsi, 1) if last_rsi else None,
        "adx": round(last_adx, 1) if last_adx else None,
        "plus_di": round(last_plus_di, 1) if last_plus_di else None,
        "minus_di": round(last_minus_di, 1) if last_minus_di else None,
        "vol_today": last_vol,
        "vol_avg20": last_vol_avg,
        "vol_ratio": vol_ratio,
        "days_since_crossover": days_cross,
        "chart": chart_data,
        "crossovers": crossovers,
        "backtest": backtest,
    }


def _send_resend_email(subject: str, html: str) -> bool:
    """Send email via Resend API. Returns True on success."""
    if not RESEND_API_KEY_FILE.exists():
        print("  ⚠️  No Resend API key file", file=sys.stderr)
        return False
    try:
        api_key = json.loads(RESEND_API_KEY_FILE.read_text())["api_key"]
    except (json.JSONDecodeError, KeyError):
        print("  ⚠️  Bad Resend API key file", file=sys.stderr)
        return False
    try:
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "from": RESEND_FROM,
                "to": [RESEND_TO],
                "subject": subject,
                "html": html,
            },
            timeout=10,
        )
        if resp.ok:
            return True
        print(f"  ⚠️  Resend API error: {resp.text}", file=sys.stderr)
    except Exception as e:
        print(f"  ⚠️  Resend send error: {e}", file=sys.stderr)
    return False


def _send_tg_alert(msg: str) -> bool:
    """Send alert via Telegram Bot API. Returns True on success."""
    tg_env = Path.home() / ".claude" / "channels" / "telegram" / ".env"
    tg_token = None
    tg_chat_id = "5168530096"  # Ryan
    if tg_env.exists():
        for line in tg_env.read_text().splitlines():
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                tg_token = line.split("=", 1)[1].strip()
    if not tg_token:
        return False
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{tg_token}/sendMessage",
            json={"chat_id": tg_chat_id, "text": msg},
            timeout=10,
        )
        return resp.ok
    except Exception:
        return False


def check_ath_overheat_alerts(ticker_data_list: list):
    """Check tickers for ATH + RSI + ADX overheat and send email + TG alert.

    Uses aggressive (cd=0) rule: alert every day the condition holds, but
    dedup within the same calendar date to handle multiple generate_data runs.
    """
    today = datetime.now().strftime("%Y-%m-%d")

    # Load prior alert state
    state = {}
    if ATH_ALERT_STATE_FILE.exists():
        try:
            state = json.loads(ATH_ALERT_STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            state = {}

    alerts_fired = []
    for data in ticker_data_list:
        ticker = data.get("ticker", "")
        if ticker not in ATH_TRIM_RULES:
            continue

        rsi = data.get("rsi")
        adx = data.get("adx")
        close = data.get("close")
        ath = data.get("ath")
        if rsi is None or adx is None or close is None or ath is None:
            continue

        # Check: at ATH (within 0.5% to handle rounding), RSI >= 75, ADX >= 50
        at_ath = close >= ath * 0.995
        overheated = rsi >= ATH_RSI_THRESH and adx >= ATH_ADX_THRESH

        if not (at_ath and overheated):
            continue

        # Dedup: already alerted today for this ticker?
        last_alert = state.get(ticker, {}).get("last_date", "")
        if last_alert == today:
            print(f"  ℹ️  {ticker} ATH overheat — already alerted today", file=sys.stderr)
            continue

        rule = ATH_TRIM_RULES[ticker]
        trim = rule["trim_pct"]
        label = rule["label"]

        # Plain text for TG
        tg_msg = (
            f"🔥 過熱減倉提醒 — {label} ({ticker})\n\n"
            f"收盤 {close} = 歷史新高！\n"
            f"RSI(14) = {rsi} ≥ 75 ✓\n"
            f"ADX(14) = {adx} ≥ 50 ✓\n\n"
            f"👉 建議賣出持股的 {trim}%\n"
            f"（回測甜蜜點：最大化提領且本金持續成長）"
        )

        # HTML for email
        email_html = f"""
<h2>🔥 過熱減倉提醒 — {label} ({ticker})</h2>
<table style="border-collapse:collapse;font-size:16px;">
  <tr><td style="padding:4px 12px;">收盤價</td><td style="padding:4px 12px;font-weight:bold;">{close}</td><td>= 歷史新高！</td></tr>
  <tr><td style="padding:4px 12px;">RSI(14)</td><td style="padding:4px 12px;font-weight:bold;">{rsi}</td><td>≥ 75 ✓</td></tr>
  <tr><td style="padding:4px 12px;">ADX(14)</td><td style="padding:4px 12px;font-weight:bold;">{adx}</td><td>≥ 50 ✓</td></tr>
</table>
<br>
<p style="font-size:20px;">👉 建議賣出持股的 <strong>{trim}%</strong></p>
<p style="color:#666;">回測甜蜜點：最大化提領且本金持續成長（RSI≥75 + ADX≥50 + 新 ATH，cd=0）</p>
<hr>
<p style="color:#999;font-size:12px;">— Nami @ EMA530 Dashboard</p>
"""

        email_ok = _send_resend_email(
            f"🔥 {label} 過熱！建議賣 {trim}% — 收盤 {close}", email_html
        )
        tg_ok = _send_tg_alert(tg_msg)

        if email_ok or tg_ok:
            channels = []
            if email_ok:
                channels.append("email")
            if tg_ok:
                channels.append("TG")
            print(f"  🔔 ATH alert sent for {ticker} via {'+'.join(channels)}", file=sys.stderr)
            state[ticker] = {"last_date": today, "close": close, "rsi": rsi, "adx": adx}
            alerts_fired.append(ticker)
        else:
            print(f"  ⚠️  Failed to send alert for {ticker}", file=sys.stderr)

    # Persist state
    if alerts_fired:
        ATH_ALERT_STATE_FILE.write_text(json.dumps(state, indent=2))

    if not alerts_fired:
        triggered = [t for t in ATH_TRIM_RULES if any(
            d["ticker"] == t and d.get("rsi") and d["rsi"] >= ATH_RSI_THRESH
            and d.get("adx") and d["adx"] >= ATH_ADX_THRESH
            for d in ticker_data_list
        )]
        if triggered:
            print(f"  ℹ️  RSI+ADX hot but not at ATH: {triggered}", file=sys.stderr)
        else:
            print("  ✅ No ATH overheat conditions met", file=sys.stderr)


def _send_crossover_alert(ticker: str, entry: dict) -> bool:
    """Send EMA crossover alert via email + TG. Returns True if at least one channel succeeded."""
    signal = entry["last_cross_signal"]
    detected_at = entry.get("detected_at", "?")
    close = entry.get("close")
    above_ma200 = entry.get("above_ma200")
    ma200_dist = entry.get("ma200_dist")
    name = TICKER_NAMES.get(ticker, ticker)

    if signal == "golden_cross":
        emoji = "🟢"
        action = "黃金交叉"
        if above_ma200:
            suggest = "MA200 上方 → 建議買入"
        elif above_ma200 is False:
            suggest = "⚠️ MA200 下方 → 觀望，可能假反彈"
        else:
            suggest = "建議買入（MA200 資料不足）"
    else:  # death_cross
        emoji = "🔴"
        action = "死亡交叉"
        suggest = "建議賣出退場"

    ma200_status = "上方 ✓" if above_ma200 else ("下方 ✗" if above_ma200 is False else "N/A")
    ma200_dist_str = f"{ma200_dist:+.2f}%" if ma200_dist is not None else "N/A"

    subject = f"{emoji} {name} EMA530 {action}"

    tg_msg = (
        f"{emoji} EMA530 {action} — {name} ({ticker})\n\n"
        f"偵測時間: {detected_at}\n"
        f"收盤價: {close}\n"
        f"MA200: {ma200_status} ({ma200_dist_str})\n\n"
        f"👉 {suggest}\n\n"
        f"⏰ T+1 開盤前 30 分鐘提醒"
    )

    email_html = f"""
<h2>{emoji} EMA530 {action} — {name} ({ticker})</h2>
<table style="border-collapse:collapse;font-size:16px;">
  <tr><td style="padding:4px 12px;">偵測時間</td><td style="padding:4px 12px;font-weight:bold;">{detected_at}</td></tr>
  <tr><td style="padding:4px 12px;">收盤價</td><td style="padding:4px 12px;font-weight:bold;">{close}</td></tr>
  <tr><td style="padding:4px 12px;">MA200</td><td style="padding:4px 12px;">{ma200_status} ({ma200_dist_str})</td></tr>
</table>
<br>
<p style="font-size:20px;">👉 {suggest}</p>
<hr>
<p style="color:#999;font-size:12px;">— Nami @ EMA530 Dashboard | T+1 開盤前 30 分鐘提醒</p>
"""

    email_ok = _send_resend_email(subject, email_html)
    tg_ok = _send_tg_alert(tg_msg)
    return email_ok or tg_ok


def check_new_crossover_alerts(ticker_data_list: list):
    """Detect new EMA5/EMA30 crossovers and send alerts at T+1 pre-open.

    State: crossover-alerts.json — per-ticker last_cross_signal + alert_pending flag.
    Detection: signal transition (state's last differs from current golden/death_cross).
    Sending: only when current TPE time falls in a SEND_WINDOWS entry matching the ticker's market.
    """
    state = {}
    if CROSSOVER_STATE_FILE.exists():
        try:
            state = json.loads(CROSSOVER_STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            state = {}

    bootstrap = not state  # First-ever run — record current signals without alerting

    # 1. Detect new crosses (signal transition vs state)
    for data in ticker_data_list:
        ticker = data.get("ticker", "")
        if ticker not in TICKER_MARKET:
            continue
        signal = data.get("signal", "")
        if signal not in ("golden_cross", "death_cross"):
            continue

        prior_signal = state.get(ticker, {}).get("last_cross_signal")
        if prior_signal == signal:
            continue  # Same cross already recorded

        state[ticker] = {
            "last_cross_signal": signal,
            "detected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "alert_pending": not bootstrap,
            "close": data.get("close"),
            "above_ma200": data.get("above_ma200"),
            "ma200_dist": data.get("ma200_dist"),
        }
        if bootstrap:
            print(f"  🌱 Bootstrap: recorded {signal} for {ticker} (no alert)", file=sys.stderr)
        else:
            print(f"  🆕 New {signal} for {ticker} — queued for next pre-open", file=sys.stderr)

    # 2. Flush pending alerts if we're in a send window (skip during bootstrap)
    if not bootstrap:
        now_tpe = datetime.now(ZoneInfo("Asia/Taipei"))
        for market, hour, mn_min, mn_max, weekdays in SEND_WINDOWS:
            if now_tpe.weekday() not in weekdays:
                continue
            if now_tpe.hour != hour:
                continue
            if not (mn_min <= now_tpe.minute <= mn_max):
                continue
            # In window — flush any pending alerts for this market
            for ticker, entry in list(state.items()):
                if not entry.get("alert_pending"):
                    continue
                if TICKER_MARKET.get(ticker) != market:
                    continue
                if _send_crossover_alert(ticker, entry):
                    state[ticker]["alert_pending"] = False
                    state[ticker]["alert_sent_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    print(f"  📤 Sent {entry['last_cross_signal']} alert for {ticker}", file=sys.stderr)
                else:
                    print(f"  ⚠️  Failed to send {ticker} alert (will retry next window)", file=sys.stderr)

    # 3. Save state
    CROSSOVER_STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def main():
    print("🔄 Generating EMA530 dashboard data...", file=sys.stderr)
    
    results = []
    all_crossovers = []
    
    for ticker in TICKERS:
        data = analyze_ticker(ticker)
        results.append(data)
        
        if "crossovers" in data:
            for c in data["crossovers"]:
                all_crossovers.append({
                    "ticker": ticker,
                    "name": TICKER_NAMES.get(ticker, ticker),
                    **c
                })

    # Sort crossovers by date descending
    all_crossovers.sort(key=lambda x: x["date"], reverse=True)

    output = {
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tickers": results,
        "signal_history": all_crossovers,
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(clean_nan(output), f, ensure_ascii=False, indent=2, allow_nan=False)

    print("✅ data.json generated!", file=sys.stderr)

    # Check ATH overheat alerts for monitored tickers
    check_ath_overheat_alerts(results)

    # Check EMA crossover alerts (task #4) — queue + flush at T+1 pre-open
    check_new_crossover_alerts(results)


if __name__ == "__main__":
    main()
