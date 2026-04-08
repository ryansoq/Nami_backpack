#!/usr/bin/env python3
"""
EMA530 Dashboard Data Generator
Fetches market data, calculates signals, runs backtests, outputs data.json
"""
import json
import math
import sys
from datetime import datetime, timedelta
import yfinance as yf
import pandas as pd
import numpy as np


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

TICKERS = ["TQQQ", "QLD", "SSO", "00631L.TW", "BTC-USD", "KAS-USD"]

TICKER_NAMES = {
    "TQQQ": "TQQQ 納指3倍",
    "QLD": "QLD 納指2倍",
    "SSO": "SSO 標普2倍",
    "00631L.TW": "元大台灣50正2",
    "BTC-USD": "比特幣",
    "KAS-USD": "Kaspa",
}


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


def analyze_ticker(ticker: str) -> dict:
    """Full analysis for one ticker"""
    print(f"  Fetching {ticker}...", file=sys.stderr)
    
    # Get 3+ years of data for backtest
    df = yf.download(ticker, period="4y", interval="1d", progress=False)
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
        "close": [round(float(v), 2) for v in recent.values],
        "ema5": [round(float(v), 2) for v in recent_ema5.values],
        "ema30": [round(float(v), 2) for v in recent_ema30.values],
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
        "close": round(last_close, 2),
        "ema5": round(last_ema5, 2),
        "ema30": round(last_ema30, 2),
        "gap_pct": round(gap_pct, 2),
        "signal": signal,
        "ma200": round(last_ma200, 2) if last_ma200 else None,
        "above_ma200": above_ma200,
        "ma200_dist": round(ma200_dist, 2) if ma200_dist else None,
        "action": action_info["action"],
        "action_color": action_info["color"],
        "action_detail": action_info["detail"],
        "ath": round(ath, 2),
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


if __name__ == "__main__":
    main()
