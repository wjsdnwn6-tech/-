import yfinance as yf
import pandas as pd
import numpy as np
import sys
import io
import FinanceDataReader as fdr
import requests
import json
import datetime
import os
import argparse

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# ============================================================
# 전역 캐시: 시작 시 한 번만 로드
# ============================================================
print("[준비] 시장 데이터를 로드 중입니다...")

# KRX: 가격/시총 정보
try:
    DF_KRX_PRICE = fdr.StockListing('KRX')
    KRX_CAP_MAP = dict(zip(DF_KRX_PRICE['Code'], DF_KRX_PRICE['Marcap']))
    print(f" > KRX 시세 데이터 {len(DF_KRX_PRICE)}개 종목 로드 완료.")
except:
    DF_KRX_PRICE = pd.DataFrame()
    KRX_CAP_MAP = {}

# KRX-DESC: 업종/산업 정보 (Sector, Industry 컬럼 포함)
try:
    DF_KRX_DESC = fdr.StockListing('KRX-DESC')
    print(f" > KRX 업종 데이터 {len(DF_KRX_DESC)}개 종목 로드 완료.")
except:
    DF_KRX_DESC = pd.DataFrame()

# NASDAQ
try:
    DF_NASDAQ = fdr.StockListing('NASDAQ')
    print(f" > NASDAQ 데이터 {len(DF_NASDAQ)}개 종목 로드 완료.")
except:
    DF_NASDAQ = pd.DataFrame()

print("[준비 완료]\n")

# ============================================================
# 일목균형표 계산
# ============================================================
def calculate_ichimoku(df):
    nine_period_high = df['High'].rolling(window=9).max()
    nine_period_low = df['Low'].rolling(window=9).min()
    df['tenkan_sen'] = (nine_period_high + nine_period_low) / 2
    period26_high = df['High'].rolling(window=26).max()
    period26_low = df['Low'].rolling(window=26).min()
    df['kijun_sen'] = (period26_high + period26_low) / 2
    df['lead_a'] = (df['tenkan_sen'] + df['kijun_sen']) / 2
    period52_high = df['High'].rolling(window=52).max()
    period52_low = df['Low'].rolling(window=52).min()
    df['lead_b'] = (period52_high + period52_low) / 2
    df['senkou_span_a'] = df['lead_a'].shift(26)
    df['senkou_span_b'] = df['lead_b'].shift(26)
    return df

# ============================================================
# 종목 분석 (하나하나 꼼꼼하게)
# ============================================================
def analyze_stocks(tickers, ticker_to_name, theme_label):
    results = {
        "future_twist": [], "breakout_red_cloud": [], "high_volume": [],
        "breakout_and_consolidation": [], "ma200_breakout": [], "monthly_bottom_reversal": []
    }
    total = len(tickers)
    print(f"\n=== [{theme_label}] 총 {total}개 종목 전수 조사 시작 ===")
    
    for idx, ticker in enumerate(tickers):
        try:
            name = ticker_to_name.get(ticker, ticker)
            print(f"  [{idx+1}/{total}] {name} ({ticker}) 분석 중...", end='\r')
            
            t_obj = yf.Ticker(ticker)
            df = t_obj.history(period="2y", interval="1d")
            if df.empty or len(df) < 200:
                continue
            
            # 시가총액: 한국 종목은 KRX 캐시에서, 미국 종목은 yfinance에서
            is_krx = ticker.endswith('.KS') or ticker.endswith('.KQ')
            pure_code = ticker.split('.')[0] if is_krx else ticker
            market_cap = KRX_CAP_MAP.get(pure_code, 0) if is_krx else 0
            if market_cap == 0:
                try:
                    market_cap = t_obj.fast_info.get('market_cap', 0)
                    if market_cap == 0:
                        market_cap = t_obj.info.get('marketCap', 0)
                except:
                    pass

            df = calculate_ichimoku(df)
            signals = []
            
            # 1. 미래 구름대 양운 전환
            if df['lead_a'].iloc[-1] > df['lead_b'].iloc[-1] and df['lead_a'].iloc[-2] <= df['lead_b'].iloc[-2]:
                signals.append("future_twist")
            
            # 2. 음운 상향 돌파
            if df['senkou_span_b'].iloc[-1] > df['senkou_span_a'].iloc[-1]:
                if (df['senkou_span_a'].iloc[-2] <= df['Close'].iloc[-2] <= df['senkou_span_b'].iloc[-2]) and df['Close'].iloc[-1] > df['senkou_span_b'].iloc[-1]:
                    signals.append("breakout_red_cloud")
            
            # 3. 거래량 폭발
            avg_vol = df['Volume'].rolling(window=20).mean()
            if df['Volume'].iloc[-1] > 2.5 * avg_vol.iloc[-1]:
                signals.append("high_volume")
            
            # 4. 전고점 돌파
            if df['Close'].iloc[-1] > df['High'].iloc[-120:-1].max():
                signals.append("breakout_and_consolidation")
            
            # 5. 200일선 돌파
            df['ma_200'] = df['Close'].rolling(window=200).mean()
            if any(df['Close'].iloc[i] > df['ma_200'].iloc[i] and df['Close'].iloc[i-1] <= df['ma_200'].iloc[i-1] for i in range(-5, 0)):
                signals.append("ma200_breakout")

            # 6. 🔥 월봉 최저가 바닥 탈출
            try:
                df_m = df.resample('ME').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()
                if len(df_m) >= 26:
                    high_2y = df_m['High'].tail(24).max()
                    if df['Close'].iloc[-1] < (high_2y * 0.35):
                        vol_avg_6m = df_m['Volume'].iloc[-7:-1].mean()
                        if df_m['Volume'].iloc[-1] > (vol_avg_6m * 1.5):
                            m_high9 = df_m['High'].rolling(window=9).max()
                            m_low9 = df_m['Low'].rolling(window=9).min()
                            m_tenkan = (m_high9 + m_low9) / 2
                            m_high26 = df_m['High'].rolling(window=26).max()
                            m_low26 = df_m['Low'].rolling(window=26).min()
                            m_kijun = (m_high26 + m_low26) / 2
                            curr_c = df_m['Close'].iloc[-1]
                            if (curr_c > df_m['Open'].iloc[-1]) and (curr_c > m_tenkan.iloc[-1] or curr_c > m_kijun.iloc[-1] or abs(curr_c - m_tenkan.iloc[-1]) / m_tenkan.iloc[-1] < 0.02):
                                signals.append("monthly_bottom_reversal")
            except:
                pass

            if signals:
                display_name = f"{name}({ticker})"
                ticker_data = {
                    "display": display_name,
                    "ticker": ticker,
                    "name": name,
                    "analysis": {
                        "price": float(df['Close'].iloc[-1]),
                        "market_cap": int(market_cap),
                        "ma20_support": False,
                        "ma60_support": False,
                        "pattern": ""
                    }
                }
                for s in signals:
                    results[s].append(ticker_data)
                print(f"  [{idx+1}/{total}] {name} → 신호 발견: {signals}")
        except Exception as e:
            pass
    
    print(f"\n  [{theme_label}] 분석 완료.\n")
    return results

# ============================================================
# 테마 정의
# ============================================================
THEMES = {
    "반도체 (Semiconductors)": {"krx": ["반도체", "전자부품"], "nasdaq": ["Semiconductor"]},
    "제약/바이오 (Healthcare/Biotech)": {"krx": ["의약품", "바이오", "제약"], "nasdaq": ["Biotechnology", "Drug"]},
    "소프트웨어/IT (Software/IT)": {"krx": ["소프트웨어", "IT", "인터넷"], "nasdaq": ["Software", "Internet"]},
    "자동차/모빌리티 (Auto/Mobility)": {"krx": ["자동차", "운송장비", "차량"], "nasdaq": ["Auto", "Vehicle"]},
    "2차전지/에너지 (EV/Energy)": {"krx": ["전지", "에너지", "화학", "유틸리티"], "nasdaq": ["Battery", "Energy", "Electric"]},
    "금융 (Financials)": {"krx": ["은행", "금융", "보험", "증권"], "nasdaq": ["Bank", "Financial", "Insurance"]},
    "인공지능/로봇 (AI/Robotics)": {"krx": ["로봇", "인공지능"], "nasdaq": ["Artificial Intelligence", "Robot"]},
    "우주항공/국방 (Aerospace/Defense)": {"krx": ["항공", "우주", "국방"], "nasdaq": ["Aerospace", "Defense"]},
    "조선/해운 (Shipbuilding/Shipping)": {"krx": ["조선", "해운"], "nasdaq": ["Marine", "Shipping"]}
}

# ============================================================
# 종목 검색: KRX-DESC의 Industry 컬럼 사용
# ============================================================
def get_market_tickers(theme_name, market_type="ALL"):
    keywords = THEMES.get(theme_name, {})
    krx_tickers = []
    nasdaq_tickers = []
    ticker_to_name = {}

    # 한국 시장: KRX-DESC에서 Industry 컬럼으로 검색
    if market_type in ["ALL", "KRX"] and not DF_KRX_DESC.empty:
        print(f"[{theme_name}] 한국 시장 종목 선정 중...")
        for kw in keywords.get("krx", []):
            matched = DF_KRX_DESC[DF_KRX_DESC['Industry'].str.contains(kw, na=False)]
            for _, row in matched.iterrows():
                code = row['Code']
                name = row['Name']
                market = row['Market']
                suffix = ".KS" if market == 'KOSPI' else ".KQ"
                full_symbol = code + suffix
                krx_tickers.append(full_symbol)
                ticker_to_name[full_symbol] = name
        krx_tickers = list(set(krx_tickers))
        print(f"  → {len(krx_tickers)}개 종목 발견")

    # 미국 시장: NASDAQ에서 Industry 컬럼으로 검색
    if market_type in ["ALL", "NASDAQ"] and not DF_NASDAQ.empty:
        print(f"[{theme_name}] 미국 시장 종목 선정 중...")
        n_col = 'Industry' if 'Industry' in DF_NASDAQ.columns else None
        if n_col:
            for kw in keywords.get("nasdaq", []):
                matched = DF_NASDAQ[DF_NASDAQ[n_col].str.contains(kw, na=False, case=False)]
                for _, row in matched.iterrows():
                    symbol = row['Symbol']
                    nasdaq_tickers.append(symbol)
                    ticker_to_name[symbol] = row['Name']
        nasdaq_tickers = list(set(nasdaq_tickers))
        print(f"  → {len(nasdaq_tickers)}개 종목 발견")

    return krx_tickers, nasdaq_tickers, ticker_to_name

# ============================================================
# 디스코드 최종 알림
# ============================================================
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1498250241797783633/p3PLg26FuaMuZEs80v3kQakvEyL6dJp10rICVQnDYy_3WNFwHRJOG6cyjetGNymaWwqk"

def send_final_notification():
    if not DISCORD_WEBHOOK_URL:
        return
    embed = {
        "title": "✅ 전체 스캔 및 분석 완료",
        "description": "대시보드에서 결과를 확인하세요.",
        "color": 65280,
        "fields": [{"name": "🔗 대시보드", "value": "http://localhost:5173", "inline": False}],
        "timestamp": datetime.datetime.now().isoformat()
    }
    payload = {"content": "🚀 **분석이 완료되었습니다!**", "embeds": [embed]}
    try:
        requests.post(DISCORD_WEBHOOK_URL, data=json.dumps(payload), headers={"Content-Type": "application/json"})
        print("[알림] 디스코드 완료 알림 전송 성공.")
    except:
        pass

# ============================================================
# 메인 실행
# ============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--market', type=str, default="ALL")
    args = parser.parse_args()
    
    all_scan_results = []
    
    for theme_name in THEMES.keys():
        krx_tickers, nasdaq_tickers, ticker_to_name = get_market_tickers(theme_name, market_type=args.market)
        
        res_krx = {}
        if krx_tickers:
            res_krx = analyze_stocks(krx_tickers, ticker_to_name, f"{theme_name} - KRX")
        
        res_nasdaq = {}
        if nasdaq_tickers:
            res_nasdaq = analyze_stocks(nasdaq_tickers, ticker_to_name, f"{theme_name} - NASDAQ")
        
        all_scan_results.append({
            "theme": theme_name,
            "krx": res_krx,
            "nasdaq": res_nasdaq
        })

    output_data = {
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data": all_scan_results
    }
    
    os.makedirs("frontend/public", exist_ok=True)
    with open("frontend/public/scan_results.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=4)
    
    send_final_notification()
    print("\n[완료] 분석 결과가 성공적으로 저장되었습니다.")
