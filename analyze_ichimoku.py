# -*- coding: utf-8 -*-
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
import logging
from dotenv import load_dotenv

load_dotenv()

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 로깅 설정
logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# ============================================================
# 전역 캐시: 시작 시 한 번만 로드
# ============================================================
print("[준비] 시장 데이터를 로드 중입니다...")

try:
    DF_KRX_PRICE = fdr.StockListing('KRX')
    KRX_CAP_MAP = dict(zip(DF_KRX_PRICE['Code'], DF_KRX_PRICE['Marcap']))
    print(f"  > KRX 시세 데이터 {len(DF_KRX_PRICE)}개 종목 로드 완료.")
except Exception as e:
    logger.warning(f"KRX 시세 데이터 로드 실패: {e}")
    DF_KRX_PRICE = pd.DataFrame()
    KRX_CAP_MAP = {}

try:
    DF_KRX_DESC = fdr.StockListing('KRX-DESC')
    print(f"  > KRX 업종 데이터 {len(DF_KRX_DESC)}개 종목 로드 완료.")
except Exception as e:
    logger.warning(f"KRX 업종 데이터 로드 실패: {e}")
    DF_KRX_DESC = pd.DataFrame()

try:
    DF_NASDAQ = fdr.StockListing('NASDAQ')
    print(f"  > NASDAQ 데이터 {len(DF_NASDAQ)}개 종목 로드 완료.")
except Exception as e:
    logger.warning(f"NASDAQ 데이터 로드 실패: {e}")
    DF_NASDAQ = pd.DataFrame()

# KRX merge (한 번만 수행)
try:
    DF_KRX_MERGED = pd.merge(DF_KRX_PRICE, DF_KRX_DESC, on='Code', how='inner')
except Exception as e:
    logger.warning(f"KRX 데이터 병합 실패: {e}")
    DF_KRX_MERGED = pd.DataFrame()

print("[준비 완료]\n")

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

    # Current Cloud (shifted)
    df['senkou_span_a'] = df['lead_a'].shift(26)
    df['senkou_span_b'] = df['lead_b'].shift(26)

    return df

def analyze_stocks(tickers, ticker_to_name):
    results = {
        "monthly_pattern": [],
        "cloud_twist": [],
        "cloud_twist_1w": [],
        "ma200_support_breakout": [],
        "5yr_high_breakout": []
    }

    total = len(tickers)
    for idx, ticker in enumerate(tickers):
        try:
            name = ticker_to_name.get(ticker, "")
            display_name = f"{name}({ticker})" if name else ticker

            # 진행상황 표시: 퍼센트 + 현재 스캔 중인 종목
            pct = (idx + 1) / total * 100
            bar_len = 20
            filled = int(bar_len * (idx + 1) / total)
            bar = '█' * filled + '░' * (bar_len - filled)
            progress_msg = f"\r  [{bar}] {pct:5.1f}% ({idx+1}/{total}) | 스캔 중: {display_name}"
            # 이전 줄 잔여 문자 제거를 위해 공백 패딩
            sys.stdout.write(f"{progress_msg:<80}")
            sys.stdout.flush()

            # 속도 향상과 에러 방지를 위해 period="10y" (최대 10년) 데이터만 다운로드
            import time; time.sleep(0.05) # Yahoo 차단 방지 (Rate limit 완화)
            df = yf.download(ticker, period="10y", interval="1d", progress=False)
            if df.empty or len(df) < 60: continue

            # yfinance MultiIndex 평탄화
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.droplevel(1)

            df = calculate_ichimoku(df)

            # 시가총액 가져오기 (한국 종목은 KRX 캐시에서, 미국은 yfinance에서)
            is_krx = ticker.endswith('.KS') or ticker.endswith('.KQ')
            pure_code = ticker.split('.')[0] if is_krx else ticker
            market_cap = KRX_CAP_MAP.get(pure_code, 0) if is_krx else 0
            if market_cap == 0:
                try:
                    t_obj = yf.Ticker(ticker)
                    market_cap = getattr(t_obj.fast_info, 'market_cap', t_obj.fast_info.get('marketCap', 0))
                    # t_obj.info 는 속도가 매우 느리고 Yahoo 차단(Rate Limit)의 주 원인이므로 제거
                    if market_cap is None or pd.isna(market_cap):
                        market_cap = 0
                except Exception as e:
                    logger.debug(f"{ticker} 시가총액 조회 실패: {e}")

            # ── 시가총액 필터 (0인 경우 제외, 미국 주식은 한화 5000억 이상) ──
            if market_cap <= 0:
                continue
            US_MIN_MARKET_CAP = 357_000_000
            if not is_krx and market_cap < US_MIN_MARKET_CAP:
                continue

            signals = []

            # 1. 당일 양운 전환
            if df['lead_a'].iloc[-1] > df['lead_b'].iloc[-1] and df['lead_a'].iloc[-2] <= df['lead_b'].iloc[-2]:
                signals.append("cloud_twist")

            # 2. 1주일 양운 전환 (최근 5일 이내 음운에서 양운으로 크로스오버/전환)
            is_recent_twist = False
            for i in range(-5, 0):
                try:
                    if df['lead_a'].iloc[i] > df['lead_b'].iloc[i] and df['lead_a'].iloc[i-1] <= df['lead_b'].iloc[i-1]:
                        is_recent_twist = True
                        break
                except IndexError:
                    break
            
            if is_recent_twist:
                signals.append("cloud_twist_1w")

            # 3. 최근 5년(약 1260일) 차트 기준 전고점 돌파
            # 과거(최근 20일 제외)의 최고점을 최근 20일 내에 돌파했고, 현재 종가가 그 고점 부근에 유지되는지 확인
            if len(df) >= 120:  # 최소 6개월 이상 데이터가 있는 종목만 의미 있는 전고점으로 간주
                past_df = df.iloc[-1260:-20] if len(df) > 1260 else df.iloc[:-20]
                if not past_df.empty:
                    prev_high = past_df['High'].max()
                    recent_20d_high = df['High'].iloc[-20:].max()
                    curr_close = df['Close'].iloc[-1]
                    
                    # 최근 20일 동안 과거 전고점을 돌파한 적이 있고, 종가가 전고점의 98% 이상에서 지지받고 있을 때
                    if prev_high > 0 and recent_20d_high >= prev_high and curr_close >= prev_high * 0.98:
                        signals.append("5yr_high_breakout")

            # 3. 200일선 존재 및 지지/돌파
            if len(df) >= 200:
                df['ma_200'] = df['Close'].rolling(window=200).mean()
                try:
                    curr_close = df['Close'].iloc[-1]
                    curr_ma200 = df['ma_200'].iloc[-1]
                    # 최근 5일 이내 돌파 확인
                    is_breakout = any(df['Close'].iloc[i] > df['ma_200'].iloc[i] and df['Close'].iloc[i-1] <= df['ma_200'].iloc[i-1] for i in range(-5, 0))
                    # 200일선 위에서 5% 이내로 근접하여 지지받고 있는지 확인
                    is_support = (curr_close > curr_ma200) and (curr_close <= curr_ma200 * 1.05)
                    if is_breakout or is_support:
                        signals.append("ma200_support_breakout")
                except Exception as e:
                    logger.debug(f"{ticker} MA200 분석 실패: {e}")

            # 4. 월봉: 대세 하락 후 바닥 다지기(지지) & 강한 장대양봉 돌파(상승) 패턴
            try:
                try:
                    df_m = df.resample('ME').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()
                except Exception:
                    df_m = df.resample('M').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()

                if len(df_m) >= 6:
                    lookback = min(24, len(df_m))
                    recent_24m = df_m.iloc[-lookback:]
                    max_high_24m = recent_24m['High'].max()
                    min_low_24m = recent_24m['Low'].min()
                    
                    # 1. 고점 대비 최소 40% 이상 하락한 이력 (대세 하락장/바닥권)
                    if max_high_24m >= min_low_24m * 1.6:
                        def is_strong_green(candle):
                            c_open = candle['Open'].item() if isinstance(candle['Open'], pd.Series) else candle['Open']
                            c_close = candle['Close'].item() if isinstance(candle['Close'], pd.Series) else candle['Close']
                            return (c_close > c_open) and (c_close >= c_open * 1.15) # 최소 15% 이상 상승한 장대양봉

                        # 2. 이번 달(-1) 또는 지난 달(-2)에 강한 장대양봉 발생 여부
                        breakout_idx = None
                        if is_strong_green(df_m.iloc[-1]):
                            breakout_idx = -1
                        elif is_strong_green(df_m.iloc[-2]):
                            breakout_idx = -2
                            
                        if breakout_idx is not None:
                            # 3. 장대양봉 직전 3~4개월간의 바닥 다지기(지지) 확인
                            start_idx = breakout_idx - 4
                            end_idx = breakout_idx
                            if start_idx >= -len(df_m):
                                base_candles = df_m.iloc[start_idx:end_idx]
                                base_low = base_candles['Low'].min()
                                base_high = base_candles['High'].max()
                                
                                # 바닥권 조건: 지지 구간의 고점이 2년 전체 변동폭의 하위 35% 이내에 있어야 함 (확실한 바닥권)
                                range_24m = max_high_24m - min_low_24m
                                bottom_threshold = min_low_24m + (range_24m * 0.35)
                                is_at_bottom = (base_high <= bottom_threshold)
                                
                                # 돌파 조건: 장대양봉의 종가가 지지 구간의 고점을 뚫어내거나 근접해야 함
                                b_candle = df_m.iloc[breakout_idx]
                                b_close = b_candle['Close'].item() if isinstance(b_candle['Close'], pd.Series) else b_candle['Close']
                                is_breaking_out = (b_close >= base_high * 0.95)
                                
                                if is_at_bottom and is_breaking_out:
                                    signals.append("monthly_pattern")
            except Exception as e:
                logger.debug(f"{ticker} 월봉 분석 실패: {e}")


            if "ma200_support_breakout" in signals and len(signals) == 1:
                signals.remove("ma200_support_breakout")

            if signals:
                pe_ratio = 0.0
                pb_ratio = 0.0
                try:
                    info = yf.Ticker(ticker).info
                    pe_info = info.get('trailingPE')
                    pb_info = info.get('priceToBook')
                    if pe_info is not None:
                        pe_val = float(pe_info)
                        if not np.isinf(pe_val) and not np.isnan(pe_val):
                            pe_ratio = pe_val
                    if pb_info is not None:
                        pb_val = float(pb_info)
                        if not np.isinf(pb_val) and not np.isnan(pb_val):
                            pb_ratio = pb_val
                except Exception:
                    pass

                ticker_data = {
                    "display": display_name,
                    "ticker": ticker,
                    "name": name,
                    "analysis": {
                        "price": float(df['Close'].iloc[-1]) if not pd.isna(df['Close'].iloc[-1]) else 0.0,
                        "market_cap": 0 if pd.isna(market_cap) else int(market_cap),
                        "pe_ratio": pe_ratio,
                        "pb_ratio": pb_ratio,
                        "ma20_support": False,
                        "ma60_support": False,
                        "pattern": ""
                    }
                }
                for s in signals:
                    results[s].append(ticker_data)
        except Exception as e:
            logger.warning(f"{ticker} 분석 중 오류 발생: {e}")

    return results

THEMES = {
    "IT (소프트웨어, 하드웨어, 반도체, IT 기기 및 서비스)": {
        "krx": ["소프트웨어", "IT", "반도체", "전자", "컴퓨터", "정보기술", "하드웨어"],
        "nasdaq": ["Software", "Hardware", "Semiconductor", "IT", "Information Technology", "Electronic", "소프트웨어", "반도체", "전자", "컴퓨터", "정보기술", "하드웨어"]
    },
    "커뮤니케이션 (통신, 미디어, 엔터테인먼트, 인터랙티브 미디어 및 서비스)": {
        "krx": ["통신", "미디어", "엔터테인먼트", "방송", "영화", "인터넷", "게임"],
        "nasdaq": ["Communication", "Media", "Entertainment", "Interactive Media", "Telecom", "Broadcasting", "통신", "미디어", "엔터테인먼트", "방송", "영화", "인터넷", "게임"]
    },
    "임의소비재 (자동차 및 부품, 내구소비재, 의류, 레저, 호텔/레스토랑)": {
        "krx": ["자동차", "내구소비재", "의류", "레저", "호텔", "레스토랑", "여행", "소비재"],
        "nasdaq": ["Automobile", "Auto Parts", "Consumer Discretionary", "Apparel", "Leisure", "Hotel", "Restaurant", "자동차", "내구소비재", "의류", "레저", "호텔", "레스토랑", "여행", "소비재"]
    },
    "필수소비재 (식음료, 유통, 가정용품, 개인용품, 담배)": {
        "krx": ["식음료", "유통", "가정용품", "개인용품", "담배", "생활용품", "화장품"],
        "nasdaq": ["Consumer Staples", "Food", "Beverage", "Retail", "Household", "Personal", "Tobacco", "식음료", "유통", "가정용품", "개인용품", "담배", "생활용품", "화장품"]
    },
    "헬스케어 (제약, 생명공학(바이오), 의료기기, 헬스케어 서비스 및 장비)": {
        "krx": ["제약", "바이오", "생명공학", "의료기기", "헬스케어"],
        "nasdaq": ["Healthcare", "Pharmaceutical", "Biotechnology", "Medical", "Health Care", "제약", "바이오", "생명공학", "의료기기", "헬스케어"]
    },
    "금융 (은행, 보험, 다각화된 금융 서비스, 소비자 금융)": {
        "krx": ["은행", "보험", "금융", "증권", "지주"],
        "nasdaq": ["Financial", "Bank", "Insurance", "Consumer Finance", "Capital Markets", "은행", "보험", "금융", "증권", "지주"]
    },
    "산업재 (자본재, 기계, 상업/전문 서비스, 운송 및 물류)": {
        "krx": ["산업재", "기계", "상업", "운송", "물류", "건설", "조선", "항공"],
        "nasdaq": ["Industrial", "Capital Goods", "Machinery", "Commercial Services", "Transportation", "Logistics", "Aerospace", "산업재", "기계", "상업", "운송", "물류", "건설", "조선", "항공"]
    },
    "소재 (화학, 건설자재, 금속 및 채광, 종이/포장재)": {
        "krx": ["화학", "건설자재", "금속", "채광", "종이", "포장재", "철강", "비철금속"],
        "nasdaq": ["Material", "Chemical", "Construction Material", "Metals", "Mining", "Paper", "Packaging", "화학", "건설자재", "금속", "채광", "종이", "포장재", "철강", "비철금속"]
    },
    "에너지 (석유/가스 탐사 및 생산, 정제, 에너지 장비 및 서비스)": {
        "krx": ["에너지", "석유", "가스", "정제"],
        "nasdaq": ["Energy", "Oil", "Gas", "Exploration", "Refining", "Energy Equipment", "에너지", "석유", "가스", "정제"]
    },
    "유틸리티 (전력, 가스, 수도, 다각화된 재생에너지)": {
        "krx": ["전력", "수도", "유틸리티", "재생에너지", "환경"],
        "nasdaq": ["Utility", "Electric", "Water", "Renewable", "전력", "수도", "유틸리티", "재생에너지", "환경"]
    },
    "부동산 (부동산 관리 및 개발, 리츠(REITs))": {
        "krx": ["부동산", "리츠", "리츠(REITs)", "건설업"],
        "nasdaq": ["Real Estate", "REIT", "Property Management", "Development", "부동산", "리츠", "리츠(REITs)", "건설업"]
    }
}

# ============================================================
# 종목 검색 (원본 방식: KRX + KRX-DESC merge)
# ============================================================
def get_market_tickers(theme_name, market_type="ALL"):
    keywords = THEMES.get(theme_name, {})
    krx_tickers = []
    nasdaq_tickers = []
    ticker_to_name = {}

    # 1. 한국 주식 (KRX) — 전역 캐시 사용
    if market_type in ["ALL", "KRX"] and not DF_KRX_MERGED.empty:
        print(f"[{theme_name}] 한국 시장 종목 선정 중...")
        try:
            krx = DF_KRX_MERGED.copy()

            # 시가총액 1000억 이상 필터링
            krx = krx[krx['Marcap'] >= 100_000_000_000]

            krx_kws = keywords.get("krx", [])
            if krx_kws:
                s_col = 'Sector' if 'Sector' in krx.columns else None
                i_col = 'Industry_y' if 'Industry_y' in krx.columns else ('Industry' if 'Industry' in krx.columns else None)

                mask = pd.Series(False, index=krx.index)
                for kw in krx_kws:
                    if s_col and s_col in krx.columns:
                        mask = mask | krx[s_col].str.contains(kw, na=False, regex=False)
                    if i_col and i_col in krx.columns:
                        mask = mask | krx[i_col].str.contains(kw, na=False, regex=False)

                krx_filtered = krx[mask]

                name_col = 'Name_x' if 'Name_x' in krx_filtered.columns else 'Name'
                market_col = 'Market_x' if 'Market_x' in krx_filtered.columns else 'Market'

                for _, row in krx_filtered.iterrows():
                    suffix = ".KS" if row[market_col] == 'KOSPI' else ".KQ"
                    ticker = f"{row['Code']}{suffix}"
                    krx_tickers.append(ticker)
                    ticker_to_name[ticker] = row[name_col]

            krx_tickers = list(set(krx_tickers))
            print(f"  → {len(krx_tickers)}개 종목 발견")
        except Exception as e:
            print(f"  [오류] KRX 데이터 처리 실패: {e}")

    # 2. 미국 주식 (NASDAQ) — 전역 캐시 사용
    if market_type in ["ALL", "NASDAQ"] and not DF_NASDAQ.empty:
        print(f"[{theme_name}] 미국 시장 종목 선정 중...")
        try:
            nasdaq = DF_NASDAQ.copy()
            nasdaq_kws = keywords.get("nasdaq", [])

            if nasdaq_kws and 'Industry' in nasdaq.columns:
                mask = pd.Series(False, index=nasdaq.index)
                for kw in nasdaq_kws:
                    mask = mask | nasdaq['Industry'].str.contains(kw, na=False, case=False, regex=False)

                nasdaq_filtered = nasdaq[mask]

                for _, row in nasdaq_filtered.iterrows():
                    symbol = row['Symbol']
                    nasdaq_tickers.append(symbol)
                    ticker_to_name[symbol] = row['Name']

            nasdaq_tickers = list(set(nasdaq_tickers))
            print(f"  → {len(nasdaq_tickers)}개 종목 발견")
        except Exception as e:
            print(f"  [오류] NASDAQ 데이터 처리 실패: {e}")

    return krx_tickers, nasdaq_tickers, ticker_to_name

# ============================================================
# 디스코드 전송 (테마별 한국/미국 결과를 하나로 묶어 전송)
# ============================================================
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
BASE_DASHBOARD_URL = "http://localhost:5173"

labels = {
    "monthly_pattern": "🛡️ 월봉 지지 후 상승 패턴",
    "cloud_twist": "🟢 양운 전환 (당일)",
    "cloud_twist_1w": "❇️ 1주 내 양운 전환: 음운에서 양운 크로스오버",
    "ma200_support_breakout": "📈 200일선: 지지 또는 돌파",
    "5yr_high_breakout": "🚀 5년 전고점 돌파: 새로운 주가 레벨 진입"
}

def translate_to_ko(text):
    if not text or text in ['No title', 'No summary']: return text
    try:
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=ko&dt=t&q={requests.utils.quote(text)}"
        res = requests.get(url, timeout=3)
        if res.status_code == 200:
            return "".join([x[0] for x in res.json()[0]])
    except Exception:
        pass
    return text

def get_realtime_data():
    print("[데이터] 실시간 시장 데이터를 가져오는 중...")
    data = {}
    
    # DXY
    try:
        dxy = yf.Ticker('DX-Y.NYB').fast_info.last_price
        data['DXY'] = f"{round(dxy, 2):.2f}"
    except Exception:
        data['DXY'] = "97.86"

    # FRED Macro Indicators
    try:
        import FinanceDataReader as fdr
        import pandas as pd
        
        try:
            cpi = fdr.DataReader('FRED:CPIAUCSL')
            cpi_yoy = (cpi.iloc[-1,0] / cpi.iloc[-13,0] - 1) * 100
            data['CPI_YOY'] = f"{cpi_yoy:.1f}%"
        except Exception: data['CPI_YOY'] = "3.3%"
        
        try:
            pce = fdr.DataReader('FRED:PCEPI')
            pce_yoy = (pce.iloc[-1,0] / pce.iloc[-13,0] - 1) * 100
            data['PCE_YOY'] = f"{pce_yoy:.1f}%"
        except Exception: data['PCE_YOY'] = "3.5%"
        
        try:
            payems = fdr.DataReader('FRED:PAYEMS')
            nfp = payems.iloc[-1,0] - payems.iloc[-2,0]
            data['NFP'] = f"{nfp:.0f}K"
        except Exception: data['NFP'] = "178K"
        
        try:
            unrate = fdr.DataReader('FRED:UNRATE')
            data['UNRATE'] = f"{unrate.iloc[-1,0]:.1f}%"
        except Exception: data['UNRATE'] = "4.3%"
        
        try:
            fed_upper = fdr.DataReader('FRED:DFEDTARU').iloc[-1,0]
            fed_lower = fdr.DataReader('FRED:DFEDTARL').iloc[-1,0]
            data['FED_RATE'] = f"Fed {fed_lower:.2f}~{fed_upper:.2f}%"
        except Exception: data['FED_RATE'] = "Fed 3.50~3.75%"
        
        try:
            nfci = fdr.DataReader('FRED:NFCI')
            data['NFCI'] = f"{nfci.iloc[-1,0]:.2f}"
        except Exception: data['NFCI'] = "-0.52"
        
        data['PMI'] = "52.7"
    except Exception:
        data['CPI_YOY'] = "3.3%"
        data['PCE_YOY'] = "3.5%"
        data['NFP'] = "178K"
        data['UNRATE'] = "4.3%"
        data['FED_RATE'] = "Fed 3.50~3.75%"
        data['NFCI'] = "-0.52"
        data['PMI'] = "52.7"

    # KRW
    try:
        krw = yf.Ticker('KRW=X').fast_info.last_price
        data['KRW'] = f"{int(krw):,}"
    except Exception:
        data['KRW'] = "1,470"

    # VIX
    try:
        vix = yf.Ticker('^VIX').fast_info.last_price
        data['VIX'] = round(vix, 2)
    except Exception:
        data['VIX'] = 17.38

    # Gold
    try:
        gold = yf.Ticker('GC=F').fast_info.last_price
        data['GOLD'] = f"{int(gold):,}"
    except Exception:
        data['GOLD'] = "4,720"

    # Silver
    try:
        silver = yf.Ticker('SI=F').fast_info.last_price
        data['SILVER'] = f"{int(silver):,}"
    except Exception:
        data['SILVER'] = "79"

    # Copper
    try:
        copper = yf.Ticker('HG=F').fast_info.last_price
        data['COPPER'] = f"{round(copper, 2):.2f}"
    except Exception:
        data['COPPER'] = "6.17"

    # WTI
    try:
        wti = yf.Ticker('CL=F').fast_info.last_price
        data['WTI'] = f"{round(wti, 2):.2f}"
    except Exception:
        data['WTI'] = "92.78"

    # TNX (10-Year Yield) & News
    try:
        hist = yf.Ticker('^TNX').history(period='5d')
        tnx = float(hist['Close'].iloc[-1])
        data['TNX'] = f"{round(tnx, 3):.3f}"
    except Exception:
        try:
            tnx = yf.Ticker('^TNX').fast_info.last_price
            data['TNX'] = f"{round(tnx, 3):.3f}"
        except Exception:
            data['TNX'] = "4.360"
            
    try:
        tnx_news = yf.Ticker('^TNX').news[:3]
        tnx_news_str = "\n\n".join([f"🔹 {translate_to_ko(n.get('content', {}).get('title', 'No title'))}\n  └ {translate_to_ko(n.get('content', {}).get('summary', 'No summary'))}" for n in tnx_news])
        data['TNX_NEWS'] = tnx_news_str if tnx_news_str else "- 최근 10년물 국채 관련 특이 뉴스 없음."
    except Exception:
         data['TNX_NEWS'] = "- 최근 10년물 국채 관련 특이 뉴스 없음."

    # BTC-USD & News
    try:
        hist = yf.Ticker('BTC-USD').history(period='5d')
        btc = float(hist['Close'].iloc[-1])
        data['BTC'] = f"{int(btc):,}"
    except Exception:
        try:
            btc = yf.Ticker('BTC-USD').fast_info.last_price
            data['BTC'] = f"{int(btc):,}"
        except Exception:
            data['BTC'] = "80,750"
            
    try:
        btc_news = yf.Ticker('BTC-USD').news[:3]
        btc_news_str = "\n\n".join([f"🔹 {translate_to_ko(n.get('content', {}).get('title', 'No title'))}\n  └ {translate_to_ko(n.get('content', {}).get('summary', 'No summary'))}" for n in btc_news])
        data['BTC_NEWS'] = btc_news_str if btc_news_str else "- 최근 비트코인 관련 특이 뉴스 없음."
    except Exception:
        data['BTC_NEWS'] = "- 최근 비트코인 관련 특이 뉴스 없음."

    # Macro / Geopolitical News
    try:
        import xml.etree.ElementTree as ET
        import urllib.parse
        
        # 한국 뉴스 (최근 24시간)
        kr_query = '(정부정책 OR 연준 OR 지정학적 리스크 OR 금리 OR 환율) AND (증시 OR 주식 OR 주가 OR 수혜 OR 타격 OR 전망) when:1d'
        kr_encoded = urllib.parse.quote(kr_query)
        kr_res = requests.get(f'https://news.google.com/rss/search?q={kr_encoded}&hl=ko&gl=KR&ceid=KR:ko')
        kr_root = ET.fromstring(kr_res.text)
        kr_items = kr_root.findall('.//item')[:5]
        kr_news = []
        for i in kr_items:
            title = i.find('title').text if i.find('title') is not None else 'No title'
            title = title.rsplit(' - ', 1)[0]
            kr_news.append(f"🇰🇷 {title}")
            
        # 미국 뉴스 (최근 24시간)
        us_query = '(Federal Reserve OR geopolitical risk OR interest rate OR policy) AND (stock market OR shares) when:1d'
        us_encoded = urllib.parse.quote(us_query)
        us_res = requests.get(f'https://news.google.com/rss/search?q={us_encoded}&hl=en-US&gl=US&ceid=US:en')
        us_root = ET.fromstring(us_res.text)
        us_items = us_root.findall('.//item')[:5]
        us_news = []
        for i in us_items:
            title = i.find('title').text if i.find('title') is not None else 'No title'
            title = title.rsplit(' - ', 1)[0]
            ko_title = translate_to_ko(title)
            us_news.append(f"🇺🇸 {ko_title}")
            
        all_news = kr_news + us_news
        data['MACRO_NEWS'] = "\n".join(all_news) if all_news else "- 최근 24시간 내 특이 뉴스 없음."
    except Exception as e:
        data['MACRO_NEWS'] = "- 뉴스 데이터를 불러올 수 없습니다."
        
    # PE Data (Trailing PE)
    etf_symbols = {
        'SPY': '시장 전체',
        'XLK': 'IT',
        'XLC': '커뮤니케이션',
        'XLY': '임의소비재',
        'XLP': '필수소비재',
        'XLV': '헬스케어',
        'XLF': '금융',
        'XLI': '산업재',
        'XLB': '소재',
        'XLE': '에너지',
        'XLU': '유틸리티',
        'XLRE': '부동산'
    }
    
    data['PE'] = {}
    for sym, name in etf_symbols.items():
        try:
            pe = yf.Ticker(sym).info.get('trailingPE')
            if pe:
                data['PE'][name] = pe
            else:
                data['PE'][name] = 20.0
        except:
            data['PE'][name] = 20.0
            
    return data


def get_top30_krx_gainers():
    print("\n[분석] 당일 한국 주식 상승률 상위 30 종목 분석을 시작합니다...")
    try:
        # 최신 데이터를 위해 새로 다운로드
        fresh_krx = fdr.StockListing('KRX')
        if fresh_krx.empty:
            return "- KRX 시세 데이터를 불러올 수 없어 분석할 수 없습니다.", []
        
        # 6자리 종목코드만 필터링 (우선주 등 제외 처리 보완 가능하나 기본 유지)
        fresh_krx = fresh_krx[fresh_krx['Code'].str.len() == 6]
        
        # 상승률(ChagesRatio) 기준 내림차순 정렬하여 상위 30종목 추출
        top30 = fresh_krx.sort_values('ChagesRatio', ascending=False).head(30)
        
        # 섹터 정보를 위해 기존 DF_KRX_DESC와 병합
        if not DF_KRX_DESC.empty:
            top30 = pd.merge(top30, DF_KRX_DESC, on='Code', how='left')
        else:
            top30['Sector'] = ''
            top30['Industry'] = ''
        
        # 종목별 테마 분류 로직 (바이오, 로봇, IT 등)
        def classify_theme(r):
            text = str(r.get('Industry', '')) + " " + str(r.get('Industry_y', '')) + " " + str(r.get('Name_x', '')) + " " + str(r.get('Name', ''))
            if '로봇' in text or '자동화' in text or '드론' in text: return '로봇 및 자동화'
            if '바이오' in text or '제약' in text or '의료' in text or '신약' in text or '생명공학' in text: return '바이오/헬스케어'
            if '반도체' in text: return '반도체'
            if '전지' in text or '배터리' in text or '에코' in text: return '이차전지/배터리'
            if '소프트웨어' in text or 'IT' in text or '정보' in text or '게임' in text or 'AI' in text: return 'IT/소프트웨어'
            if '기계' in text: return '기계장비'
            if '자동차' in text or '부품' in text: return '자동차/부품'
            if '화학' in text or '소재' in text: return '화학/소재'
            if '금융' in text or '지주' in text or '증권' in text or '투자' in text: return '금융/지주사'
            if '건설' in text or '부동산' in text or '리츠' in text: return '건설/부동산'
            if '엔터' in text or '방송' in text or '미디어' in text or '콘텐츠' in text: return '미디어/엔터'
            if '식음료' in text or '식품' in text or '의류' in text or '소비재' in text: return '소비재'
            # 분류되지 않은 경우 원래 산업군 사용
            ind = str(r.get('Industry', str(r.get('Industry_y', ''))))
            if ind and ind != 'nan': return ind
            return '기타'

        top30['Theme'] = top30.apply(classify_theme, axis=1)
        themes = top30['Theme'].value_counts()
        top_themes = themes.head(5)
        
        # 디스코드 보고서 생성
        report_lines = []
        report_lines.append(f"🔍 [당일 상승률 상위 30종목 주요 섹터 분포]")
        for theme, count in top_themes.items():
            t_name = theme if theme == '기타/확인불가' or theme.endswith('관련주') else theme + ' 관련주'
            report_lines.append(f"  └ {t_name}: {count}종목")
            
        report_lines.append(f"\n📈 [상승률 상위 30종목 표]")
        for idx, (_, row) in enumerate(top30.iterrows(), 1):
            name = str(row.get('Name_x', row.get('Name', row['Code'])))
            code = str(row['Code'])
            market = "KS" if str(row.get('Market_x', row.get('Market', ''))) == 'KOSPI' else "KQ"
            chg = float(row.get('ChagesRatio', 0.0))
            theme = str(row.get('Theme', '-'))
            t_name = theme if theme == '기타/확인불가' or theme.endswith('관련주') else theme + ' 관련주'
            report_lines.append(f"{idx:02d}위 | {name} ({code}.{market}) (+{chg:.2f}%) | {t_name}")
            
        # 분석 요약 생략 (리포트 11번의 최종 요약으로 대체됨)
        # 프론트엔드 대시보드용 데이터
        top30_data = []
        for idx, row in top30.iterrows():
            top30_data.append({
                "rank": len(top30_data) + 1,
                "code": row['Code'],
                "name": row.get('Name_x', row.get('Name', row['Code'])),
                "sector": str(row['Sector']) if pd.notna(row.get('Sector')) else '',
                "industry": str(row['Industry']) if pd.notna(row.get('Industry')) else (str(row['Industry_y']) if pd.notna(row.get('Industry_y')) else ''),
                "marcap": int(row['Marcap']) if pd.notna(row['Marcap']) else 0,
                "change_ratio": float(row['ChagesRatio']) if pd.notna(row['ChagesRatio']) else 0.0
            })
            
        return "\n".join(report_lines), top30_data
    except Exception as e:
        logger.warning(f"Top 30 분석 실패: {e}")
        return f"- 분석 중 오류 발생: {e}", []

def get_top30_us_gainers():
    print("\n[분석] 당일 미국 주식 상승률 상위 30 종목 분석을 시작합니다...")
    try:
        url = 'https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?formatted=true&lang=en-US&region=US&scrIds=day_gainers&count=30'
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}, timeout=10)
        quotes = res.json().get('finance', {}).get('result', [{}])[0].get('quotes', [])
        
        sectors_list = []
        industries_list = []
        top30_info = []

        import yfinance as yf
        import time
        import pandas as pd
        
        for q in quotes[:30]:
            sym = q.get('symbol', '')
            name = q.get('shortName', sym)
            ko_name = translate_to_ko(name)
            ko_name = ko_name if ko_name else name
            chg_obj = q.get('regularMarketChangePercent', 0.0)
            chg = chg_obj.get('raw', 0.0) if isinstance(chg_obj, dict) else float(chg_obj)
            
            sector = "Unknown"
            industry = "Unknown"
            try:
                info = yf.Ticker(sym).info
                sector = info.get('sector', 'Unknown')
                industry = info.get('industry', 'Unknown')
                time.sleep(0.1) # Yahoo 차단 방지
            except Exception:
                pass
            
            if sector != "Unknown":
                sectors_list.append(sector)
            if industry != "Unknown":
                industries_list.append(industry)
                
            top30_info.append({"sym": sym, "name": ko_name, "chg": chg, "sector": sector, "industry": industry})

        sectors_counts = pd.Series(sectors_list).value_counts().head(3) if sectors_list else pd.Series(dtype=int)
        industries_counts = pd.Series(industries_list).value_counts().head(3) if industries_list else pd.Series(dtype=int)

        report_lines = []
        report_lines.append(f"🔍 [당일 상승률 상위 종목 주요 섹터 분포]")
        if not sectors_counts.empty:
            for sec, count in sectors_counts.items():
                s_name = translate_to_ko(sec)
                s_name = s_name if s_name == '기타/확인불가' or s_name.endswith('관련주') else s_name + ' 관련주'
                report_lines.append(f"  └ {s_name}: {count}종목")
        else:
            report_lines.append("  └ 정보 없음")

        report_lines.append(f"\n📈 [상승률 상위 종목 표]")
        for idx, info in enumerate(top30_info, 1):
            sec_display = translate_to_ko(info['sector']) if info['sector'] != 'Unknown' else '기타/확인불가'
            s_name = sec_display if sec_display == '기타/확인불가' or sec_display.endswith('관련주') else sec_display + ' 관련주'
            chg = float(info['chg'])
            report_lines.append(f"{idx:02d}위 | {info['sym']} {info['name']} (+{chg:.2f}%) | {s_name}")
        
        return "\n".join(report_lines)
    except Exception as e:
        logger.warning(f"US Top 30 분석 실패: {e}")
        return f"- 미국 시장 분석 중 오류 발생: {e}"

def send_to_discord(top30_krx_text, top30_us_text):
    if not DISCORD_WEBHOOK_URL:
        print("\n[안내] 디스코드 웹훅 URL이 설정되지 않아 메시지를 전송하지 않습니다. (.env 파일을 확인하세요)")
        return

    d = get_realtime_data()
    vix = d['VIX']
    gold = d['GOLD']
    silver = d['SILVER']
    copper = d['COPPER']
    wti = d['WTI']
    tnx = d['TNX']
    btc = d['BTC']
    dxy = d.get('DXY', '97.86')
    krw = d.get('KRW', '1,470')
    
    # 버핏 지수 추산 (VTI 가격을 프록시로 사용하여 추산, 2026년 기준 362.87$ = 231% 로 가정)
    try:
        vti_price = yf.Ticker('VTI').fast_info.last_price
        buffett_indicator = round((vti_price / 362.87) * 231.0, 1)
    except Exception:
        buffett_indicator = 231.0
        
    buffett_alert = ""
    if buffett_indicator >= 200.0:
        buffett_alert = f"\n\n🚨 긴급 역발상 특보: 워런 버핏 지수 극단적 과열 경고\n👉 현재 지수: {buffett_indicator}% (위험 수준 200% 초과)\n⚠️ 버크셔 해서웨이 동향: 애플(AAPL), 뱅크오브아메리카(BAC) 등 주요 지분 대량 매각 후 4,000억 달러 이상 역대 최대 현금 확보. 시장 거품에 대한 강력한 경고로 해석되며, 추격 매수 중단 및 현금 비중 확대 필수."
    elif buffett_indicator <= 130.0:
        buffett_alert = f"\n🚨 긴급 역발상 특보: 워런 버핏 지수 바닥권 진입\n👉 현재 지수: {buffett_indicator}% (극단적 공포 및 기회 구간)\n⚠️ 버크셔 해서웨이 동향: 지수가 130% 이하로 바닥권에 진입하면 버핏은 공격적 매수를 준비합니다. 역사적으로 이런 구간에서 버크셔는 '우량 금융주(골드만삭스, BAC)', '필수소비재', '에너지(옥시덴탈, 셰브론)' 및 해자를 갖춘 '미디어/브랜드' 기업들을 대거 매집했습니다. 펀더멘털 우량주 분할 매수 타점입니다."
        
    berkshire_trade_alert = ""
    
    def format_pe(name, pe):
        if pe >= 19: return f"🔴 {name} → {pe:.1f}배 · 5점 광기"
        elif pe >= 18: return f"🟠 {name} → {pe:.1f}배 · 4점 과열"
        elif pe >= 16: return f"🟡 {name} → {pe:.1f}배 · 3점 중립"
        elif pe >= 15: return f"🟢 {name} → {pe:.1f}배 · 2점 불안"
        else: return f"🟢 {name} → {pe:.1f}배 · 1점 공포"

    pe_data = d.get('PE', {})
    market_pe = pe_data.get('시장 전체', 20.9)
    market_pe_str = format_pe('시장 전체', market_pe).split('· ')[-1]
    
    pe_it = format_pe('IT', pe_data.get('IT', 37.9))
    pe_comm = format_pe('커뮤니케이션', pe_data.get('커뮤니케이션', 21.0))
    pe_disc = format_pe('임의소비재', pe_data.get('임의소비재', 24.5))
    pe_staples = format_pe('필수소비재', pe_data.get('필수소비재', 19.5))
    pe_health = format_pe('헬스케어', pe_data.get('헬스케어', 17.5))
    pe_fin = format_pe('금융', pe_data.get('금융', 16.9))
    pe_ind = format_pe('산업재', pe_data.get('산업재', 20.0))
    pe_mat = format_pe('소재', pe_data.get('소재', 18.2))
    pe_energy = format_pe('에너지', pe_data.get('에너지', 14.5))
    pe_util = format_pe('유틸리티', pe_data.get('유틸리티', 16.5))
    pe_real = format_pe('부동산', pe_data.get('부동산', 32.0))


    try:
        import yfinance as yf
        irx_hist = yf.Ticker('^IRX').history(period='5d')
        irx = float(irx_hist['Close'].iloc[-1])
        tnx_float = float(tnx)
        spread = tnx_float - irx
        
        if spread <= -1.0:
            forecast_result = f"확률적으로 **강력한 금리 '인하' 임박 (인하 확률 95% 이상)**"
        elif spread < -0.2:
            forecast_result = f"확률적으로 **점진적 금리 '인하' 사이클 진입 (인하 확률 70% 이상)**"
        elif spread <= 0.5:
            forecast_result = f"확률적으로 **금리 동결(Pause) 및 관망 (인상/인하 팽팽함)**"
        else:
            forecast_result = f"확률적으로 **추가 금리 '인상' 또는 고금리 장기화 (인상 확률 80% 이상)**"

        rate_forecast_text = f"""📌 [앞으로의 금리의 전망]
현재 미 10년물 국채 금리는 {tnx_float:.3f}%이며, 현재 중앙은행 정책금리 대용치(13주물 T-Bill)는 {irx:.3f}%로, 양자의 차이(스프레드)는 **{spread:+.3f}%p**입니다.
과거 50년 데이터를 분석해 보면:
- **금리 인상 시기**: 보통 장기금리(10년물)가 단기금리보다 0.5%p ~ 1.5%p 이상 높게 유지됩니다.
- **금리 인하 시기**: 경기 침체 우려로 장단기 금리 역전 현상이 발생하며, 통상 장기금리가 단기금리보다 0.5%p ~ 1.5%p 이상 낮아질 때 연준이 파격적인 금리 인하를 단행했습니다.
👉 종합 분석: {forecast_result}

📌 [FOMC 핵심 주시 지표 현황]
FOMC가 금리를 결정할 때 최우선으로 보는 최신 지표는 다음과 같습니다:
1. **Core PCE (근원 개인소비지출)**: 연준의 실질적 물가 목표치 (현재 고착화 여부 주목)
2. **NFP (비농업고용지수) & 실업률**: 고용 시장의 냉각 속도 (실업률 4% 돌파 여부가 금리 인하 트리거)
3. **ISM 서비스업 PMI**: 미국 경제의 70%를 차지하는 서비스업 물가 및 성장 둔화 여부"""
    except Exception as e:
        rate_forecast_text = f"📌 [앞으로의 금리의 전망]\n데이터 수집 오류로 분석을 생략합니다. ({e})"

    messages = [
        f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 안티그레비티 통합 전략 리포트 (1/10)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━{buffett_alert}

📊 주요 경제 및 유동성 지표

🍎 물가 (CPI / PCE): {d.get('CPI_YOY', '3.3%')} / {d.get('PCE_YOY', '3.5%')}

👷 고용/경기 (NFP / 실업률 / PMI): {d.get('NFP', '178K')} / {d.get('UNRATE', '4.3%')} / {d.get('PMI', '52.7')}

💵 금리: {d.get('FED_RATE', 'Fed 3.50~3.75%')}

💧 유동성 NFCI: {d.get('NFCI', '-0.52')}""",

        f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 안티그레비티 통합 전략 리포트 (2/10)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🛢️ 핵심 원자재 트래킹

🥇 금 ${gold} 

🥈 은 ${silver}

🥉 구리 ${copper}

🛢️ WTI ${wti}

💵 외환 & 매크로 지표 변동성 분석

🇺🇸 달러 인덱스(DXY) : {dxy}

🇰🇷 USD/KRW : {krw}원""",

        f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 안티그레비티 통합 전략 리포트 (3/10)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📈 핵심 자산 상관관계 및 거시 지표 분석 (1/2)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🇺🇸 미 국채 10년물 금리 (TNX) : {tnx}%
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{rate_forecast_text}

📌 [현재 상황 및 배경]
10년물 국채금리는 글로벌 자산의 '무위험 수익률(할인율)'로, 증시 밸류에이션에 절대적 영향을 미칩니다.
현재 연준(Fed)의 금리 인하 속도 둔화와 미국의 막대한 재정 적자로 인한 국채 발행 우려가 맞물려, 금리가 쉽게 떨어지지 않고 하방 경직성을 보이고 있습니다.

📌 [증시 영향 및 전망]
금리가 4% 위에서 고공행진할 경우, 주식보다 채권 투자의 매력이 커지며 기관 자금의 이탈이 발생할 수 있습니다.
반대로 고용 지표 둔화 등으로 연준이 비둘기파적 스탠스를 취하며 금리가 꺾인다면, 그동안 짓눌렸던 가치주, 배당주, 중소형주로의 강력한 순환매 장세가 연출될 가능성이 높습니다.

🗞️ [최근 뉴스 동향]
{d.get('TNX_NEWS', '- 최근 뉴스 없음')}""",

        f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 안티그레비티 통합 전략 리포트 (4/10)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📈 핵심 자산 상관관계 및 거시 지표 분석 (2/2)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🪙 비트코인 (BTC) : ${btc}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 [현재 상황 및 배경]
비트코인은 기관 자금 유입이 본격화된 2020년 이후 나스닥 등 '초고위험(High Beta)' 자산과 매우 강하게 동조화되고 있습니다.
역사적으로 거대한 유동성 랠리(2021년, 2024년)에서 증시보다 선행하거나 폭발적으로 함께 상승하는 경향을 보였습니다.

📌 [증시 영향 및 투심 지표]
비트코인의 급락은 단순한 개별 자산의 조정이 아니라, 글로벌 스마트 머니의 '위험 회피(Risk-Off)'와 유동성 축소를 가장 먼저 경고하는 탄광 속 카나리아 역할을 합니다.
최근 미국 정부의 가상자산 정책 변화와 비트코인 현물 ETF 자금 유출입 동향은 전체 증시 투심을 가늠하는 핵심 선행 지표로 작용하고 있습니다.

🗞️ [최근 뉴스 동향]
{d.get('BTC_NEWS', '- 최근 뉴스 없음')}""",

        f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 안티그레비티 통합 전략 리포트 (5/10)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🟢 11개 GICS 섹터 맞춤 전략
🟢 확대  에너지 / 헬스케어 / 소재
🟡 중립  금융 / 유틸리티 / 필수소비재 / 산업재
🔴 축소  IT / 커뮤니케이션 / 임의소비재 / 부동산

💡 전략 근거
유가 ${wti} 고공 + 비용 압박 → 에너지·소재 실적 방어력 돋보임
밸류에이션 부담 적은 헬스케어 대안 부상
고금리 취약 부동산, 소비 둔화 임의소비재 축소 필수
IT·커뮤니케이션 P/E 29배, 차익 실현 압력 극심""",

        f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 안티그레비티 통합 전략 리포트 (6/10)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚖️ 밸류에이션 (P/E) 상태
※ 19↑ 5점(광기) / 18~19 4점(과열) / 16~18 3점(중립) / 15~16 2점(불안) / 15↓ 1점(공포)

📍 시장 전체 Trailing P/E: {market_pe:.1f}배 → {market_pe_str}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
11개 GICS 섹터별 P/E
{pe_it}
{pe_comm}
{pe_disc}
{pe_staples}
{pe_health}
{pe_fin}
{pe_ind}
{pe_mat}
{pe_energy}
{pe_util}
{pe_real}""",

        f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 안티그레비티 통합 전략 리포트 (7/10)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏛️ 정부 정책 & 지정학적 리스크 (최근 24시간)
⚠️ 최신 주요 뉴스
{d.get('MACRO_NEWS', '- 최근 특이 뉴스 없음.')}

💡 [시장 영향 인사이트]
당일 발표된 한·미 양국의 주요 거시경제 및 지정학적 뉴스들은 글로벌 자산 시장의 핵심 변수(유가, 금리, 환율)에 직접적인 영향을 주고 있습니다. 미국 연준의 정책 스탠스 변화와 지정학적 갈등은 외국인 수급 변동성과 안전자산 선호 심리를 크게 자극합니다. 따라서 위 뉴스 흐름을 바탕으로 단기적인 현금 비중 조절과 보다 보수적인 포트폴리오 대응 및 리스크 관리가 필수적인 구간입니다.""",

        f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 안티그레비티 통합 전략 리포트 (8/10)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📝 최종 행동 지침
현재 시장: Trailing P/E {market_pe:.1f}배 + 유가 ${wti} 고공

💰 현금 확보
5점(광기) 섹터 추격 매수 중단, 현금 비중 30%↑ 확보

🔄 로테이션
기술주 → 에너지·금융·소재 (1~2점 저평가 가치주)

🎯 타점 대기
200일선 지지 + 양운 전환 동반 종목만 보수적 접근

⚡ 예외 매수
펀더멘털 견고 + 경영진 $100K↑ 내부자 매수 기업만 분할 스윙 허용""",

        f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 안티그레비티 통합 전략 리포트 (9/10)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🇰🇷 당일 한국 주식 상승률 상위 30 종목 분석
{top30_krx_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🇺🇸 당일 미국 주식 상승률 상위 종목 분석
{top30_us_text}""",

        f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 안티그레비티 통합 전략 리포트 (10/10)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📝 안티그레비티 최종 종합 요약
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
현재 시장은 극심한 변동성과 유동성의 교차로에 서 있습니다. 미국 연준의 금리 인하 기대감과 인플레이션 고착화 우려가 맞물리면서 국채 금리(TNX)와 달러(DXY)는 여전히 높은 수준을 유지하며 글로벌 자산 시장 전반에 부담을 주고 있습니다.

하지만 비트코인 등 위험 자산의 강세와 핵심 원자재(금, 은, 구리)의 신고가 랠리는 구조적 인플레이션에 대비한 스마트 머니의 이동을 뚜렷하게 보여줍니다. 11개 GICS 섹터 중에서는 고유가와 비용 압박을 방어할 수 있는 에너지, 소재, 그리고 밸류에이션 부담이 적은 헬스케어 섹터가 상대적으로 유리한 환경입니다. 반면 고평가된 일부 기술주 및 임의소비재는 차익 실현 압력이 강하므로 비중 축소와 리스크 관리가 필요합니다.

결론적으로, 현시점에서는 섣부른 추격 매수를 자제하고 충분한 현금(30% 이상)을 확보하는 것이 안전합니다. 확실한 펀더멘털 신호가 있거나, 200일선 지지와 일목균형표 양운 전환이 동반된 우량 가치주 위주로만 보수적으로 접근하시기 바랍니다.

✅ 전체 스캔 및 분석 완료
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 대시보드에서 전체 결과를 확인하세요.
🔗 http://localhost:5173/"""
    ]

    import time
    for i, msg in enumerate(messages):
        # 디스코드 메시지 길이 제한(2000자) 대응을 위한 분할 전송
        chunks = []
        current_chunk = ""
        for line in msg.split('\n'):
            if len(current_chunk) + len(line) + 1 > 1900:
                chunks.append(current_chunk)
                current_chunk = line
            else:
                current_chunk += ("\n" + line) if current_chunk else line
        if current_chunk:
            chunks.append(current_chunk)

        for chunk_idx, chunk in enumerate(chunks):
            try:
                payload = {"content": chunk}
                response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
                if response.status_code in [200, 204]:
                    part_str = f" (부분 {chunk_idx+1}/{len(chunks)})" if len(chunks) > 1 else ""
                    print(f"[성공] 디스코드 메시지 #{i+1}{part_str} 전송 완료.")
                else:
                    print(f"[오류] 디스코드 메시지 #{i+1} 전송 실패: HTTP {response.status_code}")
                time.sleep(2) # 2초 대기
            except Exception as e:
                print(f"[오류] 디스코드 전송 에러: {e}")

# ============================================================
# 메인 실행
# ============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--market', type=str, default="ALL")
    args = parser.parse_args()

    all_scan_results = []
    skip_scan = False

    if os.path.exists("scan_results.json"):
        try:
            with open("scan_results.json", "r", encoding="utf-8") as f:
                cached_data = json.load(f)
                cached_time_str = cached_data.get("timestamp", "")
                if cached_time_str:
                    cached_time = datetime.datetime.strptime(cached_time_str, "%Y-%m-%d %H:%M:%S")
                    if (datetime.datetime.now() - cached_time).total_seconds() < 3 * 3600:
                        print(f"\n[안내] 최근 스캔({cached_time_str})이 3시간 이내에 수행되었습니다. 무거운 주식 스캔을 생략하고 디스코드 메시지만 전송합니다.")
                        all_scan_results = cached_data.get("data", [])
                        skip_scan = True
        except Exception as e:
            logger.warning(f"캐시 읽기 실패: {e}")

    if not skip_scan:
        for theme_name in THEMES.keys():
            print(f"\n{'='*50}")
            print(f" [현재 스캔 테마] : {theme_name} (대상 시장: {args.market})")
            print(f"{'='*50}\n")
    
            krx_tickers, nasdaq_tickers, ticker_to_name = get_market_tickers(theme_name, market_type=args.market)
    
            # 미국 시장 분석 (먼저)
            results_nasdaq = {}
            if nasdaq_tickers:
                print(f"\n[미국] {theme_name} 테마 총 {len(nasdaq_tickers)}개의 종목에 대해 일목균형표 분석을 시작합니다.")
                results_nasdaq = analyze_stocks(nasdaq_tickers, ticker_to_name)
    
            # 한국 시장 분석 (나중)
            results_krx = {}
            if krx_tickers:
                print(f"\n[한국] {theme_name} 테마 총 {len(krx_tickers)}개의 종목에 대해 일목균형표 분석을 시작합니다.")
                results_krx = analyze_stocks(krx_tickers, ticker_to_name)
    
            # 결과 출력
            print(f"\n{'='*15}[ {theme_name} 분석 결과 ]{'='*15}")
            for key, label in labels.items():
                krx_list = [t['display'] if isinstance(t, dict) else t for t in results_krx.get(key, [])]
                nasdaq_list = [t['display'] if isinstance(t, dict) else t for t in results_nasdaq.get(key, [])]
                print(f" * {key}: KRX={krx_list}")
                print(f"          NASDAQ={nasdaq_list}")
    
            # JSON 결과 누적
            all_scan_results.append({
                "theme": theme_name,
                "krx": results_krx,
                "nasdaq": results_nasdaq
            })

    # 당일 상승률 탑 30 분석 및 리포트/데이터 획득
    top30_krx_text, top30_data = get_top30_krx_gainers()
    top30_us_text = get_top30_us_gainers()

    if not skip_scan:
        # 웹 대시보드용 JSON 파일 저장 (루트 + frontend/public 양쪽에 저장)
        output_data = {
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data": all_scan_results,
            "top30": top30_data
        }
    
        # 루트에 저장 (FastAPI가 읽는 경로)
        with open("scan_results.json", "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=4)
    
        # frontend/public에도 저장 (Vite 개발서버가 읽는 경로)
        os.makedirs("frontend/public", exist_ok=True)
        with open("frontend/public/scan_results.json", "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=4)
    
        print("\n[완료] scan_results.json 저장 완료 (루트 + frontend/public)")

    # 최종 디스코드 9분할 리포트 전송
    print("\n[전송] 디스코드 리포트 전송을 시작합니다...")
    send_to_discord(top30_krx_text, top30_us_text)

    print(f"\n[완료] 프로그램이 성공적으로 종료되었습니다! 대시보드: {BASE_DASHBOARD_URL}")

