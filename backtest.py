"""
Step 1: EMA crossover backtester (XAU-USDT / PAXG-USDT / BTC etc.)

Run examples:
  python backtest.py --demo                       # fake data, sirf code test karne ke liye
  python backtest.py --csv xau.csv                # apna CSV (columns: time,open,high,low,close,volume)
  python backtest.py --pair B-XAU_USDT --days 90  # CoinDCX se live candles (symbol verify karein!)

Install:  pip install pandas numpy requests
NOTE: Ye sirf research tool hai. Isme order place karne ka code nahi hai.
"""
import argparse
import time

import numpy as np
import pandas as pd

# CoinDCX public candle endpoint. Format/symbol docs se verify karein:
# https://docs.coindcx.com  (futures pair ka exact naam active instruments list se lein)
CANDLE_URL = "https://public.coindcx.com/market_data/candlesticks"


def fetch_candles(pair, resolution="1h", days=90):
    import requests

    to_ms = int(time.time() * 1000)
    from_ms = to_ms - days * 24 * 3600 * 1000
    r = requests.get(
        CANDLE_URL,
        params={"pair": pair, "from": from_ms, "to": to_ms,
                "resolution": resolution, "pcode": "f"},
        timeout=20,
    )
    r.raise_for_status()
    data = r.json()
    rows = data["data"] if isinstance(data, dict) and "data" in data else data
    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["time"], unit="ms")
    df = df.set_index("time").sort_index()
    return df[["open", "high", "low", "close", "volume"]].astype(float)


def load_csv(path):
    df = pd.read_csv(path, parse_dates=["time"]).set_index("time").sort_index()
    return df[["open", "high", "low", "close", "volume"]].astype(float)


def demo_data(n=3000, seed=7):
    rng = np.random.default_rng(seed)
    drift = np.repeat(rng.normal(0, 0.0004, n // 200 + 1), 200)[:n]  # trend regimes
    ret = drift + rng.normal(0, 0.003, n)
    close = 2000 * np.exp(np.cumsum(ret))
    open_ = np.r_[close[0], close[:-1]]
    spread = np.abs(rng.normal(0, 0.002, n)) * close
    idx = pd.date_range("2026-01-01", periods=n, freq="h")
    return pd.DataFrame({"open": open_, "high": np.maximum(open_, close) + spread,
                         "low": np.minimum(open_, close) - spread,
                         "close": close, "volume": 1.0}, index=idx)


def exit_trade(equity, pos, entry, price, lev, fee):
    gross = max(0.0, 1 + pos * (price / entry - 1) * lev)  # 0 = liquidation
    return equity * gross * (1 - fee * lev)


def backtest(df, fast=20, slow=50, leverage=2.0, fee=0.0005, stop_loss=0.01,
             equity0=1000.0):
    close = df["close"]
    sig = np.where(close.ewm(span=fast, adjust=False).mean()
                   > close.ewm(span=slow, adjust=False).mean(), 1, -1)
    o, h, l, c = (df[k].to_numpy() for k in ("open", "high", "low", "close"))

    equity, pos, entry, trade_start, blocked = equity0, 0, 0.0, equity0, 0
    curve, trades = [], []

    for i in range(slow, len(df)):
        want = sig[i - 1]  # signal pichli candle ke close par, entry agli candle ke open par
        if want != blocked:
            blocked = 0
        if pos != 0 and want != pos:
            equity = exit_trade(equity, pos, entry, o[i], leverage, fee)
            trades.append(equity / trade_start - 1)
            pos = 0
        if pos == 0 and want != blocked:
            pos, entry, trade_start = want, o[i], equity
            equity *= 1 - fee * leverage
        if pos != 0:
            stop = entry * (1 - stop_loss * pos)
            if (pos == 1 and l[i] <= stop) or (pos == -1 and h[i] >= stop):
                equity = exit_trade(equity, pos, entry, stop, leverage, fee)
                trades.append(equity / trade_start - 1)
                blocked, pos = pos, 0  # stop ke baad trend flip hone tak wait
        mtm = equity * max(0.0, 1 + pos * (c[i] / entry - 1) * leverage) if pos else equity
        curve.append(mtm)

    if pos != 0:
        equity = exit_trade(equity, pos, entry, c[-1], leverage, fee)
        trades.append(equity / trade_start - 1)
        curve[-1] = equity

    curve = np.array(curve)
    peak = np.maximum.accumulate(curve)
    return {
        "final_equity": round(equity, 2),
        "return_%": round((equity / equity0 - 1) * 100, 2),
        "buy_hold_%": round((c[-1] / c[slow] - 1) * 100, 2),
        "max_drawdown_%": round(((curve / peak) - 1).min() * 100, 2),
        "trades": len(trades),
        "win_rate_%": round(100 * np.mean(np.array(trades) > 0), 1) if trades else 0,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--pair", default="B-XAU_USDT")
    p.add_argument("--resolution", default="1h")
    p.add_argument("--days", type=int, default=90)
    p.add_argument("--csv")
    p.add_argument("--demo", action="store_true")
    p.add_argument("--fast", type=int, default=20)
    p.add_argument("--slow", type=int, default=50)
    p.add_argument("--leverage", type=float, default=2.0)
    p.add_argument("--fee", type=float, default=0.0005, help="per side, 0.0005 = 0.05%%")
    p.add_argument("--stop", type=float, default=0.01, help="0.01 = 1%% price move")
    a = p.parse_args()

    data = demo_data() if a.demo else load_csv(a.csv) if a.csv else \
        fetch_candles(a.pair, a.resolution, a.days)
    print(f"Candles: {len(data)}  ({data.index[0]} -> {data.index[-1]})")
    for k, v in backtest(data, a.fast, a.slow, a.leverage, a.fee, a.stop).items():
        print(f"{k:>16}: {v}")
