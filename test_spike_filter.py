import yfinance as yf
import pandas as pd
import numpy as np

stocks = {
    "030610.KS": ("교보증권", "BAD"),
    "030210.KS": ("다올투자증권", "BAD"), 
    "206560.KQ": ("미스트홀딩스", "BAD"),
    "006120.KS": ("SK디스커버리", "BAD"),
    "008930.KS": ("한미사이언스", "BAD"),
}

for ticker, (name, label) in stocks.items():
    try:
        df = yf.download(ticker, period="max", interval="1d", progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)
        
        try:
            df_m = df.resample('ME').agg({'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}).dropna()
        except:
            df_m = df.resample('M').agg({'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}).dropna()
        
        if len(df_m) < 24:
            continue
        
        idx = -1
        pos_idx = len(df_m) + idx
        spike_start = max(0, pos_idx - 24)
        
        c_close = float(df_m['Close'].iloc[idx])
        recent_high = float(df_m['High'].iloc[spike_start:pos_idx].max())
        spike_range_low = float(df_m['Low'].iloc[spike_start:pos_idx].min())
        ratio = recent_high / spike_range_low if spike_range_low > 0 else 0
        
        # 최고점 위치
        high_month_idx = df_m['High'].iloc[spike_start:pos_idx].idxmax()
        high_pos = df_m.index.get_loc(high_month_idx)
        months_since_high = pos_idx - high_pos
        
        # 고점 전 12개월간 최저→최고 상승률
        pre_high_12m = max(0, high_pos - 12)
        pre_low = float(df_m['Low'].iloc[pre_high_12m:high_pos+1].min())
        rise_to_peak = (recent_high / pre_low - 1) * 100 if pre_low > 0 else 0
        
        # 고점 이후 하락 비율
        drop_pct = (1 - c_close / recent_high) * 100
        decline_months = 0
        total_months_after = 0
        if months_since_high >= 3:
            for di in range(high_pos + 1, pos_idx + 1):
                if di < len(df_m) and di > 0:
                    total_months_after += 1
                    if float(df_m['Close'].iloc[di]) < float(df_m['Close'].iloc[di-1]):
                        decline_months += 1
            decline_ratio = decline_months / max(total_months_after, 1)
        else:
            decline_ratio = 0
        
        # ===== 최종 필터 =====
        # 1. H/L > 3배 (극단적 급등)
        f1 = ratio > 3.0
        # 2. 12개월간 급등률 > 80% (강한 급등)  
        f2 = rise_to_peak > 80
        # 3. 하락 지속 패턴 (고점 후 3개월+, 하락월 50%+, 20%+ 하락)
        f3 = months_since_high >= 3 and decline_ratio > 0.50 and drop_pct > 20
        # 4. H/L > 2배 AND 하락 지속 (고점 후 3개월+, 하락 25%+)
        f4 = ratio > 2.0 and months_since_high >= 3 and drop_pct > 25
        
        filtered = f1 or f2 or f3 or f4
        
        print("=" * 60)
        print("[{}] {} ({})".format(label, name, ticker))
        print("  H/L: {:.2f}x | 12M급등: {:.1f}% | 고점후: {}개월 | 하락: {:.1f}% | 하락월: {:.0f}%".format(
            ratio, rise_to_peak, months_since_high, drop_pct, decline_ratio*100))
        print("  F1(H/L>3): {} | F2(급등>80%): {} | F3(하락지속): {} | F4(H/L>2+하락): {}".format(f1, f2, f3, f4))
        print("  >>> {}".format("제거됨" if filtered else "유지"))
        
    except Exception as e:
        print("{}: 오류 - {}".format(name, e))
