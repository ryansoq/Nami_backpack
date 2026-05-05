#!/usr/bin/env python3
"""
Backtest: 00631L.TW asymmetric grid trading

Ryan's strategy (2026-05-02):
- Total capital NT$800,000
- Split: some % buy stock at start, rest as cash reserve
- Rule: every X% drop (vs last trade price) → buy Y NT$ worth
        every X% rise (vs last trade price) → sell Z NT$ worth
        asymmetric Y > Z so net effect is "accumulate during dips,
        skim small cash on rallies"
- Optional overlay: RSI ≥ 75 AND at-ATH → sell 3% of holdings
  (Ryan's existing overheat trim rule)

Goal: find the sweet spot — extract meaningful cash while keeping
most of B&H's upside. Not trying to beat B&H on paper; B&H is the
upper bound on total wealth. The question is "how much cash flow
without bleeding the underlying position".

Authors: Ryan & Nami ✨
"""
import itertools
import sys

import numpy as np
import pandas as pd
import yfinance as yf


TICKER = "00631L.TW"
INITIAL_CAPITAL = 800_000  # NT$
PERIOD_YEARS = 5


def adjust_for_splits(df: pd.DataFrame) -> pd.DataFrame:
    """Detect >50% single-day drops as missed splits, retroactively divide
    earlier OHLC by the inferred ratio (same logic as generate_data.py).
    00631L had this issue early on."""
    close = df["Close"].squeeze().dropna()
    if len(close) < 2:
        return df
    pct = close.pct_change()
    suspects = pct[pct < -0.5]
    if suspects.empty:
        return df
    adjusted = df.copy()
    for date, drop in suspects.items():
        ratio = 1 / (1 + drop)
        before_idx = adjusted.index < date
        for col in ["Open", "High", "Low", "Close"]:
            if col in adjusted.columns:
                adjusted.loc[before_idx, col] = (
                    adjusted.loc[before_idx, col] / ratio
                )
    return adjusted


def fetch_data() -> pd.DataFrame:
    """Pull 5 years of daily OHLC + RSI + ATH info."""
    df = yf.Ticker(TICKER).history(
        period=f"{PERIOD_YEARS}y", auto_adjust=False
    )
    df = adjust_for_splits(df)
    df = df[["Open", "High", "Low", "Close"]].dropna()

    # RSI(14)
    delta = df["Close"].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = -delta.where(delta < 0, 0).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    df["RSI"] = 100 - 100 / (1 + rs)

    # ATH up to today
    df["ATH"] = df["Close"].cummax()

    return df.dropna()


def run_grid_strategy(
    df: pd.DataFrame,
    initial_stock_pct: float,  # 0..1, fraction of capital initially in stock
    drop_pct: float,           # 0..0.05, e.g. 0.01 for 1%
    rise_pct: float,           # same
    buy_ntd: int,              # NT$ buy on each drop trigger
    sell_ntd: int,             # NT$ sell on each rise trigger
    apply_overheat: bool = True,
    rsi_thresh: float = 75,
    overheat_trim_pct: float = 0.03,
    overheat_cooldown_days: int = 0,
    grid_sell: bool = True,    # if False → A mode (no grid sell)
):
    """Walk daily; return (final_position_value, total_cash_extracted,
    max_drawdown_pct, num_trades, cash_balance, shares_held)."""
    initial_price = df["Close"].iloc[0]
    initial_stock_ntd = INITIAL_CAPITAL * initial_stock_pct
    shares = initial_stock_ntd / initial_price
    cash_reserve = INITIAL_CAPITAL - initial_stock_ntd  # buying-power cash
    cash_extracted = 0.0  # cash that's been "withdrawn" out of the system
    last_trade_price = initial_price
    num_trades = 0

    portfolio_history = []  # list of total values to compute max drawdown
    last_overheat_trim = -10**9

    for i, (_, row) in enumerate(df.iterrows()):
        price = row["Close"]
        rsi = row["RSI"]
        is_at_ath = price >= row["ATH"] * 0.995  # within 0.5% of ATH

        # ── overheat overlay ────────────────────────────────────────
        if (apply_overheat and rsi >= rsi_thresh and is_at_ath
                and (i - last_overheat_trim) >= overheat_cooldown_days):
            sell_shares = shares * overheat_trim_pct
            cash_extracted += sell_shares * price
            shares -= sell_shares
            num_trades += 1
            last_trade_price = price
            last_overheat_trim = i

        # ── grid drop trigger ───────────────────────────────────────
        if price <= last_trade_price * (1 - drop_pct):
            if cash_reserve >= buy_ntd:
                shares += buy_ntd / price
                cash_reserve -= buy_ntd
                num_trades += 1
                last_trade_price = price

        # ── grid rise trigger ───────────────────────────────────────
        elif grid_sell and price >= last_trade_price * (1 + rise_pct):
            sell_value = min(sell_ntd, shares * price)
            sell_shares = sell_value / price
            shares -= sell_shares
            cash_extracted += sell_value
            num_trades += 1
            last_trade_price = price
        elif not grid_sell and price >= last_trade_price * (1 + rise_pct):
            # mode A: still update last_trade_price on rise so the next
            # drop trigger is relative to the new high (ratchet behaviour)
            last_trade_price = price

        # ── track total portfolio for drawdown ──────────────────────
        # Total value = stock market value + cash reserve (NOT extracted cash,
        # since that's already spent). For drawdown, we care about
        # total wealth still under the strategy's control.
        total_under_management = shares * price + cash_reserve
        portfolio_history.append(total_under_management)

    final_price = df["Close"].iloc[-1]
    final_position_value = shares * final_price
    total_wealth = final_position_value + cash_reserve + cash_extracted

    # max drawdown of the under-management portfolio
    pv = pd.Series(portfolio_history)
    rolling_peak = pv.cummax()
    drawdown = (pv - rolling_peak) / rolling_peak
    max_drawdown = drawdown.min() * 100  # as %

    return {
        "final_position_value": final_position_value,
        "cash_reserve": cash_reserve,
        "cash_extracted": cash_extracted,
        "total_wealth": total_wealth,
        "max_drawdown_pct": max_drawdown,
        "num_trades": num_trades,
        "shares": shares,
        "final_price": final_price,
    }


def run_buy_and_hold(df: pd.DataFrame):
    """Baseline: 100% of capital into stock at start, never trade."""
    initial_price = df["Close"].iloc[0]
    shares = INITIAL_CAPITAL / initial_price

    pv = df["Close"] * shares
    rolling_peak = pv.cummax()
    drawdown = (pv - rolling_peak) / rolling_peak
    max_drawdown = drawdown.min() * 100

    final_price = df["Close"].iloc[-1]
    return {
        "final_position_value": shares * final_price,
        "total_wealth": shares * final_price,
        "cash_extracted": 0.0,
        "max_drawdown_pct": max_drawdown,
        "shares": shares,
        "final_price": final_price,
    }


def main():
    print(f"📊 Fetching {TICKER} {PERIOD_YEARS}-year daily data...")
    df = fetch_data()
    print(f"   {df.index[0].date()} to {df.index[-1].date()} "
          f"({len(df)} rows)")
    print()

    # Baseline
    bh = run_buy_and_hold(df)
    print("━━ Buy & Hold baseline ━━")
    print(f"   Final position: NT${bh['final_position_value']:>12,.0f}")
    print(f"   Total wealth:   NT${bh['total_wealth']:>12,.0f}")
    print(f"   Max drawdown:   {bh['max_drawdown_pct']:>6.1f}%")
    print(f"   x growth:       {bh['final_position_value']/INITIAL_CAPITAL:.2f}x")
    print()

    # Strategy sweep
    sweeps = list(itertools.product(
        [0.30, 0.50, 0.70],   # initial_stock_pct
        [0.005, 0.01, 0.02],  # drop_pct
        [0.005, 0.01, 0.02],  # rise_pct
        [(20_000, 5_000),     # (buy_ntd, sell_ntd) — Ryan's central case
         (10_000, 5_000),
         (20_000, 10_000),
         (10_000, 10_000),    # symmetric reference
         (30_000, 10_000)],
    ))

    print(f"━━ Asymmetric grid sweep ({len(sweeps)} configs) ━━")
    print(f"   {'init':>4} {'drop':>5} {'rise':>5} {'buy':>6} {'sell':>5} | "
          f"{'final_pos':>12} {'extracted':>10} {'wealth':>12} "
          f"{'mdd':>6} {'trades':>6}")
    print("   " + "─" * 100)

    results = []
    for init_pct, dr, rs, (buy, sell) in sweeps:
        if dr != rs and (init_pct, dr, rs) not in [
            (0.30, 0.005, 0.01), (0.30, 0.01, 0.005),
            (0.50, 0.01, 0.005), (0.50, 0.01, 0.02),
            (0.70, 0.01, 0.02),
        ]:
            # only sweep dr != rs at a few representative configs
            continue
        r = run_grid_strategy(
            df,
            initial_stock_pct=init_pct,
            drop_pct=dr,
            rise_pct=rs,
            buy_ntd=buy,
            sell_ntd=sell,
        )
        results.append({
            "init": init_pct, "drop": dr, "rise": rs,
            "buy": buy, "sell": sell, **r,
        })
        print(f"   {init_pct:>4.0%} {dr:>5.1%} {rs:>5.1%} "
              f"{buy:>6,} {sell:>5,} | "
              f"NT${r['final_position_value']:>10,.0f} "
              f"NT${r['cash_extracted']:>8,.0f} "
              f"NT${r['total_wealth']:>10,.0f} "
              f"{r['max_drawdown_pct']:>5.1f}% "
              f"{r['num_trades']:>5}")

    print()
    # ── Mode A: 嚴格賣 — only ATH overheat trim, no grid sell ──
    # Sweep cooldown days too — without cooldown, trim fires every day
    # during a sustained uptrend and erodes position too fast.
    print("━━ Mode A: 嚴格賣（no grid sell, only overheat trim with cooldown） ━━")
    print(f"   {'init':>4} {'drop':>5} {'buy':>6} {'cd':>3} {'trim':>4} {'rsi':>4} | "
          f"{'final_pos':>12} {'extracted':>10} {'wealth':>12} "
          f"{'mdd':>6} {'%B&H':>5}")
    print("   " + "─" * 110)
    a_results = []
    for init_pct in [0.50, 0.70, 1.00]:
        for cd in [0, 10, 30, 90]:
            for trim in [0.01, 0.03, 0.05]:
                for rsi_t in [75, 80]:
                    r = run_grid_strategy(
                        df,
                        initial_stock_pct=init_pct,
                        drop_pct=0.01,
                        rise_pct=0.01,
                        buy_ntd=20_000,
                        sell_ntd=0,
                        grid_sell=False,
                        rsi_thresh=rsi_t,
                        overheat_trim_pct=trim,
                        overheat_cooldown_days=cd,
                    )
                    a_results.append({
                        "mode": "A", "init": init_pct, "drop": 0.01,
                        "buy": 20_000, "cd": cd, "trim": trim, "rsi": rsi_t,
                        **r
                    })
                    pct_bh = r["final_position_value"] / bh["final_position_value"] * 100
                    print(f"   {init_pct:>4.0%} {0.01:>5.1%} "
                          f"{20_000:>6,} {cd:>3} {trim*100:>3.0f}% {rsi_t:>4} | "
                          f"NT${r['final_position_value']:>10,.0f} "
                          f"NT${r['cash_extracted']:>8,.0f} "
                          f"NT${r['total_wealth']:>10,.0f} "
                          f"{r['max_drawdown_pct']:>5.1f}% "
                          f"{pct_bh:>4.0f}%")

    print()
    print("━━ Mode B: 極端不對稱（buy >> sell, e.g. 50:1） ━━")
    print(f"   {'init':>4} {'drop':>5} {'rise':>5} {'buy':>6} {'sell':>5} | "
          f"{'final_pos':>12} {'extracted':>10} {'wealth':>12} "
          f"{'mdd':>6} {'%B&H':>5}")
    print("   " + "─" * 100)
    b_results = []
    for init_pct in [0.30, 0.50]:
        for dr in [0.005, 0.01, 0.02]:
            for rs in [0.01, 0.02, 0.03]:
                for (buy, sell) in [
                    (50_000, 1_000),
                    (50_000, 2_000),
                    (30_000, 1_000),
                    (20_000, 1_000),
                ]:
                    r = run_grid_strategy(
                        df,
                        initial_stock_pct=init_pct,
                        drop_pct=dr,
                        rise_pct=rs,
                        buy_ntd=buy,
                        sell_ntd=sell,
                    )
                    b_results.append({
                        "mode": "B", "init": init_pct, "drop": dr, "rise": rs,
                        "buy": buy, "sell": sell, **r
                    })
                    pct_bh = r["final_position_value"] / bh["final_position_value"] * 100
                    print(f"   {init_pct:>4.0%} {dr:>5.1%} {rs:>5.1%} "
                          f"{buy:>6,} {sell:>5,} | "
                          f"NT${r['final_position_value']:>10,.0f} "
                          f"NT${r['cash_extracted']:>8,.0f} "
                          f"NT${r['total_wealth']:>10,.0f} "
                          f"{r['max_drawdown_pct']:>5.1f}% "
                          f"{pct_bh:>4.0f}%")

    print()
    print("━━ Sweet spot analysis ━━")
    print("   B&H final position is the upper bound. We want strategies that")
    print("   extract substantial cash while keeping ≥85% of B&H final position.\n")

    all_results = (
        [{**r, "mode": "grid"} for r in results]
        + a_results
        + b_results
    )

    print(f"   B&H: position NT${bh['final_position_value']:,.0f}, "
          f"mdd {bh['max_drawdown_pct']:.1f}%\n")

    print("   Top 5 by cash extracted (any mode), keeping ≥ 70% of B&H:")
    target_floor = bh["final_position_value"] * 0.70
    qualified = [
        r for r in all_results if r["final_position_value"] >= target_floor
    ]
    qualified.sort(key=lambda r: -r["cash_extracted"])
    if not qualified:
        print(f"   ⚠️  No config kept ≥70% of B&H position (NT${target_floor:,.0f})")
        print("   Top 5 by cash extracted overall:")
        qualified = sorted(all_results, key=lambda r: -r["cash_extracted"])[:5]
    for r in qualified[:5]:
        retain_pct = r["final_position_value"] / bh["final_position_value"] * 100
        keys = "init {:.0%} drop {:.1%}".format(r["init"], r["drop"])
        if r.get("rise"):
            keys += " rise {:.1%}".format(r["rise"])
        if r.get("buy"):
            keys += " buy {:,}".format(r["buy"])
        if r.get("sell"):
            keys += " sell {:,}".format(r["sell"])
        print(f"   [{r['mode']}] {keys} → "
              f"extracted NT${r['cash_extracted']:,.0f}, "
              f"position {retain_pct:.0f}% of B&H, "
              f"mdd {r['max_drawdown_pct']:.1f}%")

    print()
    print("   Top 5 by total wealth (any mode):")
    by_wealth = sorted(all_results, key=lambda r: -r["total_wealth"])[:5]
    for r in by_wealth:
        retain_pct = r["final_position_value"] / bh["final_position_value"] * 100
        keys = "init {:.0%} drop {:.1%}".format(r["init"], r["drop"])
        if r.get("rise"):
            keys += " rise {:.1%}".format(r["rise"])
        if r.get("buy"):
            keys += " buy {:,}".format(r["buy"])
        if r.get("sell"):
            keys += " sell {:,}".format(r["sell"])
        print(f"   [{r['mode']}] {keys} → "
              f"wealth NT${r['total_wealth']:,.0f}, "
              f"extracted NT${r['cash_extracted']:,.0f}, "
              f"position {retain_pct:.0f}% of B&H")


if __name__ == "__main__":
    main()
