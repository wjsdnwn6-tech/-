import re

with open('analyze_ichimoku.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Modify get_top30_us_gainers to return a tuple
content = re.sub(
    r"return \"\\n\"\.join\(report_lines\)\n\s*except Exception as e:",
    r"return \"\\n\".join(report_lines), [info['sym'] for info in top30_info]\n    except Exception as e:",
    content
)

content = re.sub(
    r"return f\"- 미국 시장 분석 중 오류 발생: \{e\}\"",
    r"return f\"- 미국 시장 분석 중 오류 발생: {e}\", []",
    content
)

# 2. Modify execution flow to build templates BEFORE scanning
main_flow_replacement = """    # 당일 상승률 탑 30 분석 및 리포트/데이터 획득
    top30_krx_text, top30_data = get_top30_krx_gainers()
    top30_us_text, top30_us_tickers = get_top30_us_gainers()
    
    krx_top30_tickers = [d['code'] for d in top30_data] if top30_data else []

    if not skip_scan:
        build_top30_templates(krx_top30_tickers, top30_us_tickers)
        for theme_name in THEMES.keys():"""
        
content = re.sub(
    r"    if not skip_scan:\n        for theme_name in THEMES.keys():",
    main_flow_replacement,
    content
)

# remove the old top30 calls at the bottom
content = re.sub(
    r"    # 당일 상승률 탑 30 분석 및 리포트/데이터 획득\n    top30_krx_text, top30_data = get_top30_krx_gainers\(\)\n    top30_us_text = get_top30_us_gainers\(\)\n\n    if not skip_scan:",
    r"    if not skip_scan:",
    content
)

# 3. Add extract_features_for_template and build_top30_templates after global vars
template_code = '''
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
        
        return {
            'w_slope': w_ma20_slope,
            'w_dist': w_distance,
            'w_vol': w_volatility,
            'm_dist': m_distance
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

        return {
            'w_slope': w_ma20_slope,
            'w_dist': w_distance,
            'w_vol': w_volatility,
            'm_dist': m_distance
        }
    except Exception:
        return None

def is_pattern_matched(current_feat, templates):
    if not current_feat or not templates: return False
    
    for t in templates:
        diff_slope = abs(current_feat['w_slope'] - t['w_slope'])
        diff_dist = abs(current_feat['w_dist'] - t['w_dist'])
        diff_vol = abs(current_feat['w_vol'] - t['w_vol'])
        diff_m_dist = abs(current_feat['m_dist'] - t['m_dist'])
        
        if diff_slope < 0.05 and diff_dist < 0.05 and diff_vol < 0.05 and diff_m_dist < 0.10:
            return True
    return False

def build_top30_templates(krx_tickers, us_tickers):
    global TOP30_TEMPLATES
    TOP30_TEMPLATES = []
    print(f"\\n[패턴 스캔 준비] 당일 급등한 상위 종목 {len(krx_tickers) + len(us_tickers)}개의 급등 직전 템플릿 추출 중...")
    
    import datetime
    start_date = (datetime.datetime.now() - datetime.timedelta(days=700)).strftime('%Y-%m-%d')
    
    for code in krx_tickers:
        try:
            df = fdr.DataReader(code, start_date)
            if not df.empty:
                feat = extract_features_for_template(df)
                if feat: TOP30_TEMPLATES.append(feat)
        except Exception:
            pass
            
    if us_tickers:
        try:
            import yfinance as yf
            data = yf.download(us_tickers, period="2y", interval="1d", progress=False, threads=True)
            if isinstance(data.columns, pd.MultiIndex):
                for t in us_tickers:
                    try:
                        if t in data['Close'].columns:
                            df_t = pd.DataFrame({
                                'Open': data['Open'][t],
                                'High': data['High'][t],
                                'Low': data['Low'][t],
                                'Close': data['Close'][t]
                            }).dropna()
                            feat = extract_features_for_template(df_t)
                            if feat: TOP30_TEMPLATES.append(feat)
                    except Exception: pass
            else:
                df_t = data.dropna()
                feat = extract_features_for_template(df_t)
                if feat: TOP30_TEMPLATES.append(feat)
        except Exception:
            pass
            
    print(f"  > 완료: 유의미한 급등 전조 패턴 템플릿 {len(TOP30_TEMPLATES)}개 생성됨.")

'''
content = content.replace('print("[준비 완료]\\n")', 'print("[준비 완료]\\n")\n' + template_code)

# 4. Add pattern matching inside analyze_stocks
pattern_code = '''
            # Top 30 그림자 (급등 전조 패턴) 매칭
            if len(TOP30_TEMPLATES) > 0:
                current_feat = extract_current_features(df)
                if is_pattern_matched(current_feat, TOP30_TEMPLATES):
                    signals.append("top30_pattern_match")
'''
content = re.sub(r'(signals\.append\("200d_bounce"\))', r'\1\n' + pattern_code, content)

with open('analyze_ichimoku.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Patch applied successfully.")
