import yfinance as yf
import pandas as pd

for ticker in ['ABCL', 'QS', 'QUBT', 'RGTI']:
    df = yf.download(ticker, period='max', interval='1d', progress=False)
    if isinstance(df.columns, pd.MultiIndex): 
        df.columns = df.columns.get_level_values(0)
    try: 
        df_m = df.resample('ME').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()
    except: 
        df_m = df.resample('M').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()
    
    pattern_found = False
    lookback_limit = min(6, len(df_m) - 6)
    
    for i in range(lookback_limit + 1):
        idx = -1 - i
        c_close = df_m['Close'].iloc[idx]
        c_open = df_m['Open'].iloc[idx]
        c_vol = df_m['Volume'].iloc[idx]
        
        p_close = df_m['Close'].iloc[idx-1]
        p_vol = df_m['Volume'].iloc[idx-1]
        
        past_3year_high = df_m['High'].iloc[max(0, len(df_m)-36+idx) : idx].max() if len(df_m[:idx]) > 0 else df_m['High'].max()
        if c_close < past_3year_high * 0.98:
            base_period = min(5, len(df_m[:idx-1]))
            if base_period >= 3:
                base_df = df_m.iloc[idx-1-base_period : idx-1]
                base_low = base_df['Low'].min()
                
                # Check base low is not strictly broken (or close price >= base_low)
                if c_close >= base_low:
                    if c_close > c_open and c_close > p_close:
                        vol_condition = False
                        if i == 0:
                            pp_vol = df_m['Volume'].iloc[-3] if len(df_m) >= 3 else 0
                            if c_vol > p_vol * 0.5 or p_vol > pp_vol:
                                vol_condition = True
                        else:
                            if c_vol > p_vol:
                                vol_condition = True
                                
                        if vol_condition:
                            print(f"{ticker} pattern found at idx {idx} (i={i})")
                            pattern_found = True
                            break
    if not pattern_found:
        print(f"{ticker} NOT FOUND")
