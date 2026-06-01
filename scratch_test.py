import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from analyze_ichimoku import get_top70_krx_gainers, get_top70_us_gainers, extract_features_for_template, extract_current_features
import FinanceDataReader as fdr
import datetime
import yfinance as yf

krx_text, krx_data = get_top70_krx_gainers()
krx_top = [t['code'] for t in krx_data][:70] if krx_data else []

us_text, us_data = get_top70_us_gainers()
us_top = us_data[:70] if us_data else []

templates = []
start_date = (datetime.datetime.now() - datetime.timedelta(days=700)).strftime('%Y-%m-%d')

for code in krx_top:
    try:
        df = fdr.DataReader(code, start_date)
        if not df.empty:
            feat = extract_features_for_template(df)
            if feat:
                feat['ticker'] = code
                templates.append(feat)
    except: pass

print(f"KRX Templates: {len(templates)}")

for code in us_top:
    try:
        df = yf.download(code, start=start_date, progress=False)
        if not df.empty:
            feat = extract_features_for_template(df)
            if feat:
                feat['ticker'] = code
                templates.append(feat)
    except: pass

print(f"Total Templates: {len(templates)}")

target_tickers = ['023160', '000370', '003380', '117730', '211270']
for ticker in target_tickers:
    try:
        df = fdr.DataReader(ticker, start_date)
        feat = extract_current_features(df)
        if not feat: continue
        
        matches = []
        for t in templates:
            diff_slope = abs(feat['w_slope'] - t['w_slope'])
            diff_dist = abs(feat['w_dist'] - t['w_dist'])
            diff_vol = abs(feat['w_vol'] - t['w_vol'])
            diff_m_dist = abs(feat['m_dist'] - t['m_dist'])
            if diff_slope < 0.05 and diff_dist < 0.05 and diff_vol < 0.05 and diff_m_dist < 0.10:
                matches.append(t['ticker'])
        print(f"RESULT: {ticker} matched with: {matches}")
    except Exception as e:
        print(f"Error for {ticker}: {e}")
