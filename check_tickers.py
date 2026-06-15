# -*- coding: utf-8 -*-
import sys, io
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pickle, pandas as pd

cache = pickle.load(open('stock_data_cache.pkl','rb'))

def get_val(val):
    return val.item() if isinstance(val, pd.Series) else val

# RBLX + 기존 종목 전부 체크
targets = ['RBLX', 'SMR', 'QUBT', 'OKLO']

for sym in targets:
    df = cache['ohlcv'].get(sym)
    if df is None:
        print(f"  {sym}: 캐시 없음")
        continue
    df = df.copy()
    try:
        df_m = df.resample('ME').agg({'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}).dropna()
    except:
        df_m = df.resample('M').agg({'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}).dropna()

    if len(df_m) < 6:
        print(f"  {sym}: 월봉 부족")
        continue

    lookback = min(24, len(df_m))
    hist = df_m.iloc[-lookback:]
    max_h = hist.iloc[:-3]['High'].max() if len(hist) > 3 else hist['High'].max()
    min_l = hist['Low'].min()

    if get_val(max_h) < get_val(min_l) * 1.5:
        print(f"  {sym}: 하락폭 부족")
        continue

    range_24m = get_val(max_h) - get_val(min_l)
    bottom_threshold = get_val(min_l) + (range_24m * 0.50)

    def check_pattern(c_2, c_1, c_0):
        o2, c2 = get_val(c_2['Open']), get_val(c_2['Close'])
        o1, c1 = get_val(c_1['Open']), get_val(c_1['Close'])
        o0, c0 = get_val(c_0['Open']), get_val(c_0['Close'])
        v1, v0 = get_val(c_1['Volume']), get_val(c_0['Volume'])
        pct2 = abs(c2 - o2) / o2 if o2 > 0 else 0
        pct1 = abs(c1 - o1) / o1 if o1 > 0 else 0
        return ((c2<o2) or (pct2<=0.05)) and ((c1<o1) or (pct1<=0.03)) and (c0>o0) and (v0>v1)

    def evaluate_window(c_2, c_1, c_0):
        if check_pattern(c_2, c_1, c_0):
            base_low = min(get_val(c_2['Close']), get_val(c_1['Close']))
            return base_low <= bottom_threshold
        return False

    matched = False
    case = ""

    if len(df_m) >= 3 and evaluate_window(df_m.iloc[-3], df_m.iloc[-2], df_m.iloc[-1]):
        matched = True
        case = "Case1"
    elif len(df_m) >= 4 and evaluate_window(df_m.iloc[-4], df_m.iloc[-3], df_m.iloc[-2]):
        c0_o, c0_c = get_val(df_m.iloc[-2]['Open']), get_val(df_m.iloc[-2]['Close'])
        midpoint = c0_o + (c0_c - c0_o) * 0.5
        t_c = get_val(df_m.iloc[-1]['Close'])
        if t_c >= midpoint:
            matched = True
            case = f"Case2 | 종가={t_c:.2f} >= mid={midpoint:.2f}"
        else:
            case = f"Case2 패턴O→후속X | 종가={t_c:.2f} < mid={midpoint:.2f}"
    elif len(df_m) >= 5 and evaluate_window(df_m.iloc[-5], df_m.iloc[-4], df_m.iloc[-3]):
        c0_o = get_val(df_m.iloc[-3]['Open'])
        t1_c = get_val(df_m.iloc[-2]['Close'])
        if t1_c >= c0_o:
            matched = True
            case = f"Case3 | 지난달={t1_c:.2f} >= 시가={c0_o:.2f}"
        else:
            case = f"Case3 패턴O→후속X | 지난달={t1_c:.2f} < 시가={c0_o:.2f}"
    else:
        case = "패턴 불일치"

    print(f"  {sym}: {'✅ 매칭' if matched else '❌ 탈락'} → {case}")
