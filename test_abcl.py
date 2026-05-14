import yfinance as yf
import pandas as pd

ticker = "ABCL"
df = yf.download(ticker, period="max", interval="1d", progress=False)

if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.droplevel(1)

try:
    df_m = df.resample('ME').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()
except Exception:
    df_m = df.resample('M').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()

pattern_found = False
lookback_limit = min(2, len(df_m) - 12)

print(f"Total months: {len(df_m)}, Lookback limit: {lookback_limit}")

if lookback_limit >= 0:
    for i in range(lookback_limit + 1):
        idx = -1 - i
        
        c_close = df_m['Close'].iloc[idx].item() if isinstance(df_m['Close'].iloc[idx], pd.Series) else df_m['Close'].iloc[idx]
        c_open = df_m['Open'].iloc[idx].item() if isinstance(df_m['Open'].iloc[idx], pd.Series) else df_m['Open'].iloc[idx]
        c_vol = df_m['Volume'].iloc[idx].item() if isinstance(df_m['Volume'].iloc[idx], pd.Series) else df_m['Volume'].iloc[idx]
        
        past_high = df_m['High'].iloc[:idx].max() if len(df_m[:idx]) > 0 else df_m['High'].max()
        past_high_val = past_high.item() if isinstance(past_high, pd.Series) else past_high
        
        base_period = 6
        if len(df_m[:idx]) >= base_period:
            base_df = df_m.iloc[idx-base_period : idx]
            base_low = base_df['Low'].min()
            base_avg_vol = base_df['Volume'].mean()
            
            base_low_val = base_low.item() if isinstance(base_low, pd.Series) else base_low
            base_avg_vol_val = base_avg_vol.item() if isinstance(base_avg_vol, pd.Series) else base_avg_vol
            
            print(f"Month idx={idx}: Close={c_close:.2f}, High={past_high_val:.2f}, Base Low={base_low_val:.2f}, Vol={c_vol}, Avg Vol={base_avg_vol_val}")
            
            if past_high_val >= base_low_val * 2.5:
                if c_close >= base_low_val:
                    if c_close > c_open * 1.15 or c_close > base_low_val * 1.3:
                        if c_vol > base_avg_vol_val * 1.0:
                            if c_close > c_open and c_close > df_m['Close'].iloc[idx-1]:
                                pattern_found = True
                                print(f"==> PATTERN FOUND for {ticker} at idx {idx}!")
                                break

if not pattern_found:
    print(f"Pattern NOT found for {ticker}")
