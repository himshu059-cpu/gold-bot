import time

import pandas as pd
import streamlit as st

from backtest import backtest, fetch_candles
from paper import PaperBot, signal

st.set_page_config(page_title="Gold Bot", layout="wide")
st.title("Gold Bot (paper trading)")
st.caption("Sirf nakli trades aur signals. Isme asli order nahi jaata, aur ye trading ki salah nahi hai.")

with st.sidebar:
    pair = st.text_input("Pair", "B-XAU_USDT")
    resolution = st.selectbox("Timeframe", ["15m", "1h", "4h"], index=1)
    fast = st.number_input("Fast EMA", min_value=2, max_value=200, value=20, step=1)
    slow = st.number_input("Slow EMA", min_value=5, max_value=400, value=50, step=1)
    leverage = st.slider("Leverage", 1.0, 5.0, 2.0, 0.5)
    stop = st.slider("Stop-loss (%)", 0.2, 5.0, 1.0, 0.1) / 100
    capital = st.number_input("Paper capital (USDT)", min_value=100.0, value=1000.0, step=100.0)
    days = st.slider("Data (days)", 15, 180, 60)
    auto = st.checkbox("Auto refresh (60 sec)")

if slow <= fast:
    st.error("Slow EMA, Fast EMA se bada hona chahiye.")
    st.stop()


@st.cache_data(ttl=60)
def load(pair, resolution, days):
    return fetch_candles(pair, resolution, days)


try:
    df = load(pair, resolution, days)
except Exception as e:
    st.error(f"Data nahi mila: {e}. Pair ka naam aur timeframe check karein.")
    st.stop()

if len(df) < slow + 10:
    st.error("Data kam hai. Sidebar me Data (days) badhayein.")
    st.stop()

closed = df.iloc[:-1]  # aakhri candle abhi chal rahi hai, isliye hata di

tab1, tab2, tab3 = st.tabs(["Signal", "Backtest", "Paper trades"])

with tab1:
    sig = signal(closed, int(fast), int(slow))
    c1, c2, c3 = st.columns(3)
    c1.metric("Signal", "LONG" if sig == 1 else "SHORT")
    c2.metric("Abhi ka price", f"{df['close'].iloc[-1]:,.2f}")
    c3.metric("Aakhri closed candle", str(closed.index[-1]))
    chart = pd.DataFrame({
        "price": closed["close"],
        f"EMA{fast}": closed["close"].ewm(span=int(fast), adjust=False).mean(),
        f"EMA{slow}": closed["close"].ewm(span=int(slow), adjust=False).mean(),
    })
    st.line_chart(chart.tail(300))
    st.caption("LONG = fast EMA upar, SHORT = fast EMA neeche. Ye sirf strategy ka output hai.")

with tab2:
    if st.button("Backtest chalao"):
        res = backtest(df, int(fast), int(slow), leverage, 0.0005, stop, capital)
        st.table(pd.DataFrame(res, index=["value"]).T)
        st.warning("Backtest ka achha result future me kamai ki guarantee nahi hai.")

with tab3:
    cfg = (pair, resolution, fast, slow, leverage, stop, capital)
    ss = st.session_state
    if ss.get("cfg") != cfg:
        ss.cfg, ss.last_ts = cfg, None
        ss.log = f"paper_log_{int(time.time())}.csv"
        ss.bot = PaperBot(capital, int(fast), int(slow), stop, leverage, 0.0005, log=ss.log)
    if closed.index[-1] != ss.last_ts:
        ss.last_ts = closed.index[-1]
        ss.bot.step(closed)
    b = ss.bot
    c1, c2, c3 = st.columns(3)
    c1.metric("Equity (USDT)", f"{b.rm.equity:,.2f}")
    c2.metric("Position", {1: "LONG", -1: "SHORT", 0: "Koi nahi"}[b.pos])
    c3.metric("Entry price", f"{b.entry:,.2f}" if b.pos else "-")
    ok, why = b.rm.can_trade()
    if not ok:
        st.warning(f"Bot abhi trade nahi karega: {why}")
    try:
        st.dataframe(pd.read_csv(ss.log).iloc[::-1])
    except Exception:
        st.info("Abhi koi trade nahi hui.")
    st.caption("Ye bot sirf tab nayi candle dekhta hai jab app khula ho.")
    if st.button("Reset paper bot"):
        ss.cfg = None
        st.rerun()

if auto:
    time.sleep(60)
    st.rerun()
