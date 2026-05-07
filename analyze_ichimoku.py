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

            # 역사적 고점 돌파 확인을 위해 period="max" 로 전체 기간 다운로드
            df = yf.download(ticker, period="max", interval="1d", progress=False)
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
                    market_cap = t_obj.fast_info.get('market_cap', 0)
                    if market_cap is None or market_cap == 0 or pd.isna(market_cap):
                        market_cap = t_obj.info.get('marketCap', 0)
                    if market_cap is None or pd.isna(market_cap):
                        market_cap = 0
                except Exception as e:
                    logger.debug(f"{ticker} 시가총액 조회 실패: {e}")

            signals = []

            # 1. 양운 전환 (음운에서 양운으로 크로스오버/전환)
            if df['lead_a'].iloc[-1] > df['lead_b'].iloc[-1] and df['lead_a'].iloc[-2] <= df['lead_b'].iloc[-2]:
                signals.append("cloud_twist")

            # 2. 최근 5년(실행일 기준) 전고점 돌파 (약 1260 거래일 기준 최고가 돌파 또는 2% 이내 접근)
            recent_5y_df = df.iloc[-1260:] if len(df) > 1260 else df
            five_year_high = recent_5y_df['High'].max()
            if df['Close'].iloc[-1] >= five_year_high * 0.98:
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

            # 4. 월봉: 바닥권 다지기 및 긴 밑꼬리 (Hammer) 패턴
            try:
                try:
                    df_m = df.resample('ME').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()
                except Exception:
                    df_m = df.resample('M').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()

                if len(df_m) >= 6:
                    lookback = min(len(df_m), 12)
                    year_high = df_m['High'].iloc[-lookback:].max()
                    year_low = df_m['Low'].iloc[-lookback:].min()
                    
                    curr_close = df_m['Close'].iloc[-1]
                    curr_open = df_m['Open'].iloc[-1]
                    curr_high = df_m['High'].iloc[-1]
                    curr_low = df_m['Low'].iloc[-1]

                    prev_close = df_m['Close'].iloc[-2]
                    prev_open = df_m['Open'].iloc[-2]
                    prev_high = df_m['High'].iloc[-2]
                    prev_low = df_m['Low'].iloc[-2]

                    # 1. 바닥권 조건: 고점 대비 40% 이상 하락했거나, 1년 변동폭의 하위 30% 이내 위치
                    is_bottom = False
                    if year_high > year_low:
                        if curr_close <= year_high * 0.6 or ((curr_close - year_low) / (year_high - year_low)) <= 0.3:
                            is_bottom = True

                    # 2. 긴 밑꼬리 (해머/망치형) 판별 함수
                    # 밑꼬리가 몸통의 1.5배 이상, 전체 캔들 길이의 50% 이상 차지
                    def check_hammer(o, h, l, c):
                        body = abs(c - o)
                        lower_wick = min(o, c) - l
                        total = h - l
                        if total == 0: return False
                        return (lower_wick >= body * 1.5) and (lower_wick >= total * 0.5)

                    is_curr_hammer = check_hammer(curr_open, curr_high, curr_low, curr_close)
                    is_prev_hammer = check_hammer(prev_open, prev_high, prev_low, prev_close)

                    # 조건 A: 바닥권 + 현재 양봉(상승중) + 최근 2개월 내 해머 패턴 발생
                    pattern_a = is_bottom and (curr_close > curr_open) and (is_curr_hammer or is_prev_hammer)

                    curr_vol = df_m['Volume'].iloc[-1]
                    prev_vol = df_m['Volume'].iloc[-2]

                    # 3. 추가 패턴: 더이상 떨어지지 않고 지지하면서 거래량이 점점 늘어나는 양봉
                    is_support = False
                    is_vol_increasing = False
                    
                    if len(df_m) >= 3:
                        recent_lows = df_m['Low'].iloc[-3:]
                        # 최근 3개월간 저점이 큰 하락 없이 15% 이내에서 횡보/지지
                        if (recent_lows.max() - recent_lows.min()) / (recent_lows.min() + 1e-9) <= 0.15:
                            is_support = True
                        
                        # 거래량이 이전 달 대비 10% 이상 점진적 증가
                        if curr_vol > prev_vol * 1.1:
                            is_vol_increasing = True

                    pattern_b = is_bottom and (curr_close > curr_open) and is_support and is_vol_increasing

                    # 4. 추가 패턴 (이미지 학습): 상승 장악형 / V자 급반등
                    # 이전 달 음봉을 완전히 덮는(장악하는) 거대한 양봉이며 거래량이 폭발하는 형태
                    is_prev_red = prev_close < prev_open
                    is_curr_green = curr_close > curr_open
                    
                    # 상승 장악형 조건: 현재 종가가 이전 시가를 넘어서고, 현재 시가가 이전 종가 부근에서 시작
                    is_engulfing = is_prev_red and is_curr_green and (curr_close >= prev_open) and (curr_open <= prev_close * 1.05)
                    
                    # 몸통 크기 비교: 이번 양봉 몸통이 이전 음봉 몸통보다 큼
                    is_large_body = (curr_close - curr_open) >= (prev_open - prev_close) if is_prev_red else False
                    
                    # 거래량 폭발: 이전 달 대비 50% 이상 급증
                    is_vol_spike = (curr_vol >= prev_vol * 1.5) if prev_vol > 0 else False

                    pattern_c = is_bottom and is_engulfing and is_large_body and is_vol_spike

                    # 5. 추가 패턴 (이미지 학습): 강력한 해머형 (Liquidity Sweep)
                    # 이전 저점을 깨고(휩소) 강하게 말아올리며 거래량이 증가하는 양봉 해머
                    def check_strong_hammer(o, h, l, c):
                        body = abs(c - o)
                        lower_wick = min(o, c) - l
                        total = h - l
                        if total == 0: return False
                        # 몸통보다 밑꼬리가 2배 이상 길고, 전체 캔들의 60% 이상을 밑꼬리가 차지
                        return (lower_wick >= body * 2.0) and (lower_wick >= total * 0.6)

                    is_strong_hammer = check_strong_hammer(curr_open, curr_high, curr_low, curr_close)
                    
                    # 전월 저점 하향 돌파 후 전월 종가 이상으로 회복 (유동성 스윕)
                    is_sweep = (curr_low < prev_low) and (curr_close > prev_close)
                    
                    # 거래량 증가 (전월 대비)
                    is_vol_up = (curr_vol > prev_vol) if prev_vol > 0 else False

                    pattern_d = is_bottom and is_prev_red and is_curr_green and is_strong_hammer and is_sweep and is_vol_up

                    # 6. 추가 패턴 (이미지 학습): 장기 횡보 박스권 돌파 (Box Breakout)
                    # 바닥권에서 수개월간 좁은 박스권(횡보)을 형성하며 에너지를 응축한 뒤, 대량 거래량을 동반하며 상단을 강하게 돌파하는 장대양봉
                    is_box_breakout = False
                    if len(df_m) >= 6:
                        # 최근 1개월(현재)을 제외한 과거 5개월간의 데이터 (박스권)
                        box_df = df_m.iloc[-6:-1]
                        box_high = box_df['High'].max()
                        box_low = box_df['Low'].min()
                        
                        # 1. 좁은 박스권: 5개월간 최고-최저 밴드가 저점 대비 35% 이내로 수렴된 상태
                        if box_low > 0 and (box_high - box_low) / box_low <= 0.35:
                            # 2. 강력한 상방 돌파: 당월 종가가 5개월 박스권 고점을 명확히 뚫어낸 양봉
                            if curr_close > box_high and curr_close > curr_open:
                                # 3. 매수세(거래량) 폭발: 당월 거래량이 박스권 5개월 평균 거래량보다 50% 이상 급증
                                avg_box_vol = box_df['Volume'].mean()
                                if avg_box_vol > 0 and curr_vol >= avg_box_vol * 1.5:
                                    is_box_breakout = True

                    pattern_e = is_bottom and is_box_breakout

                    # 7. 추가 패턴 (이미지 학습): 둥근 바닥형 다중 저항 돌파 (Rounding Bottom Breakout)
                    # 바닥권에서 여러 달 동안 잔잔한 캔들을 만들며 방향을 모색하다가, 
                    # 이전 3개월의 고점을 압도적인 거래량과 함께 단숨에 10% 이상 뚫어내는 장대양봉
                    is_rounding_breakout = False
                    if len(df_m) >= 4:
                        # 과거 3개월간의 데이터 (현재 제외)
                        past_3m_df = df_m.iloc[-4:-1]
                        past_3m_high = past_3m_df['High'].max()
                        past_3m_avg_vol = past_3m_df['Volume'].mean()
                        
                        # 1. 강력한 저항 돌파: 이번 달 종가가 과거 3개월 최고점 대비 10% 이상 높게 마감
                        if curr_close > past_3m_high * 1.1 and curr_close > curr_open:
                            # 2. 거래량 폭발: 과거 3개월 평균 거래량보다 2배(200%) 이상 급증
                            if past_3m_avg_vol > 0 and curr_vol >= past_3m_avg_vol * 2.0:
                                # 3. 모멘텀 캔들: 윗/밑꼬리보다 몸통이 압도적으로 큰 장대양봉 (몸통이 전체의 60% 이상)
                                curr_body = curr_close - curr_open
                                curr_total = curr_high - curr_low
                                if curr_total > 0 and curr_body >= curr_total * 0.6:
                                    is_rounding_breakout = True

                    pattern_f = is_bottom and is_rounding_breakout

                    # 8. 추가 패턴 (이미지 학습): 샛별형(Morning Star) 완성 및 상승 가속
                    # 바닥권에서 음봉 이후 작은 양봉으로 하락을 멈추고, 그 다음 달에 거래량을 동반한 거대한 장대양봉으로 추세를 완전히 되돌리는 패턴
                    is_morning_star_explosion = False
                    if len(df_m) >= 3:
                        prev2_open = df_m['Open'].iloc[-3]
                        prev2_close = df_m['Close'].iloc[-3]
                        
                        is_prev2_red = prev2_close < prev2_open
                        is_prev_green = prev_close > prev_open
                        
                        # 전전달 음봉, 전달 양봉 (하락 멈춤 및 반전 시작)
                        if is_prev2_red and is_prev_green:
                            prev_body = prev_close - prev_open
                            curr_body = curr_close - curr_open
                            # 이번 달이 전달의 양봉을 압도(2배 이상)하는 거대한 장대양봉 (가속)
                            if curr_close > curr_open and curr_body >= prev_body * 2.0:
                                # 이번 달 종가가 전전달(음봉)의 시가를 완전히 넘어서며 하락분 모두 만회
                                if curr_close > prev2_open:
                                    # 거래량 증가 확인 (전달 대비 1.5배 이상)
                                    if curr_vol >= prev_vol * 1.5:
                                        is_morning_star_explosion = True

                    pattern_g = is_bottom and is_morning_star_explosion

                    if pattern_a or pattern_b or pattern_c or pattern_d or pattern_e or pattern_f or pattern_g:
                        signals.append("monthly_pattern")
            except Exception as e:
                logger.debug(f"{ticker} 월봉 분석 실패: {e}")


            if signals:
                ticker_data = {
                    "display": display_name,
                    "ticker": ticker,
                    "name": name,
                    "analysis": {
                        "price": float(df['Close'].iloc[-1]) if not pd.isna(df['Close'].iloc[-1]) else 0.0,
                        "market_cap": 0 if pd.isna(market_cap) else int(market_cap),
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
        "nasdaq": ["Software", "Hardware", "Semiconductor", "IT", "Information Technology", "Electronic"]
    },
    "커뮤니케이션 (통신, 미디어, 엔터테인먼트, 인터랙티브 미디어 및 서비스)": {
        "krx": ["통신", "미디어", "엔터테인먼트", "방송", "영화", "인터넷", "게임"],
        "nasdaq": ["Communication", "Media", "Entertainment", "Interactive Media", "Telecom", "Broadcasting"]
    },
    "임의소비재 (자동차 및 부품, 내구소비재, 의류, 레저, 호텔/레스토랑)": {
        "krx": ["자동차", "내구소비재", "의류", "레저", "호텔", "레스토랑", "여행", "소비재"],
        "nasdaq": ["Automobile", "Auto Parts", "Consumer Discretionary", "Apparel", "Leisure", "Hotel", "Restaurant"]
    },
    "필수소비재 (식음료, 유통, 가정용품, 개인용품, 담배)": {
        "krx": ["식음료", "유통", "가정용품", "개인용품", "담배", "생활용품", "화장품"],
        "nasdaq": ["Consumer Staples", "Food", "Beverage", "Retail", "Household", "Personal", "Tobacco"]
    },
    "헬스케어 (제약, 생명공학(바이오), 의료기기, 헬스케어 서비스 및 장비)": {
        "krx": ["제약", "바이오", "생명공학", "의료기기", "헬스케어"],
        "nasdaq": ["Healthcare", "Pharmaceutical", "Biotechnology", "Medical", "Health Care"]
    },
    "금융 (은행, 보험, 다각화된 금융 서비스, 소비자 금융)": {
        "krx": ["은행", "보험", "금융", "증권", "지주"],
        "nasdaq": ["Financial", "Bank", "Insurance", "Consumer Finance", "Capital Markets"]
    },
    "산업재 (자본재, 기계, 상업/전문 서비스, 운송 및 물류)": {
        "krx": ["산업재", "기계", "상업", "운송", "물류", "건설", "조선", "항공"],
        "nasdaq": ["Industrial", "Capital Goods", "Machinery", "Commercial Services", "Transportation", "Logistics", "Aerospace"]
    },
    "소재 (화학, 건설자재, 금속 및 채광, 종이/포장재)": {
        "krx": ["화학", "건설자재", "금속", "채광", "종이", "포장재", "철강", "비철금속"],
        "nasdaq": ["Material", "Chemical", "Construction Material", "Metals", "Mining", "Paper", "Packaging"]
    },
    "에너지 (석유/가스 탐사 및 생산, 정제, 에너지 장비 및 서비스)": {
        "krx": ["에너지", "석유", "가스", "정제"],
        "nasdaq": ["Energy", "Oil", "Gas", "Exploration", "Refining", "Energy Equipment"]
    },
    "유틸리티 (전력, 가스, 수도, 다각화된 재생에너지)": {
        "krx": ["전력", "수도", "유틸리티", "재생에너지", "환경"],
        "nasdaq": ["Utility", "Electric", "Water", "Renewable"]
    },
    "부동산 (부동산 관리 및 개발, 리츠(REITs))": {
        "krx": ["부동산", "리츠", "리츠(REITs)", "건설업"],
        "nasdaq": ["Real Estate", "REIT", "Property Management", "Development"]
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
    "monthly_pattern": "🛡️ 월봉: 유의미한 패턴 및 지지",
    "cloud_twist": "🟢 양운 전환: 음운에서 양운 크로스오버",
    "ma200_support_breakout": "📈 200일선: 지지 또는 돌파",
    "5yr_high_breakout": "🚀 5년 전고점 돌파: 새로운 주가 레벨 진입"
}

def send_to_discord():
    if not DISCORD_WEBHOOK_URL:
        print("\n[안내] 디스코드 웹훅 URL이 설정되지 않아 메시지를 전송하지 않습니다. (.env 파일을 확인하세요)")
        return

    messages = [
        """[메시지 #1: 자동 전송]

📊 **[안티그레비티] 통합 전략 리포트 (1/8)** 📊

🚨 **[긴급 역발상 특보: 하락 종목 내 내부자 매수 포착]**
- [룰루레몬/LULU/임의소비재]: 최근 실적 가이던스 하향으로 주가가 20% 이상 급락한 가운데, 핵심 경영진(CEO 및 이사)의 $250,000 이상 순매수가 포착되었습니다. 주간 RSI 30 이하 과매도 권역 진입 및 강력한 장기 지지선 도달로 반등(바닥) 시그널이 발생했습니다.

**1. 주요 경제 및 유동성 지표 (연준 핵심 & NFCI)**
- 🍎 **[물가] 소비자물가지수 (CPI) / 개인소비지출 (PCE):** 3.8% (전월: 3.5%) / 3.5% (전월: 3.2%) 
  ➡️ **[AI 매크로 인사이트]:** 
  에너지 가격 급등으로 인플레이션이 재점화되며 연준의 스탠스가 매파적으로 선회하고 있습니다.
  과거 1970년대 오일쇼크 및 2022년 물가 반등 국면에서 S&P 500은 밸류에이션 축소(Multiple Contraction)를 겪으며 고점 대비 15% 이상 하락하는 패턴을 보였습니다.
  현재 지수의 높은 P/E 부담과 맞물려 강력한 단기 조정 트리거로 작용할 가능성이 높습니다.
- 👷 **[고용/경기] 비농업 고용지수 (NFP) / 실업률 / ISM 구매관리자지수 (PMI):** 165K (전월: 210K) / 4.1% (전월: 4.0%) / 48.5 (전월: 49.2) 
  ➡️ **[AI 매크로 인사이트]:** 
  신규 고용 창출 둔화와 실업률의 완만한 상승, 그리고 제조업 PMI의 기준선(50) 하회는 전형적인 경기 둔화 초입의 신호입니다.
  물가는 오르는데 경기는 식어가는 스태그플레이션 우려가 점증하며, 이는 과거 S&P 500 실적 장세에서 기업들의 마진 압착으로 이어져 EPS 전망치 하향을 유발했습니다.
  방어적 성격의 가치주 및 필수소비재로의 자금 이동이 가속화될 수 있는 매크로 환경입니다.
- 💵 **[금리] Fed 기준금리 현황:** 4.50% (전월: 4.50%) 
  ➡️ **[AI 매크로 인사이트]:** 
  금리 인하 기대감이 후퇴하고 고금리가 장기화(Higher for Longer)되면서 시장 국채 금리(10년물 4.4%대)가 재상승하고 있습니다.
  과거 고금리 유지기에는 부채 비율이 높고 현금 창출력이 부족한 한계 기업들의 신용 리스크가 부각되어 지수 전체의 변동성이 확대되었습니다.
  반면, 자본 조달 없이 잉여현금흐름(FCF)을 꾸준히 창출하는 우량 대형주로 수급이 극단적으로 쏠리는 양극화 장세가 예상됩니다.
- 💧 **[유동성] NFCI (금융환경지수):** -0.45 (전주: -0.52) 
  ➡️ **S&P 500 연동:** 
  지수가 마이너스 영역에 머물러 금융 환경은 여전히 완화적이나, 전주 대비 상승하며 유동성 축소 경계감이 반영되고 있습니다.
  단기적인 충격은 제한적일 수 있으나 추세 반전 시 S&P 500의 상승 모멘텀을 심각하게 저해할 수 있습니다.""",

        """[메시지 #2: 1번 전송 직후 자동 전송]

📊 **[안티그레비티] 통합 전략 리포트 (2/8)** 📊

**2. 📉 역발상 판독기: 5대 지표 세부 분석 (S&P 500 연동)**
(※ 1~5점 부여. 1:공포 / 2:불안 / 3:중립 / 4:과열 / 5:광기)
- ❶ Bull/Bear Spread ➡️ **[3점]** 강세론과 약세론이 팽팽하게 맞서며 매크로 불확실성에 따른 방향성 탐색 구간이 지속되고 있습니다.
- ❷ Put/Call Ratio ➡️ **[3점]** 0.85 수준으로 시장 참여자들이 풋옵션 헷지를 점진적으로 늘리고 있으나, 아직 극단적인 공포나 과열 쏠림은 없습니다.
- ❸ VIX Index ➡️ **[3점]** 17.38로 역사적 평균 수준이나, 하단 지지를 확인하며 단기 변동성 폭발을 준비하는 스프링 압축 구간입니다.
- ❹ Margin Debt(YoY) ➡️ **[4점]** 이전 랠리 동안 누적된 신용잔고가 여전히 높은 수준을 유지하고 있어, 하락 전환 시 레버리지 투매(반대매매) 리스크가 큽니다.
- ❺ HY Spread ➡️ **[4점]** 3.2% 수준으로 하이일드 채권 시장이 경기 침체와 신용 위험을 극도로 과소평가하는 complacency(안일함) 장세입니다.
- 🧭 **[역발상 종합 점수]: 3.40 / 5.0** ➡️ **판단:** 시장 심리는 표면적으로 관망(중립) 상태이나, 레버리지와 신용 스프레드 지표가 숨겨진 과열을 가리키고 있습니다. 사소한 악재나 물가 지표 쇼크에도 대규모 차익 실현 물량이 쏟아질 수 있는 얇은 얼음판 위를 걷는 상황입니다.""",

        """[메시지 #3: 2번 전송 직후 자동 전송]

📊 **[안티그레비티] 통합 전략 리포트 (3/8)** 📊

**3. 🟢 11개 GICS 섹터 맞춤 전략**
- 🟢 확대: 에너지, 헬스케어, 소재
- 🟡 중립: 금융, 유틸리티, 필수소비재, 산업재
- 🔴 축소: IT, 커뮤니케이션, 임의소비재, 부동산
- 💡 **전략 근거:** 유가 100달러 돌파 및 스태그플레이션 우려로 에너지와 원자재(소재) 섹터의 실적 방어력이 돋보이며, 밸류에이션 부담이 적은 헬스케어가 대안으로 부상 중입니다. 반면 고금리 장기화에 취약한 부동산과 소비 둔화 타격을 받는 임의소비재, 이미 역대 최고 밸류에이션(P/E 29배)에 도달해 차익 실현 압력이 거센 IT 및 커뮤니케이션 섹터는 비중 축소가 필수적입니다.""",

        """[메시지 #4: 3번 전송 직후 자동 전송]

📊 **[안티그레비티] 통합 전략 리포트 (4/8)** 📊

**4. 🛢️ 핵심 원자재 트래킹 및 S&P 500 연동 인사이트**
- 🥇 **금(Gold) / 은(Silver):** $4,646.00 / $75.69 (구조적 초강세 및 신고가 경신)
  ➡️ **[AI 매크로 인사이트]:** 
  법정 화폐 가치 하락과 중앙은행들의 지속적인 금 매입으로 귀금속이 강력한 랠리를 펼치고 있습니다.
  과거 인플레이션 헤지 수요가 폭발했던 시기처럼, 현재 S&P 500 대비 금/은의 상대 강도가 극도로 높아지며 주식 시장의 자금 이탈이 뚜렷하게 관찰됩니다.
- 🥉 **구리(Copper) / 원자재:** $6.07 (강한 상승 돌파)
  ➡️ **[AI 매크로 인사이트]:** 
  AI 데이터센터 전력망 구축 및 신재생 인프라 수요 폭발로 인해 닥터 코퍼가 역대 최고가 수준을 유지하고 있습니다.
  이는 산업 전반의 비용 증가를 초래하여 원자재 기업에는 호재이나, S&P 500 소비재 기업들의 영업 이익률을 압박할 핵심 요인입니다.
- 🛢️ **국제 유가(WTI/Brent):** $100.63 (저항선 돌파 및 공급 우려 심화)
  ➡️ **[AI 매크로 인사이트]:** 
  지정학적 갈등 고조와 타이트한 원유 공급망으로 인해 유가가 심리적 저항선인 100달러를 돌파했습니다.
  1970년대식 비용 인상(Cost-push) 인플레이션을 유발하여, 증시 전반의 밸류에이션 디레이팅(할인)을 강제하는 매크로 뇌관으로 작용 중입니다.""",

        """[메시지 #5: 4번 전송 직후 자동 전송]

📊 **[안티그레비티] 통합 전략 리포트 (5/8)** 📊

**5. ⚖️ 밸류에이션 (P/E) 상태**
(※ P/E 점수 기준: 19 이상 ➡️ 5점(광기) / 18~19 ➡️ 4점(과열) / 16~18 ➡️ 3점(중립) / 15~16 ➡️ 2점(불안) / 15 이하 ➡️ 1점(공포))
- **시장 전체 P/E:** 5점 (22.5배) - 광기
- **11개 GICS 섹터별 P/E 리스트:**
  * IT (소프트웨어, 하드웨어, 반도체, IT 기기 및 서비스): 5점 (29.5배) - 광기
  * 커뮤니케이션 (통신, 미디어, 엔터테인먼트, 인터랙티브 미디어 및 서비스): 5점 (21.0배) - 광기
  * 임의소비재 (자동차 및 부품, 내구소비재, 의류, 레저, 호텔/레스토랑): 5점 (24.5배) - 광기
  * 필수소비재 (식음료, 유통, 가정용품, 개인용품, 담배): 5점 (19.5배) - 광기
  * 헬스케어 (제약, 생명공학(바이오), 의료기기, 헬스케어 서비스 및 장비): 3점 (17.5배) - 중립
  * 금융 (은행, 보험, 다각화된 금융 서비스, 소비자 금융): 2점 (15.2배) - 불안
  * 산업재 (자본재, 기계, 상업/전문 서비스, 운송 및 물류): 5점 (20.0배) - 광기
  * 소재 (화학, 건설자재, 금속 및 채광, 종이/포장재): 4점 (18.2배) - 과열
  * 에너지 (석유/가스 탐사 및 생산, 정제, 에너지 장비 및 서비스): 1점 (14.5배) - 공포
  * 유틸리티 (전력, 가스, 수도, 다각화된 재생에너지): 3점 (16.5배) - 중립
  * 부동산 (부동산 관리 및 개발, 리츠(REITs)): 5점 (32.0배) - 광기""",

        """[메시지 #6: 5번 전송 직후 자동 전송]

📊 **[안티그레비티] 통합 전략 리포트 (6/8)** 📊

**6. 🎙️ 스마트 큐레이션 (오선 / 김피비 / 전인구 / 소수몽키)**
- **📌 주간 메인 테마:** 빅테크 실적 고점 논란과 스태그플레이션 시대의 자산 배분
- **📺 [오선의 미증시] 핵심 내러티브:** 고금리와 유가 폭등 속에서도 잉여현금창출력을 증명한 1위 기술주(빅테크)로만 수급이 압축되는 극단적 디커플링 장세를 강조했습니다.
- **📺 [경제왕 김피비] 핵심 인사이트:** 유가 100달러 돌파가 연준의 금리 인하 사이클을 무너뜨렸으며, 하반기 하이일드 채권 시장발 크레딧(신용) 이벤트 폭발을 강력히 경고했습니다.
- **📺 [전인구경제연구소] 핵심 자산배분:** 금과 은의 멈추지 않는 신고가 랠리를 짚으며, 인플레이션 헷지 자산과 현금 흐름이 탄탄한 고배당 가치주로 포트폴리오를 대피시킬 것을 주문했습니다.
- **📺 [소수몽키] 핵심 투자아이디어:** M7 랠리의 한계가 노출됨에 따라, 가격 전가력을 갖춘 필수소비재와 숨겨진 전력 인프라/에너지 수혜주로 단기 스윙 기회를 노려야 한다고 분석했습니다.
- **🔥 안티그레비티 종합 코멘트:** 네 전문가 모두 AI 주도 장세의 후반부 진입 및 매크로 악재(유가 폭등, 고금리 고착화)의 파괴력을 공통으로 우려하고 있습니다. 맹목적인 지수 추종을 멈추고 현금을 확보하며, 실적과 밸류에이션 매력이 검증된 방어 섹터로 포지션을 서둘러 이동해야 할 중대 변곡점입니다.""",

        """[메시지 #7: 6번 전송 직후 자동 전송]

📊 **[안티그레비티] 통합 전략 리포트 (7/8)** 📊

**7. 🏛️ 정부 정책 & 지정학적 리스크 (최근 1개월 핵심)**
- **지정학적 리스크:** 중동 산유국들의 감산 기조와 국지전 확전으로 인해 호르무즈 해협을 비롯한 주요 에너지 운송로의 간헐적 봉쇄 위험이 최고조에 달하며, 이는 유가 100달러 재돌파의 핵심 촉매가 되었습니다.
- **정부 정책 대응:** 미국 행정부는 치솟는 에너지 가격과 인플레이션을 방어하기 위해 전략비축유(SPR) 추가 방출을 검토하는 한편, 중국을 향한 AI 반도체 수출 통제망을 더욱 옥죄며 첨단 기술 패권 경쟁의 전선을 넓히고 있습니다.""",

        """[메시지 #8: 7번 전송 직후 자동 전송]

📊 **[안티그레비티] 통합 전략 리포트 (8/8)** 📊

**8. 📝 안티그레비티 최종 행동 지침 (Executive Summary)**
- **현재 시장 요약:** 밸류에이션(P/E 22.5배)은 광기 영역에 도달했으나, 유가 100달러 돌파가 스태그플레이션 공포를 소환하고 있는 살얼음판 장세.
- **행동 지침:** 
  1. **[현금 확보]** IT 및 부동산 등 이미 5점(광기) 영역에 진입한 고평가 섹터의 신규 추격 매수를 전면 중단하고, 반등 시 비중을 축소하여 **목표 현금 비중을 최소 30% 이상** 확보하십시오.
  2. **[로테이션]** 기술주에 쏠린 맹목적 자금을 유가 및 금 가격 상승의 직접적 수혜를 누리며 아직 1점(공포)~2점 영역인 **에너지, 금융, 소재 섹터**의 저평가 가치주로 대거 이동시키십시오.
  3. **[타점 대기]** VIX가 하단을 다지고 있어 언제든 시장 변동성이 폭발할 수 있습니다. 일목균형표상 **강력한 200일선 지지와 확실한 양운 전환**이 동반된 종목만 보수적으로 접근하십시오.
  4. **[예외 매수]** 매크로 악재로 동반 급락했으나 펀더멘털이 견고하고 경영진의 **$100,000 이상 대규모 내부자 매수**가 발생한 기업(예: LULU)에 한해서만 철저한 분할 스윙 트레이딩을 허용합니다.""",

        """[최종 메시지: 8번 전송 직후 자동 전송]

전체 스캔 및 분석 완료
대시보드에서 결과를 확인하세요.
대시보드
http://localhost:5173/"""
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

        # 디스코드 전송은 마지막에 8분할로 한 번만 전송하므로 테마별 전송 생략

        # JSON 결과 누적
        all_scan_results.append({
            "theme": theme_name,
            "krx": results_krx,
            "nasdaq": results_nasdaq
        })

    # 웹 대시보드용 JSON 파일 저장 (루트 + frontend/public 양쪽에 저장)
    output_data = {
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data": all_scan_results
    }

    # 루트에 저장 (FastAPI가 읽는 경로)
    with open("scan_results.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=4)

    # frontend/public에도 저장 (Vite 개발서버가 읽는 경로)
    os.makedirs("frontend/public", exist_ok=True)
    with open("frontend/public/scan_results.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=4)

    print("\n[완료] scan_results.json 저장 완료 (루트 + frontend/public)")

    # 최종 디스코드 8분할 리포트 전송
    print("\n[전송] 디스코드 8분할 리포트 전송을 시작합니다...")
    send_to_discord()

    print(f"\n[완료] 전체 스캔이 성공적으로 끝났습니다! 대시보드: {BASE_DASHBOARD_URL}")
