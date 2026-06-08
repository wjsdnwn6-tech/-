# -*- coding: utf-8 -*-
"""최종 검증: 모든 수정 반영 후 SMR/QUBT/OKLO 통과 여부"""
import sys, io
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import pandas as pd
import numpy as np
import pickle
import os

CACHE_FILE = "stock_data_cache.pkl"
targets = ['IONQ', 'SMR', 'QUBT', 'RGTI', 'OKLO']

cache = None
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, "rb") as f:
        cache = pickle.load(f)

def get_val(val):
    return val.item() if isinstance(val, pd.Series) else val

US_MIN_AVG_AMOUNT_FALLBACK = 5_000_000

print("=" * 70)
print("최종 검증 (시가총액 fallback + 불완전 월봉 제외)")
print("=" * 70)

if cache:
    for sym in targets:
        print(f"\n  --- {sym} ---")
        
        df = cache["ohlcv"].get(sym)
        if df is None:
            print(f"    ❌ OHLCV 캐시 없음 → 재다운로드 필요 (누락 종목 재시도 로직으로 해결)")
            continue
        
        df = df.copy()
        
        recent_20d = df.tail(20)
        avg_vol = recent_20d['Volume'].mean()
        avg_price = recent_20d['Close'].mean()
        if isinstance(avg_vol, pd.Series): avg_vol = avg_vol.item()
        if isinstance(avg_price, pd.Series): avg_price = avg_price.item()
        avg_amount = avg_vol * avg_price
        
        market_cap = cache.get("market_caps", {}).get(sym, 0)
        
        # 시가총액 필터 (수정된 로직)
        if market_cap > 0:
            print(f"    시가총액: ${market_cap:,} ✅")
        elif avg_amount >= US_MIN_AVG_AMOUNT_FALLBACK:
            print(f"    시가총액: $0 → 거래대금 ${avg_amount:,.0f}/일 ✅ (fallback 통과)")
        else:
            print(f"    ❌ 시가총액=0 & 거래대금 부족 → 탈락")
            continue
        
        # 월봉 패턴 (최종 수정 로직)
        try:
            df_m = df.resample('ME').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()
        except:
            df_m = df.resample('M').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()
        
        if len(df_m) < 6:
            print(f"    ❌ 월봉 부족")
            continue
        
        lookback = min(24, len(df_m))
        historical_24m = df_m.iloc[-lookback:]
        if len(historical_24m) > 3:
            max_high_24m = historical_24m.iloc[:-3]['High'].max()
        else:
            max_high_24m = historical_24m['High'].max()
        min_low_24m = historical_24m['Low'].min()
        
        if get_val(max_high_24m) < get_val(min_low_24m) * 1.5:
            print(f"    ❌ 하락폭 부족")
            continue
        
        range_24m = get_val(max_high_24m) - get_val(min_low_24m)
        bottom_threshold = get_val(min_low_24m) + (range_24m * 0.50)
        
        def check_pattern(c_2, c_1, c_0):
            o2, c2 = get_val(c_2['Open']), get_val(c_2['Close'])
            o1, c1 = get_val(c_1['Open']), get_val(c_1['Close'])
            o0, c0 = get_val(c_0['Open']), get_val(c_0['Close'])
            v1, v0 = get_val(c_1['Volume']), get_val(c_0['Volume'])
            pct2 = abs(c2 - o2) / o2 if o2 > 0 else 0
            is_t2_valid = (c2 < o2) or (pct2 <= 0.05)
            pct1 = abs(c1 - o1) / o1 if o1 > 0 else 0
            is_t1_exhausted = (c1 < o1) or (pct1 <= 0.03)
            is_t_green = c0 > o0
            is_t_volume_up = v0 > v1
            return is_t2_valid and is_t1_exhausted and is_t_green and is_t_volume_up
        
        def evaluate_window(c_2, c_1, c_0):
            if check_pattern(c_2, c_1, c_0):
                base_low = min(get_val(c_2['Close']), get_val(c_1['Close']))
                if base_low <= bottom_threshold:
                    return True
            return False

        pattern_matched = False
        match_case = ""
        
        # Case 1: 이번 달에 턴어라운드
        if len(df_m) >= 3 and evaluate_window(df_m.iloc[-3], df_m.iloc[-2], df_m.iloc[-1]):
            pattern_matched = True
            match_case = "Case1 (이번달 턴어라운드)"
        
        # Case 2: 지난 달에 턴어라운드 (이번 달 불완전 → 무조건 인정)
        elif len(df_m) >= 4 and evaluate_window(df_m.iloc[-4], df_m.iloc[-3], df_m.iloc[-2]):
            pattern_matched = True
            match_case = "Case2 (지난달 턴어라운드 확정)"
        
        # Case 3: 지지난 달에 턴어라운드 (완성된 지난달 종가만 체크)
        elif len(df_m) >= 5 and evaluate_window(df_m.iloc[-5], df_m.iloc[-4], df_m.iloc[-3]):
            c0_o = get_val(df_m.iloc[-3]['Open'])
            t1_c = get_val(df_m.iloc[-2]['Close'])
            if t1_c >= c0_o:
                pattern_matched = True
                match_case = f"Case3 (지지난달) | 지난달종가={t1_c:.2f} >= 돌파시가={c0_o:.2f}"
            else:
                match_case = f"Case3 패턴O, 후속X | 지난달종가={t1_c:.2f} < 돌파시가={c0_o:.2f}"
        else:
            match_case = "캔들 패턴 불일치"
        
        if pattern_matched:
            print(f"    ✅ 월봉 지지후 상승 패턴 매칭! → {match_case}")
        else:
            print(f"    ❌ 월봉 패턴 미매칭 → {match_case}")

print("\n완료!")
