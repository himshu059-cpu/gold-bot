import csv
import os
import time

from backtest import fetch_candles
from risk import RiskManager


def signal(df, fast, slow):
    c = df["close"]
    f = c.ewm(span=fast, adjust=False).mean().iloc[-1]
    s = c.ewm(span=slow, adjust=False).mean().iloc[-1]
    return 1 if f > s else -1


class PaperBot:
    def __init__(self, equity=1000.0, fast=20, slow=50, stop_loss=0.01,
                 leverage=2.0, fee=0.0005, log="paper_log.csv"):
        self.rm = RiskManager(equity=equity, stop_loss=stop_loss, max_leverage=leverage)
        self.fast, self.slow, self.sl, self.fee = fast, slow, stop_loss, fee
        self.pos, self.entry, self.notional, self.blocked = 0, 0.0, 0.0, 0
        self.log = log
        if not os.path.exists(log):
            with open(log, "w", newline="") as f:
                csv.writer(f).writerow(["time", "event", "side", "price", "pnl_usdt", "equity"])

    def _write(self, ts, event, side, price, pnl=0.0):
        with open(self.log, "a", newline="") as f:
            csv.writer(f).writerow([ts, event, side, round(price, 2), round(pnl, 2), round(self.rm.equity, 2)])
        print(ts, event, "LONG" if side == 1 else "SHORT", round(price, 2),
              "| pnl", round(pnl, 2), "| equity", round(self.rm.equity, 2))

    def _close(self, ts, price, event):
        pnl = self.pos * (price / self.entry - 1) * self.notional - self.notional * self.fee
        self.rm.update_equity(self.rm.equity + pnl)
        self._write(ts, event, self.pos, price, pnl)
        self.pos = 0

    def step(self, df):
        """df me sirf poori ho chuki (closed) candles hon. Har nayi candle par ek baar call karein."""
        ts, last = df.index[-1], df.iloc[-1]
        if self.pos:
            stop = self.entry * (1 - self.sl * self.pos)
            if (self.pos == 1 and last["low"] <= stop) or (self.pos == -1 and last["high"] >= stop):
                side = self.pos
                self._close(ts, stop, "STOP")
                self.blocked = side          # trend flip hone tak dobara entry nahi
        want = signal(df, self.fast, self.slow)
        if want != self.blocked:
            self.blocked = 0
        if self.pos and want != self.pos:
            self._close(ts, last["close"], "EXIT")
        if self.pos == 0 and want != self.blocked:
            ok, why = self.rm.can_trade()
            if ok:
                self.pos, self.entry = want, last["close"]
                self.notional = self.rm.position_size()
                self.rm.update_equity(self.rm.equity - self.notional * self.fee)
                self.rm.record_trade()
                self._write(ts, "ENTRY", want, self.entry)
            else:
                print(ts, "no trade:", why)


def run(pair, resolution="1h", poll=60, max_minutes=60, **kw):
    bot, last_ts, end = PaperBot(**kw), None, time.time() + max_minutes * 60
    print(f"Paper trading shuru: {pair} {resolution} (max {max_minutes} min). Rokne ke liye Colab me stop dabayein.")
    while time.time() < end:
        try:
            df = fetch_candles(pair, resolution, days=15).iloc[:-1]  # aakhri candle abhi chal rahi hai
            if len(df) > bot.slow + 5 and df.index[-1] != last_ts:
                last_ts = df.index[-1]
                bot.step(df)
        except Exception as e:
            print("error:", e)
        time.sleep(poll)
    print("Khatam. Final equity:", round(bot.rm.equity, 2))
