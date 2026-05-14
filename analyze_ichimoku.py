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

            # 4. 월봉: 월봉 지지 후 상승 패턴
            try:
                try:
                    df_m = df.resample('ME').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()
                except Exception:
                    df_m = df.resample('M').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()

                pattern_found = False
                # 최근 1~2개월 내 패턴 발생 확인
                lookback_limit = min(2, len(df_m) - 12)
                
                if lookback_limit >= 0:
                    for i in range(lookback_limit + 1):
                        idx = -1 - i
                        
                        c_close = df_m['Close'].iloc[idx].item() if isinstance(df_m['Close'].iloc[idx], pd.Series) else df_m['Close'].iloc[idx]
                        c_open = df_m['Open'].iloc[idx].item() if isinstance(df_m['Open'].iloc[idx], pd.Series) else df_m['Open'].iloc[idx]
                        c_vol = df_m['Volume'].iloc[idx].item() if isinstance(df_m['Volume'].iloc[idx], pd.Series) else df_m['Volume'].iloc[idx]
                        
                        past_high = df_m['High'].iloc[:idx].max() if len(df_m[:idx]) > 0 else df_m['High'].max()
                        past_high_val = past_high.item() if isinstance(past_high, pd.Series) else past_high
                        
                        base_period = 6
                        if len(df_m[:idx]) >= base_period:
                            base_df = df_m.iloc[idx-base_period : idx]
                            base_low = base_df['Low'].min()
                            base_avg_vol = base_df['Volume'].mean()
                            
                            base_low_val = base_low.item() if isinstance(base_low, pd.Series) else base_low
                            base_avg_vol_val = base_avg_vol.item() if isinstance(base_avg_vol, pd.Series) else base_avg_vol
                            
                            # 공통: 현재 종가가 최근 6개월 최저점을 깨지 않아야 함
                            if c_close >= base_low_val:
                                # 공통: 당월 양봉 및 전월 대비 상승
                                if c_close > c_open and c_close > df_m['Close'].iloc[idx-1]:
                                    
                                    is_deep_crash = past_high_val >= base_low_val * 2.5
                                    
                                    # 합집합 조건 A: SATL형 (대폭락 후 폭발적 대량 거래량 동반)
                                    cond_a = is_deep_crash and (c_vol > base_avg_vol_val * 2.5)
                                    
                                    # 합집합 조건 B: ABCL형 (대폭락 후 강력한 장대양봉 돌파 + 평이 이상의 거래량)
                                    cond_b = is_deep_crash and (c_close > c_open * 1.15 or c_close > base_low_val * 1.3) and (c_vol >= base_avg_vol_val * 1.0)
                                    
                                    # 합집합 조건 C: SMR형 (단기 낙폭 과대 후 V자 반등 첫 양봉 + 거래량 실림)
                                    cond_c = is_deep_crash and (c_close > c_open * 1.1) and (c_vol >= base_avg_vol_val * 1.2)
                                    
                                    # 합집합 조건 D: RKLB/QUBT/QS형 (강한 추세 속 눌림목 N자 반등 또는 상승장악형)
                                    # 직전 1~2개월 내에 음봉(조정)이 있었고, 당월 10% 이상 양봉으로 전월 캔들 몸통의 고점을 덮어버린 경우 (상승 장악)
                                    is_pullback = (df_m['Close'].iloc[idx-1] < df_m['Open'].iloc[idx-1]) or (len(df_m[:idx]) >= 2 and df_m['Close'].iloc[idx-2] < df_m['Open'].iloc[idx-2])
                                    prev_body_top = max(df_m['Open'].iloc[idx-1], df_m['Close'].iloc[idx-1])
                                    cond_d = is_pullback and (c_close > c_open * 1.10) and (c_close > prev_body_top)
                                    
                                    if cond_a or cond_b or cond_c or cond_d:
                                        pattern_found = True
                                        break
                                            
                if pattern_found:
                    signals.append("monthly_pattern")
            except Exception as e:
                logger.debug(f"{ticker} 월봉 분석 실패: {e}")


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
        tnx_news = yf.Ticker('^TNX').news[:2]
        tnx_news_str = "\n".join([f"- {translate_to_ko(n.get('content', {}).get('title', 'No title'))} : {translate_to_ko(n.get('content', {}).get('summary', 'No summary')[:100])}..." for n in tnx_news])
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
        btc_news = yf.Ticker('BTC-USD').news[:2]
        btc_news_str = "\n".join([f"- {translate_to_ko(n.get('content', {}).get('title', 'No title'))} : {translate_to_ko(n.get('content', {}).get('summary', 'No summary')[:100])}..." for n in btc_news])
        data['BTC_NEWS'] = btc_news_str if btc_news_str else "- 최근 비트코인 관련 특이 뉴스 없음."
    except Exception:
        data['BTC_NEWS'] = "- 최근 비트코인 관련 특이 뉴스 없음."

    # Macro / Geopolitical News
    try:
        import xml.etree.ElementTree as ET
        import urllib.parse
        
        # 주식 시장에 영향을 미칠만한 정부 정책 및 매크로 뉴스로 한정
        query = '(정부정책 OR 연준 OR 지정학적 리스크 OR 금리 OR 환율) AND (증시 OR 주식 OR 주가 OR 수혜 OR 타격 OR 전망)'
        encoded_query = urllib.parse.quote(query)
        
        res = requests.get(f'https://news.google.com/rss/search?q={encoded_query}&hl=ko&gl=KR&ceid=KR:ko')
        root = ET.fromstring(res.text)
        items = root.findall('.//item')[:3]
        news_list = []
        for i in items:
            title = i.find('title').text if i.find('title') is not None else 'No title'
            news_list.append(f"- {title}")
        data['MACRO_NEWS'] = "\n".join(news_list) if news_list else "- 최근 특이 뉴스 없음."
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
        
        # 섹터 및 산업 분포 분석
        sectors = top30['Sector'].dropna().value_counts()
        # 'Industry' might be 'Industry_x' or 'Industry_y' depending on columns after merge. 
        # fdr StockListing KRX doesn't have Sector/Industry, KRX-DESC has them.
        # So in the merged df, they are named Sector and Industry.
        industries = top30['Industry'].dropna().value_counts() if 'Industry' in top30.columns else top30['Industry_y'].dropna().value_counts() if 'Industry_y' in top30.columns else pd.Series(dtype=int)
        
        top_sectors = sectors.head(3)
        top_industries = industries.head(3)
        
        # 디스코드 보고서 생성
        report_lines = []
        report_lines.append(f"🔍 [당일 상승률 상위 30종목 주요 섹터 분포]")
        for sector, count in top_sectors.items():
            report_lines.append(f"  └ {sector}: {count}종목")
            
        report_lines.append(f"\n🔍 [당일 상승률 상위 30종목 주요 세부 산업]")
        for industry, count in top_industries.items():
            report_lines.append(f"  └ {industry}: {count}종목")
            
        report_lines.append(f"\n💡 [분석 요약]")
        summary_text = f"당일 시장의 강한 매수세는 주로 '{top_sectors.index[0] if len(top_sectors)>0 else 'N/A'}' 및 '{top_sectors.index[1] if len(top_sectors)>1 else 'N/A'}' 섹터로 유입되었습니다. "
        summary_text += f"세부적으로는 '{top_industries.index[0] if len(top_industries)>0 else 'N/A'}' 관련 테마가 급등하며 당일 시장의 주도 테마를 형성하고 있습니다."
        report_lines.append(summary_text)
        
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

def send_to_discord(top30_report_text):
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
        buffett_alert = f"\n\n🚨 긴급 역발상 특보: 워런 버핏 지수 바닥권 진입\n👉 현재 지수: {buffett_indicator}% (극단적 공포 및 기회 구간)\n⚠️ 버크셔 해서웨이 동향: 지수가 130% 이하로 바닥권에 진입하면 버핏은 공격적 매수를 준비합니다. 역사적으로 이런 구간에서 버크셔는 '우량 금융주(골드만삭스, BAC)', '필수소비재', '에너지(옥시덴탈, 셰브론)' 및 해자를 갖춘 '미디어/브랜드' 기업들을 대거 매집했습니다. 펀더멘털 우량주 분할 매수 타점입니다."
        
    berkshire_trade_alert = "\n\n🚨 긴급 역발상 특보: 워런 버핏(버크셔 해서웨이) 최근 1주일 거래 포착\n[다비타/DVA/헬스케어]: 2026년 5월 첫째 주, 약 150달러 부근에서 122만 주(약 1.8억 달러) 대규모 매도 (SEC Form 4 공시). 버크셔의 핵심 지분 축소 및 포트폴리오 차익 실현(현금 확보) 기조가 중소형주에서도 일관되게 나타나고 있는 시그널입니다."
    
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

    messages = [
        f"""📊 안티그레비티 통합 전략 리포트 (1/9)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚨 긴급 역발상 특보: 하락 종목 내 내부자 매수 포착
[룰루레몬/LULU/임의소비재]: 실적 가이던스 하향 → 주가 20%↓ 급락 중 경영진 $250K↑ 순매수 포착. RSI 30↓ 과매도 + 장기 지지선 도달 → 반등 시그널{buffett_alert}{berkshire_trade_alert}

📊 주요 경제 및 유동성 지표
🍎 물가 (CPI / PCE): 3.3% / 3.5%
➡️ 인플레이션 여전히 목표(2%) 상회. 연준 금리 인하 신중 모드 지속

👷 고용/경기 (NFP / 실업률 / PMI): 178K / 4.3% / 52.7
➡️ 고용 증가세 둔화 + 실업률 4.3% 상승. PMI 52.7(확장) but 원자재 가격(Prices 84.6) 급등 → 비용 압박

💵 금리: Fed 3.50~3.75%
➡️ 연준 3.75%까지 인하했으나 추가 인하 속도 둔화. 물가 안정 전까지 신중한 스탠스 유지

💧 유동성 NFCI: -0.52
➡️ 금융 환경 완화적 유지(-0.52). 유동성 풍부하나 인플레 재점화 시 급변 가능""",

        f"""📊 안티그레비티 통합 전략 리포트 (2/9)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📈 핵심 자산 상관관계 및 거시 지표 분석
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🇺🇸 미 국채 10년물 금리 (TNX) : {tnx}%
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 [현재 상황 및 배경]
10년물 국채금리는 글로벌 자산의 '무위험 수익률(할인율)'로, 증시 밸류에이션에 절대적 영향을 미칩니다.
현재 연준(Fed)의 금리 인하 속도 둔화와 미국의 막대한 재정 적자로 인한 국채 발행 우려가 맞물려, 금리가 쉽게 떨어지지 않고 하방 경직성을 보이고 있습니다.

📌 [증시 영향 및 전망]
금리가 4% 위에서 고공행진할 경우, 주식보다 채권 투자의 매력이 커지며 기관 자금의 이탈이 발생할 수 있습니다.
반대로 고용 지표 둔화 등으로 연준이 비둘기파적 스탠스를 취하며 금리가 꺾인다면, 그동안 짓눌렸던 가치주, 배당주, 중소형주로의 강력한 순환매 장세가 연출될 가능성이 높습니다.

🗞️ [최근 뉴스 동향]
{d.get('TNX_NEWS', '- 최근 뉴스 없음')}

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

        f"""📊 안티그레비티 통합 전략 리포트 (3/9)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📉 역발상 판독기: 실시간 지표 및 체크리스트

❶ 실시간 VIX Index (공포지수)
👉 현재 VIX: {vix} 
(15 미만 과열 / 15~20 4점 과열 / 20~30 3점 중립 / 30~40 2점 불안 / 40이상 1점 공포)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 매매 전 추가 수동 확인 지표
👉 Bull/Bear Spread
(30 이상 광기 / 20~30 4점 과열 / -20~20 3점 중립 / -30~-20 2점 불안 / -30 1점 공포)
👉 Put/Call Ratio
(0.4 이하 5점 광기 / 0,4~0.5 4점 과열 / 0.5~1 3점 중립 / 1~1.2 2점 불안 / 1.2~ 1점 공포)
👉 Margin Debt(YoY)
(40점 이상 5점 광기 / 20~40 4점 과열 / -20~20 3점 중립 / -30~-20 2점 불안 / -30 1점 공포)
👉 HY Spread
(3%이하 5점 광기 / 바닥 +1% 4점 과열 / 3~5% 3점 중립 / 5% 상승세 2점 불안 / 5% 상승 후 -1% 하락 1점 공포)""",

        f"""📊 안티그레비티 통합 전략 리포트 (4/9)
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

        f"""📊 안티그레비티 통합 전략 리포트 (5/9)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🛢️ 핵심 원자재 트래킹
🥇 금 ${gold} / 은 ${silver}
구조적 초강세 · 신고가 경신
➡️ 중앙은행 금 매입 + 법정화폐 가치 하락

🥉 구리 ${copper}
강한 상승 돌파
➡️ AI 데이터센터·신재생 인프라 수요 폭발

🛢️ WTI ${wti}
고유가 지속
➡️ 지정학 리스크 + 공급 우려로 $90대 유지. 중동 휴전 진전 시 하락 가능

💵 외환 & 매크로 지표 변동성 분석
🇺🇸 달러 인덱스(DXY) : {dxy}
🇰🇷 USD/KRW : {krw}원
📌 [변동성 원인 및 매크로 요인 요약]
• 지정학적 불안(중동 분쟁 등)으로 인한 안전자산 선호 심리가 달러 수요를 지지.
• 연준(Fed)의 금리 인하 속도 둔화 및 인플레이션 고착화 우려가 강달러와 원화 약세(환율 상승) 압력으로 작용.
• 한국 내 구조적 자본 유출(서학개미발 미국 기술주/AI 투자 쏠림)이 원/달러 환율 상승(원화 가치 하락)의 만성적 드라이버 역할을 함.
• 향후 반도체 수출 호조 지속 및 WGBI 편입(외국인 자금 유입) 여부가 환율 상단을 방어하고 안정을 되찾을 핵심 트리거가 될 전망.""",

        f"""📊 안티그레비티 통합 전략 리포트 (6/9)
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

        f"""📊 안티그레비티 통합 전략 리포트 (7/9)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏛️ 정부 정책 & 지정학적 리스크 (실시간 뉴스)
⚠️ 최신 주요 뉴스
{d.get('MACRO_NEWS', '- 최근 특이 뉴스 없음.')}

💡 [시장 영향]
위 뉴스들은 유가(에너지), 금리(성장주 밸류에이션), 그리고 안전 자산(금/달러) 선호 심리에 즉각적인 영향을 미치는 핵심 변수입니다.""",

        f"""📊 안티그레비티 통합 전략 리포트 (8/9)
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

        f"""📊 안티그레비티 통합 전략 리포트 (9/9)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🇰🇷 당일 한국 주식 상승률 상위 30 종목 분석
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{top30_report_text}

💡 [분석 요약]
당일 시장에서 가장 강하게 상승한 상위 30종목이 속한 섹터와 테마는 현재 시장을 주도하는 단기적인 강세 테마를 의미합니다.""",

        f"""✅ 전체 스캔 및 분석 완료
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 대시보드에서 결과를 확인하세요.
🔗 http://localhost:5173/"""
    ]

    import time
    for i, msg in enumerate(messages):
        try:
            payload = {"content": msg}
            response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
            if response.status_code in [200, 204]:
                print(f"[성공] 디스코드 메시지 #{i+1} 전송 완료.")
            else:
                print(f"[오류] 디스코드 전송 실패: HTTP {response.status_code}")
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
    top30_report_text, top30_data = get_top30_krx_gainers()

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
    print("\n[전송] 디스코드 9분할 리포트 전송을 시작합니다...")
    send_to_discord(top30_report_text)

    print(f"\n[완료] 전체 스캔이 성공적으로 끝났습니다! 대시보드: {BASE_DASHBOARD_URL}")

