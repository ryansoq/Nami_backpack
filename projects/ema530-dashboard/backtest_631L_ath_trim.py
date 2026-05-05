#!/usr/bin/env python3
"""
Backtest: 00631L.TW ATH + RSI + ADX trim-on-overheat strategy

Context
-------
Ryan needs to withdraw cash from this position periodically to live on and
buy tokens. He is NOT trying to beat buy-and-hold on paper — he knows B&H
wins that. He needs to know:

  "Given I MUST withdraw at overheat points, what trim % lets me take the
   most money out over time WITHOUT shrinking the underlying position?"

So cash is CONSUMED, not held. The metric we care about is:
  1. Is the remaining position value at the end still ≥ initial? (principal
     preserved — the "principal shrinking" concern Ryan mentioned)
  2. How much total cash got withdrawn? (lifetime income)
  3. Growth multiple: final_position_value / initial_position_value
     (ideally ≥ 1 meaning the stock position didn't shrink)

Grid searches (rsi_threshold, adx_threshold, trim_pct, cooldown_days).
"""
import sys
import math
import itertools
import yfinance as yf
import pandas as pd


def adjust_for_splits(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Same logic as generate_data.py — detects >50% single-day drops as
    splits yfinance missed and divides earlier OHLC by the inferred ratio."""
    close = df['Close'].squeeze().dropna()
    if len(close) < 2:
        return df
    pct = close.pct_change()
    suspects = pct[pct < -0.5]
    if suspects.empty:
        return df
    adjusted = df.copy()
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
        print(f"  [split] {ticker} {date.date()}: ratio {ratio:.2f}:1", file=sys.stderr)
    return adjusted


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def compute_adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(span=period, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(span=period, adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(span=period, adjust=False).mean() / atr)
    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di))
    return dx.ewm(span=period, adjust=False).mean()


def simulate(df: pd.DataFrame, rsi_thresh: float, adx_thresh: float,
             trim_pct: float, cooldown_days: int) -> dict:
    """Run the withdraw-on-overheat strategy.

    Starts with 1.0 share, no cash. When trigger fires, trim trim_pct of
    CURRENT shares and WITHDRAW the proceeds (consumed, not retained as
    cash). Tracks shares over time and accumulates total withdrawn.
    """
    shares = 1.0
    total_withdrawn = 0.0
    ath = 0.0
    last_trim_idx = -10**9
    trims = []

    initial_price = df['Close'].iloc[0]
    initial_value = 1.0 * initial_price  # the "principal" reference

    for i, (date, row) in enumerate(df.iterrows()):
        close = row['Close']
        rsi = row['RSI']
        adx = row['ADX']

        if close > ath:
            ath = close
            new_ath = True
        else:
            new_ath = False

        if (new_ath and pd.notna(rsi) and pd.notna(adx)
                and rsi >= rsi_thresh and adx >= adx_thresh
                and (i - last_trim_idx) >= cooldown_days):
            trim_shares = shares * trim_pct
            withdrawn = trim_shares * close
            total_withdrawn += withdrawn
            shares -= trim_shares
            last_trim_idx = i
            trims.append({
                "date": date, "price": close, "rsi": rsi, "adx": adx,
                "withdrawn": withdrawn, "shares_after": shares,
                "position_value_after": shares * close,
            })

    final_price = df['Close'].iloc[-1]
    final_position_value = shares * final_price
    years = (df.index[-1] - df.index[0]).days / 365.25

    # Principal growth: did the stock position grow despite the withdrawals?
    principal_mult = final_position_value / initial_value
    principal_cagr = principal_mult ** (1 / years) - 1 if years > 0 else 0

    return {
        "rsi_thresh": rsi_thresh,
        "adx_thresh": adx_thresh,
        "trim_pct": trim_pct,
        "cooldown": cooldown_days,
        "n_trims": len(trims),
        "initial_value": initial_value,
        "final_position_value": final_position_value,
        "final_shares": shares,
        "total_withdrawn": total_withdrawn,
        "principal_mult": principal_mult,
        "principal_cagr": principal_cagr,
        "principal_preserved": final_position_value >= initial_value,
        "withdrawn_vs_initial": total_withdrawn / initial_value,
        "trims": trims,
    }


def main():
    print("📥 Fetching 00631L.TW (max history)...", file=sys.stderr)
    df = yf.download("00631L.TW", period="max", progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna(subset=['Close'])
    df = adjust_for_splits(df, "00631L.TW")

    close = df['Close']
    df['RSI'] = compute_rsi(close, 14)
    df['ADX'] = compute_adx(df['High'], df['Low'], close, 14)

    # Drop rows where indicators aren't ready yet
    df = df.dropna(subset=['RSI', 'ADX'])

    print(f"  Data: {len(df)} rows, {df.index[0].date()} → {df.index[-1].date()}", file=sys.stderr)
    print(f"  Years: {(df.index[-1] - df.index[0]).days / 365.25:.1f}", file=sys.stderr)
    print(f"  Initial: {df['Close'].iloc[0]:.2f}", file=sys.stderr)
    print(f"  Final:   {df['Close'].iloc[-1]:.2f}", file=sys.stderr)
    print(f"  ATH:     {df['Close'].max():.2f}", file=sys.stderr)

    rsi_grid = [60, 65, 70, 75]
    adx_grid = [25, 30, 35, 40, 50]
    # Fine-grained around Ryan's 3-7% zone of interest
    trim_grid = [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.10]
    cooldown_grid = [0, 5, 10, 30]

    results = []
    for rsi_t, adx_t, trim, cd in itertools.product(
        rsi_grid, adx_grid, trim_grid, cooldown_grid
    ):
        r = simulate(df, rsi_t, adx_t, trim, cd)
        results.append(r)

    # Primary sort: principal preserved first, then total withdrawn descending
    # (the goal is "squeeze the most cash out without shrinking the pot")
    results.sort(
        key=lambda r: (r['principal_preserved'], r['total_withdrawn']),
        reverse=True,
    )

    bh_final = df['Close'].iloc[-1]
    bh_initial = df['Close'].iloc[0]
    years = (df.index[-1] - df.index[0]).days / 365.25

    print()
    print("=" * 90)
    print("BACKTEST — 00631L.TW withdraw-on-overheat (cash CONSUMED for living expenses)")
    print("=" * 90)
    print(f"\nContext: Ryan MUST pull cash out of this position periodically.")
    print(f"Question: which trim % maximizes total withdrawn while keeping")
    print(f"          the remaining position value ≥ initial position value?")
    print()
    print(f"Buy-and-Hold reference (NOT the benchmark — cash is consumed):")
    print(f"  Initial price : {bh_initial:.4f}")
    print(f"  Final price   : {bh_final:.4f}")
    print(f"  B&H multiple  : {bh_final/bh_initial:.2f}x  over {years:.1f} years")
    print(f"  Meaning: if Ryan withdraws NOTHING, 1 unit → {bh_final/bh_initial:.2f} units")

    # TOP 20 — ranked by total_withdrawn among principal-preserving combos
    print(f"\nTop 20 combos (principal_preserved first, then most-cash-withdrawn):")
    print(f"{'#':<3} {'RSI':>4} {'ADX':>4} {'Trim':>5} {'CD':>4} {'Trims':>6} "
          f"{'Withdrawn':>11} {'FinalPos':>10} {'PrincMult':>10} {'Preserved':>10}")
    print("-" * 90)
    for i, r in enumerate(results[:20]):
        mark = "✓" if r['principal_preserved'] else "✗"
        print(f"{i+1:<3} {r['rsi_thresh']:>4.0f} {r['adx_thresh']:>4.0f} "
              f"{r['trim_pct']*100:>4.0f}% {r['cooldown']:>4} {r['n_trims']:>6} "
              f"{r['total_withdrawn']:>11.4f} {r['final_position_value']:>10.4f} "
              f"{r['principal_mult']:>9.2f}x {mark:>10}")

    # Zoom: fix best RSI/ADX/cooldown, sweep trim_pct (Ryan's real question)
    best = results[0]
    print()
    print("-" * 90)
    print(f"Trim-size sweep @ RSI≥{best['rsi_thresh']:.0f}, ADX≥{best['adx_thresh']:.0f}, "
          f"cooldown={best['cooldown']}d:")
    print(f"{'Trim':>5} {'Trims':>6} {'Withdrawn':>11} {'W/Initial':>10} "
          f"{'FinalPos':>10} {'PrincMult':>10} {'PrincCAGR':>10} {'Preserved':>10}")
    print("-" * 90)
    for trim in trim_grid:
        r = [x for x in results
             if x['rsi_thresh'] == best['rsi_thresh']
             and x['adx_thresh'] == best['adx_thresh']
             and x['cooldown'] == best['cooldown']
             and x['trim_pct'] == trim][0]
        mark = "✓" if r['principal_preserved'] else "✗ SHRINKS"
        print(f"{trim*100:>4.0f}% {r['n_trims']:>6} "
              f"{r['total_withdrawn']:>11.4f} {r['withdrawn_vs_initial']:>9.2f}x "
              f"{r['final_position_value']:>10.4f} {r['principal_mult']:>9.2f}x "
              f"{r['principal_cagr']*100:>9.2f}% {mark:>10}")

    # Find the flip point: the largest trim % where principal is still preserved
    print()
    print("-" * 90)
    print("Break-even analysis: at what trim % does principal start shrinking?")
    print(f"(Fixed RSI≥{best['rsi_thresh']:.0f}, ADX≥{best['adx_thresh']:.0f}, "
          f"cooldown={best['cooldown']}d)")
    preserved_trims = sorted([
        x['trim_pct'] for x in results
        if x['rsi_thresh'] == best['rsi_thresh']
        and x['adx_thresh'] == best['adx_thresh']
        and x['cooldown'] == best['cooldown']
        and x['principal_preserved']
    ])
    shrink_trims = sorted([
        x['trim_pct'] for x in results
        if x['rsi_thresh'] == best['rsi_thresh']
        and x['adx_thresh'] == best['adx_thresh']
        and x['cooldown'] == best['cooldown']
        and not x['principal_preserved']
    ])
    if preserved_trims:
        print(f"  Principal still grows at: "
              f"{', '.join(f'{t*100:.0f}%' for t in preserved_trims)}")
    if shrink_trims:
        print(f"  Principal shrinks at    : "
              f"{', '.join(f'{t*100:.0f}%' for t in shrink_trims)}")
    if preserved_trims and shrink_trims:
        max_safe = max(preserved_trims)
        min_shrink = min(shrink_trims)
        print(f"  → Safe ceiling: {max_safe*100:.0f}% "
              f"(next step up {min_shrink*100:.0f}% starts eroding principal)")

    # Sweep ALL RSI/ADX combos, fixed cooldown=30, to find the global principal-preserving sweet spot
    print()
    print("-" * 90)
    print("Global sweet spot (principal-preserved combos with MAX total_withdrawn):")
    preserved = [r for r in results if r['principal_preserved']]
    preserved.sort(key=lambda r: r['total_withdrawn'], reverse=True)
    print(f"{'RSI':>4} {'ADX':>4} {'Trim':>5} {'CD':>4} {'Trims':>6} "
          f"{'Withdrawn':>11} {'FinalPos':>10} {'PrincMult':>10}")
    print("-" * 90)
    for r in preserved[:10]:
        print(f"{r['rsi_thresh']:>4.0f} {r['adx_thresh']:>4.0f} "
              f"{r['trim_pct']*100:>4.0f}% {r['cooldown']:>4} {r['n_trims']:>6} "
              f"{r['total_withdrawn']:>11.4f} {r['final_position_value']:>10.4f} "
              f"{r['principal_mult']:>9.2f}x")

    print()
    print("-" * 90)
    print("Best combo trim events (first 10):")
    for t in results[0]['trims'][:10]:
        print(f"  {t['date'].date()}: close={t['price']:.2f} "
              f"RSI={t['rsi']:.1f} ADX={t['adx']:.1f} "
              f"withdrawn={t['withdrawn']:.4f} shares_after={t['shares_after']:.4f}")
    if len(results[0]['trims']) > 10:
        print(f"  ... and {len(results[0]['trims']) - 10} more")


if __name__ == "__main__":
    main()
