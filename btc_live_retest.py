import requests
import pandas as pd
from datetime import datetime, timezone

SYMBOL = "BTCUSDT"
ASIAN_START = 0
ASIAN_END = 7
SESSION_START_LONDON = 7
SESSION_END_LONDON = 12
SESSION_START_NY = 13
SESSION_END_NY = 17
MIN_RANGE_PCT = 0.003

# Using Bybit API to bypass Binance US IP block (451 Error)
URL = "https://api.bybit.com/v5/market/kline"

def fetch_live_data():
    try:
        params = {
            "category": "linear",
            "symbol": SYMBOL,
            "interval": "15", # 15 minutes directly!
            "limit": 200      # 200 * 15m = 50 hours of data (covers Asian session)
        }
        r = requests.get(URL, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        
        if data["retCode"] != 0:
            print(f"API Error: {data['retMsg']}")
            return None
            
        # Bybit returns klines in descending order. Columns:
        # [start_time, open, high, low, close, volume, turnover]
        df = pd.DataFrame(data["result"]["list"], columns=[
            "open_time","open","high","low","close","volume","turnover"
        ])
        
        df["datetime"] = pd.to_datetime(df["open_time"].astype(int), unit="ms", utc=True)
        for c in ["open","high","low","close","volume"]:
            df[c] = pd.to_numeric(df[c])
            
        # Reverse to chronological order (oldest to newest)
        df = df.iloc[::-1].reset_index(drop=True)
        return df
    except Exception as e:
        print(f"Error fetching data: {e}")
        return None

def check_strategy(df):
    if len(df) < 2: return
    
    state = {}
    # We only evaluate the most recently CLOSED 15m candle (index -2)
    target_i = len(df) - 2
    last_closed = df.iloc[target_i]
    dt = last_closed["datetime"]
    cur_date = dt.date()
    hr = dt.hour

    # Rebuild state day by day up to the target candle
    for i in range(len(df)):
        if i > target_i: break
        row = df.iloc[i]
        row_dt = row["datetime"]
        
        if row_dt.date() != state.get("date"):
            state = {
                "date": row_dt.date(),
                "asian_h": 0.0,
                "asian_l": 9999999.0,
                "bull_broken": False,
                "bear_broken": False,
                "trade_taken": False
            }

        row_hr = row_dt.hour
        if ASIAN_START <= row_hr < ASIAN_END:
            if row["high"] > state["asian_h"]: state["asian_h"] = row["high"]
            if row["low"] < state["asian_l"]: state["asian_l"] = row["low"]
        elif row_hr >= ASIAN_END:
            in_london = SESSION_START_LONDON <= row_hr < SESSION_END_LONDON
            in_ny = SESSION_START_NY <= row_hr < SESSION_END_NY
            if in_london or in_ny:
                if state["asian_h"] > 0 and state["asian_l"] < 9999999.0:
                    range_pct = (state["asian_h"] - state["asian_l"]) / state["asian_l"]
                    if range_pct >= MIN_RANGE_PCT:
                        if not state["bull_broken"] and row["close"] > state["asian_h"]:
                            state["bull_broken"] = True
                        if not state["bear_broken"] and row["close"] < state["asian_l"]:
                            state["bear_broken"] = True

                        if state["bull_broken"] and not state["trade_taken"]:
                            if row["low"] <= state["asian_h"] and row["close"] > state["asian_h"]:
                                state["trade_taken"] = True
                                if i == target_i:
                                    ep = state["asian_h"]
                                    sl = (state["asian_h"] + state["asian_l"]) / 2.0
                                    tp = ep + (state["asian_h"] - state["asian_l"])
                                    print(f"\n[{dt.strftime('%Y-%m-%d %H:%M')} UTC] 🚀 LONG ENTRY SIGNAL 🚀")
                                    print(f"Entry: {ep:.2f} | SL: {sl:.2f} | TP: {tp:.2f}")
                                    return

                        if state["bear_broken"] and not state["trade_taken"]:
                            if row["high"] >= state["asian_l"] and row["close"] < state["asian_l"]:
                                state["trade_taken"] = True
                                if i == target_i:
                                    ep = state["asian_l"]
                                    sl = (state["asian_h"] + state["asian_l"]) / 2.0
                                    tp = ep - (state["asian_h"] - state["asian_l"])
                                    print(f"\n[{dt.strftime('%Y-%m-%d %H:%M')} UTC] 🔻 SHORT ENTRY SIGNAL 🔻")
                                    print(f"Entry: {ep:.2f} | SL: {sl:.2f} | TP: {tp:.2f}")
                                    return

    print(f"[{dt.strftime('%Y-%m-%d %H:%M')} UTC] Checked. No setup triggered.")

if __name__ == "__main__":
    print(f"--- Running 15m Retest Check at {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC ---")
    df = fetch_live_data()
    if df is not None:
        check_strategy(df)
