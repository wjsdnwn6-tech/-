import re

with open('analyze_ichimoku.py', 'r', encoding='utf-8') as f:
    content = f.read()

replacement = '''
# ============================================================
# 급등주 선행 패턴 (Top 30 그림자) 추출 및 매칭 로직
# ============================================================
TOP30_TEMPLATES = []

def extract_features_for_template(df):
    try:
        if len(df) < 120: return None
        # 최근 급등 캔들(당일) 제외
        df_past = df.iloc[:-1].copy()
        
        # 주봉 변환
        df_w = df_past.resample('W').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()
        if len(df_w) < 20: return None
        
        df_w['ma20'] = df_w['Close'].rolling(window=20).mean()
        df_w = df_w.dropna()
        if len(df_w) < 4: return None
        
        w_ma20_slope = (df_w['ma20'].iloc[-1] - df_w['ma20'].iloc[-4]) / df_w['ma20'].iloc[-4]
        w_distance = (df_w['Close'].iloc[-1] - df_w['ma20'].iloc[-1]) / df_w['ma20'].iloc[-1]
        w_volatility = (df_w['High'].iloc[-4:].max() - df_w['Low'].iloc[-4:].min()) / df_w['ma20'].iloc[-1]
        
        # 월봉 변환
        df_m = df_past.resample('ME').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()
        m_distance = 0
        if len(df_m) >= 20:
            df_m['ma20'] = df_m['Close'].rolling(window=20).mean()
            df_m = df_m.dropna()
            if len(df_m) > 0:
                m_distance = (df_m['Close'].iloc[-1] - df_m['ma20'].iloc[-1]) / df_m['ma20'].iloc[-1]
        
        # 60일 종가 차트 궤적 정규화 (Shape)
        recent_60_closes = df_past['Close'].tail(60).values
        if len(recent_60_closes) == 60:
            mean = recent_60_closes.mean()
            std = recent_60_closes.std()
            if std == 0: std = 1
            shape_array = (recent_60_closes - mean) / std
        else:
            shape_array = None

        return {
            'w_slope': w_ma20_slope,
            'w_dist': w_distance,
            'w_vol': w_volatility,
            'm_dist': m_distance,
            'shape': shape_array
        }
    except Exception:
        return None

def extract_current_features(df):
    try:
        if len(df) < 120: return None
        df_w = df.resample('W').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()
        if len(df_w) < 20: return None
        
        df_w['ma20'] = df_w['Close'].rolling(window=20).mean()
        df_w = df_w.dropna()
        if len(df_w) < 4: return None
        
        w_ma20_slope = (df_w['ma20'].iloc[-1] - df_w['ma20'].iloc[-4]) / df_w['ma20'].iloc[-4]
        w_distance = (df_w['Close'].iloc[-1] - df_w['ma20'].iloc[-1]) / df_w['ma20'].iloc[-1]
        w_volatility = (df_w['High'].iloc[-4:].max() - df_w['Low'].iloc[-4:].min()) / df_w['ma20'].iloc[-1]
        
        df_m = df.resample('ME').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()
        m_distance = 0
        if len(df_m) >= 20:
            df_m['ma20'] = df_m['Close'].rolling(window=20).mean()
            df_m = df_m.dropna()
            if len(df_m) > 0:
                m_distance = (df_m['Close'].iloc[-1] - df_m['ma20'].iloc[-1]) / df_m['ma20'].iloc[-1]

        # 60일 종가 차트 궤적 정규화 (Shape)
        recent_60_closes = df['Close'].tail(60).values
        if len(recent_60_closes) == 60:
            mean = recent_60_closes.mean()
            std = recent_60_closes.std()
            if std == 0: std = 1
            shape_array = (recent_60_closes - mean) / std
        else:
            shape_array = None

        return {
            'w_slope': w_ma20_slope,
            'w_dist': w_distance,
            'w_vol': w_volatility,
            'm_dist': m_distance,
            'shape': shape_array
        }
    except Exception:
        return None

def is_pattern_matched(current_feat, templates):
    """
    조건 매칭(옵션 B)과 모양 매칭(옵션 A) 결과를 튜플로 반환합니다.
    return (is_condition_match, is_shape_match)
    """
    if not current_feat or not templates: return False, False
    
    cond_match = False
    shape_match = False
    
    import numpy as np

    for t in templates:
        # 1. 조건 매칭 (옵션 B)
        if not cond_match:
            diff_slope = abs(current_feat['w_slope'] - t['w_slope'])
            diff_dist = abs(current_feat['w_dist'] - t['w_dist'])
            diff_vol = abs(current_feat['w_vol'] - t['w_vol'])
            diff_m_dist = abs(current_feat['m_dist'] - t['m_dist'])
            
            if diff_slope < 0.05 and diff_dist < 0.05 and diff_vol < 0.05 and diff_m_dist < 0.10:
                cond_match = True

        # 2. 모양 매칭 (옵션 A - 피어슨 상관계수 연산)
        if not shape_match and current_feat['shape'] is not None and t['shape'] is not None:
            # 두 배열은 평균 0, 표준편차 1로 정규화되어 있으므로 내적 후 N으로 나누면 Pearson Correlation이 됨
            corr = np.dot(current_feat['shape'], t['shape']) / 60.0
            if corr > 0.90:  # 90% 이상 일치
                shape_match = True

        if cond_match and shape_match:
            break

    return cond_match, shape_match
'''

# Find the block to replace
start_idx = content.find("# ============================================================\n# 급등주 선행 패턴 (Top 30 그림자) 추출 및 매칭 로직\n# ============================================================")
end_idx = content.find("def build_top30_templates(krx_tickers, us_tickers):")

if start_idx != -1 and end_idx != -1:
    content = content[:start_idx] + replacement + content[end_idx:]
    with open('analyze_ichimoku.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Function replaced.")
else:
    print("Could not find block.")
