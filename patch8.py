import re

with open('analyze_ichimoku.py', 'r', encoding='utf-8') as f:
    content = f.read()

target = '''                                    # 바닥권 조건: 지지 구간의 고점이 2년 전체 변동폭의 하위 50% 이내에 있어야 함 (조건 완화)
                                    range_24m = max_high_24m - min_low_24m
                                    bottom_threshold = min_low_24m + (range_24m * 0.50)
                                    is_at_bottom = (base_high <= bottom_threshold)
                                    
                                    # 돌파 조건: 장대양봉의 종가가 지지 구간의 고점을 뚫어내거나 최소 85% 이상 근접해야 함 (조건 완화)
                                    b_candle = df_m.iloc[breakout_idx]
                                    b_close = b_candle['Close'].item() if isinstance(b_candle['Close'], pd.Series) else b_candle['Close']
                                    is_breaking_out = (b_close >= base_high * 0.85)'''

replacement = '''                                    # 바닥권 조건: 최근 4개월 내에 2년 전체 변동폭의 하위 50% 구간(바닥)을 터치했는지 확인 (V자/U자 반등 허용)
                                    range_24m = max_high_24m - min_low_24m
                                    bottom_threshold = min_low_24m + (range_24m * 0.50)
                                    base_low = base_candles['Low'].min()
                                    is_at_bottom = (base_low <= bottom_threshold)
                                    
                                    # 돌파 조건: 장대양봉의 종가가 '직전 달'의 고점을 강하게 돌파(최소 95% 이상 근접)하여 추세를 반전시켰는지 확인
                                    b_candle = df_m.iloc[breakout_idx]
                                    b_close = b_candle['Close'].item() if isinstance(b_candle['Close'], pd.Series) else b_candle['Close']
                                    prev_candle = df_m.iloc[breakout_idx - 1]
                                    prev_high = prev_candle['High'].item() if isinstance(prev_candle['High'], pd.Series) else prev_candle['High']
                                    is_breaking_out = (b_close >= prev_high * 0.95)'''

if target in content:
    content = content.replace(target, replacement)
    with open('analyze_ichimoku.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("V-shape/U-shape monthly pattern constraints updated successfully.")
else:
    print("Failed to find target block in analyze_ichimoku.py")
