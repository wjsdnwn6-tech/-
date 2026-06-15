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
import pickle
from dotenv import load_dotenv

load_dotenv()

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 로깅 설정
logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# ============================================================
# 진행 상황 추적 유틸리티
# ============================================================
import time as _global_time
_SCRIPT_START = _global_time.time()

class StageTracker:
    """전체 스캔 파이프라인의 단계별 진행 상황을 추적합니다."""
    def __init__(self, total_stages=8):
        self.start_time = _SCRIPT_START
        self.stage_start = _global_time.time()
        self.current_stage = 0
        self.total_stages = total_stages

    def start_stage(self, name):
        self.current_stage += 1
        self.stage_start = _global_time.time()
        elapsed = _global_time.time() - self.start_time
        mins, secs = divmod(int(elapsed), 60)
        print(f"\n{'━'*60}")
        print(f"  ⏱️  [{self.current_stage}/{self.total_stages}] {name}")
        print(f"  📍 총 경과 시간: {mins}분 {secs}초")
        print(f"{'━'*60}", flush=True)

    def end_stage(self, summary=""):
        elapsed = _global_time.time() - self.stage_start
        mins, secs = divmod(int(elapsed), 60)
        msg = f"  ✅ 완료 ({mins}분 {secs}초 소요)"
        if summary:
            msg += f" — {summary}"
        print(msg, flush=True)

    def print_total(self):
        elapsed = _global_time.time() - self.start_time
        mins, secs = divmod(int(elapsed), 60)
        print(f"\n{'━'*60}")
        print(f"  🏁 전체 스캔 완료! 총 소요 시간: {mins}분 {secs}초")
        print(f"{'━'*60}", flush=True)

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
    df_nasdaq = fdr.StockListing('NASDAQ')
    df_nyse = fdr.StockListing('NYSE')
    df_amex = fdr.StockListing('AMEX')
    DF_US = pd.concat([df_nasdaq, df_nyse, df_amex], ignore_index=True)
    DF_US.drop_duplicates(subset=['Symbol'], inplace=True)
    print(f"  > 미국 주식 데이터 (NASDAQ, NYSE, AMEX 통합) {len(DF_US)}개 종목 로드 완료.")
except Exception as e:
    logger.warning(f"미국 주식 목록 로드 실패: {e}")
    DF_US = pd.DataFrame()

# KRX merge (한 번만 수행)
try:
    DF_KRX_MERGED = pd.merge(DF_KRX_PRICE, DF_KRX_DESC, on='Code', how='inner')
except Exception as e:
    logger.warning(f"KRX 데이터 병합 실패: {e}")
    DF_KRX_MERGED = pd.DataFrame()

print("[준비 완료]\n")


# ============================================================
# 급등주 선행 패턴 (Top 70) 추출 및 매칭 로직
# ============================================================
TOP70_TEMPLATES = []

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
def build_top70_templates(krx_tickers, us_tickers):
    global TOP70_TEMPLATES
    TOP70_TEMPLATES = []
    print(f"\n[패턴 스캔 준비] 당일 급등한 상위 종목 {len(krx_tickers) + len(us_tickers)}개의 급등 직전 템플릿 추출 중...")
    
    start_date = (datetime.datetime.now() - datetime.timedelta(days=700)).strftime('%Y-%m-%d')
    
    total_krx = len(krx_tickers)
    for idx, code in enumerate(krx_tickers):
        try:
            if total_krx > 0:
                pct = (idx + 1) / total_krx * 100
                sys.stdout.write(f"\r  → KRX 템플릿 추출: {idx+1}/{total_krx} ({pct:.0f}%)")
                sys.stdout.flush()
            df = fdr.DataReader(code, start_date)
            if not df.empty:
                feat = extract_features_for_template(df)
                if feat: TOP70_TEMPLATES.append(feat)
        except Exception:
            pass
    if total_krx > 0:
        sys.stdout.write("\n")
            
    if us_tickers:
        try:
            data = yf.download(us_tickers, period="2y", interval="1d", progress=False, threads=True)
            if isinstance(data.columns, pd.MultiIndex):
                for t in us_tickers:
                    try:
                        if t in data['Close'].columns:
                            df_t = pd.DataFrame({
                                'Open': data['Open'][t],
                                'High': data['High'][t],
                                'Low': data['Low'][t],
                                'Close': data['Close'][t],
                                'Volume': data['Volume'][t]
                            }).dropna()
                            feat = extract_features_for_template(df_t)
                            if feat: TOP70_TEMPLATES.append(feat)
                    except Exception: pass
            else:
                df_t = data.dropna()
                feat = extract_features_for_template(df_t)
                if feat: TOP70_TEMPLATES.append(feat)
        except Exception:
            pass
            
    print(f"  > 완료: 총 {len(TOP70_TEMPLATES)}개의 템플릿 생성됨.")



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

def analyze_stocks(tickers, ticker_to_name, cache):
    results = {
        "monthly_pattern": [],
        "top70_pattern_match": [],
        "top70_shape_match": [],
        "cloud_twist": [],
        "cloud_twist_1w": [],
        "ma200_support_breakout": [],
        "5yr_high_breakout": []
    }

    # 우선주/특수종목(띄어쓰기 포함 티커) 사전 제외
    def _is_valid_ticker(t, name_map):
        if ' ' in t: return False
        name = name_map.get(t, '')
        import re
        if re.search(r'\uc6b0[A-C]?$', name): return False
        skip_kw = ['\uc2a4\ud329', 'SPAC', '\uae30\uc5c5\uc778\uc218', '\uc778\uc218\ubaa9\uc801', '\uc6b0\uc120\uc8fc']
        if any(kw in name for kw in skip_kw): return False
        return True
    valid_tickers = [t for t in tickers if _is_valid_ticker(t, ticker_to_name)]
    total = len(valid_tickers)
    if total == 0:
        return results

    # ── 캐시에서 데이터 조회 (네트워크 호출 없음) ──
    print(f"    → {total}개 종목 캐시 데이터로 분석을 시작합니다...")

    for idx, ticker in enumerate(valid_tickers):
        try:
            name = ticker_to_name.get(ticker, "")
            display_name = f"{name}({ticker})" if name else ticker

            # 진행상황 표시
            pct = (idx + 1) / total * 100
            bar_len = 20
            filled = int(bar_len * (idx + 1) / total)
            bar = '█' * filled + '░' * (bar_len - filled)
            progress_msg = f"\r  [{bar}] {pct:5.1f}% ({idx+1}/{total}) | 분석 중: {display_name}"
            sys.stdout.write(f"{progress_msg:<80}")
            sys.stdout.flush()

            # 캐시에서 개별 종목 데이터 추출
            df = cache["ohlcv"].get(ticker)
            if df is None:
                continue
            df = df.copy()

            if df.empty or len(df) < 60:
                continue

            # 유동성 필터: 거래량이 거의 없는 잡주, SPAC 등 제외
            is_krx = ticker.endswith('.KS') or ticker.endswith('.KQ')
            avg_amount = 0
            try:
                recent_20d = df.tail(20)
                avg_vol = recent_20d['Volume'].mean()
                avg_price = recent_20d['Close'].mean()
                if isinstance(avg_vol, pd.Series): avg_vol = avg_vol.item()
                if isinstance(avg_price, pd.Series): avg_price = avg_price.item()
                
                avg_amount = avg_vol * avg_price
                min_vol = 50000
                min_amount = 1_000_000_000 if is_krx else 1_000_000  # KRX: 10억, US: $1M
                
                if avg_vol < min_vol or avg_amount < min_amount:
                    continue
            except:
                pass

            df = calculate_ichimoku(df)

            # 시가총액 가져오기 (한국: KRX 캐시, 미국: 데이터 캐시)
            pure_code = ticker.split('.')[0] if is_krx else ticker
            market_cap = KRX_CAP_MAP.get(pure_code, 0) if is_krx else cache.get("market_caps", {}).get(ticker, 0)

            # ── 시가총액 필터 ──
            # 미국 주식: yfinance rate limiting으로 시가총액=0인 경우가 빈번하므로,
            # 시가총액이 0이면 일평균 거래대금으로 대체 판단 (거래대금 $5M 이상 = 대형주급)
            US_MIN_MARKET_CAP = 714_000_000  # 약 1조원 ($714M ≈ 1조원 @1400원/달러)
            US_MIN_AVG_AMOUNT_FALLBACK = 5_000_000  # 시가총액 누락 시 대체 기준: 일평균 $5M
            if is_krx:
                if market_cap <= 0:
                    continue
            else:
                if market_cap > 0 and market_cap < US_MIN_MARKET_CAP:
                    continue
                if market_cap <= 0:
                    # 시가총액 조회 실패 → 거래대금으로 대체 판단
                    if avg_amount < US_MIN_AVG_AMOUNT_FALLBACK:
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

            # Top 70 급등 전조 패턴 매칭 (조건 + 모양)
            if len(TOP70_TEMPLATES) > 0:
                current_feat = extract_current_features(df)
                if current_feat:
                    cond_match, shape_match = is_pattern_matched(current_feat, TOP70_TEMPLATES)
                    if cond_match:
                        signals.append("top70_pattern_match")
                    if shape_match:
                        signals.append("top70_shape_match")

            # 4. 월봉: 대세 하락 후 바닥 다지기(지지) & 강한 장대양봉 돌파(상승) 패턴
            try:
                try:
                    df_m = df.resample('ME').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()
                except Exception:
                    df_m = df.resample('M').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()

                if len(df_m) >= 6:
                    # 1. 2년 고점 대비 크게 하락한 종목인지 확인 (단순 눌림목 제외)
                    lookback = min(24, len(df_m))
                    historical_24m = df_m.iloc[-lookback:]
                    
                    # 최근 턴어라운드 구간(최대 3개월)에 발생한 급등을 과거 '전고점'으로 착각하지 않도록 제외
                    if len(historical_24m) > 3:
                        max_high_24m = historical_24m.iloc[:-3]['High'].max()
                    else:
                        max_high_24m = historical_24m['High'].max()
                        
                    min_low_24m = historical_24m['Low'].min()
                    
                    if max_high_24m >= min_low_24m * 1.5:
                        def get_val(val):
                            return val.item() if isinstance(val, pd.Series) else val
                            
                        def check_pattern(c_2, c_1, c_0):
                            o2, c2 = get_val(c_2['Open']), get_val(c_2['Close'])
                            o1, c1 = get_val(c_1['Open']), get_val(c_1['Close'])
                            o0, c0 = get_val(c_0['Open']), get_val(c_0['Close'])
                            v1, v0 = get_val(c_1['Volume']), get_val(c_0['Volume'])
                            
                            pct2 = abs(c2 - o2) / o2
                            is_t2_valid = (c2 < o2) or (pct2 <= 0.05)
                            
                            pct1 = abs(c1 - o1) / o1
                            is_t1_exhausted = (c1 < o1) or (pct1 <= 0.03)
                            
                            is_t_green = c0 > o0
                            is_t_volume_up = v0 > v1
                            return is_t2_valid and is_t1_exhausted and is_t_green and is_t_volume_up
                            
                        def evaluate_window(c_2, c_1, c_0):
                            if check_pattern(c_2, c_1, c_0):
                                # 턴어라운드 시작점(T-2, T-1)이 과거 2년 변동폭의 하위 50% 이내 바닥권이었는지 확인
                                range_24m = max_high_24m - min_low_24m
                                bottom_threshold = min_low_24m + (range_24m * 0.50)
                                base_low = min(get_val(c_2['Close']), get_val(c_1['Close']))
                                if base_low <= bottom_threshold:
                                    return True
                            return False

                        pattern_matched = False
                        
                        # Case 1: 이번 달에 턴어라운드 (T-2, T-1, T)
                        if len(df_m) >= 3 and evaluate_window(df_m.iloc[-3], df_m.iloc[-2], df_m.iloc[-1]):
                            pattern_matched = True
                            
                        # Case 2: 지난 달에 턴어라운드 (T-3, T-2, T-1)
                        elif len(df_m) >= 4 and evaluate_window(df_m.iloc[-4], df_m.iloc[-3], df_m.iloc[-2]):
                            # 돌파 캔들 몸통의 절반(midpoint) 이상을 이번 달에도 유지하는지 확인
                            # → 양봉 후 큰 음봉이 나온 실패한 돌파 제외 (예: RBLX)
                            c0_o, c0_c = get_val(df_m.iloc[-2]['Open']), get_val(df_m.iloc[-2]['Close'])
                            midpoint = c0_o + (c0_c - c0_o) * 0.5
                            t_c = get_val(df_m.iloc[-1]['Close'])
                            if t_c >= midpoint:
                                pattern_matched = True
                                
                        # Case 3: 지지난 달에 턴어라운드 (T-4, T-3, T-2)
                        elif len(df_m) >= 5 and evaluate_window(df_m.iloc[-5], df_m.iloc[-4], df_m.iloc[-3]):
                            # 지난 달(완성된 월봉)만으로 후속 유지 확인
                            # 이번 달(진행 중)은 불완전하므로 판단에서 제외
                            c0_o = get_val(df_m.iloc[-3]['Open'])
                            t1_c = get_val(df_m.iloc[-2]['Close'])
                            if t1_c >= c0_o:
                                pattern_matched = True
                                
                        if pattern_matched:
                            signals.append("monthly_pattern")
            except Exception as e:
                logger.debug(f"{ticker} 월봉 분석 실패: {e}")


            if "ma200_support_breakout" in signals and len(signals) == 1:
                signals.remove("ma200_support_breakout")

            if signals:
                # PE/PB: .info 호출은 1~3초/건으로 극심한 속도 저하 유발하므로 제거
                # 대시보드에서 종목 클릭 시 네이버/TradingView에서 직접 확인 가능
                pe_ratio = 0.0
                pb_ratio = 0.0

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
        "krx": ["소프트웨어", "IT", "반도체", "전자", "컴퓨터", "정보기술", "하드웨어",
                "전지", "이차전지", "영상", "음향", "측정", "정밀기기", "케이블", "절연선",
                "마그네틱", "광학", "전구", "조명", "정보 서비스"],
        "nasdaq": ["Software", "Hardware", "Semiconductor", "IT", "Information Technology", "Electronic",
                   # 기존 한국어 키워드
                   "소프트웨어", "반도체", "전자", "컴퓨터", "정보기술", "하드웨어",
                   # FDR 한국어 Industry 매핑 (IONQ, QUBT 등 누락 방지)
                   "IT 서비스 및 컨설팅", "반도체 장비 및 테스트", "컴퓨터 하드웨어",
                   "전자 장비 및 부품", "전기 부품 및 장비", "통합 하드웨어 및 소프트웨어",
                   "전화 및 소형 장치", "사무기기", "전문 정보 서비스",
                   "통신 및 네트워킹", "블록 체인 및 암호화폐", "핀테크", "기타 핀테크 인프라"]
    },
    "커뮤니케이션 (통신, 미디어, 엔터테인먼트, 인터랙티브 미디어 및 서비스)": {
        "krx": ["통신", "미디어", "엔터테인먼트", "방송", "영화", "인터넷", "게임",
                "오디오", "출판", "녹음", "광고", "창작", "예술"],
        "nasdaq": ["Communication", "Media", "Entertainment", "Interactive Media", "Telecom", "Broadcasting",
                   "통신", "미디어", "엔터테인먼트", "방송", "영화", "인터넷", "게임",
                   # FDR 한국어 Industry 매핑
                   "온라인 서비스", "엔터테인먼트 제작", "광고 및 마케팅",
                   "소비자 출판", "무선 통신 서비스", "통합 통신 서비스"]
    },
    "임의소비재 (자동차 및 부품, 내구소비재, 의류, 레저, 호텔/레스토랑)": {
        "krx": ["자동차", "내구소비재", "의류", "레저", "호텔", "레스토랑", "여행", "소비재",
                "봉제", "의복", "가구", "가죽", "가방", "신발", "악기", "숙박", "오락",
                "음식점", "교습", "학원", "교육"],
        "nasdaq": ["Automobile", "Auto Parts", "Consumer Discretionary", "Apparel", "Leisure", "Hotel", "Restaurant",
                   "자동차", "내구소비재", "의류", "레저", "호텔", "레스토랑", "여행", "소비재",
                   # FDR 한국어 Industry 매핑
                   "자동차 및 트럭 제조", "자동차, 트럭 및 오토바이 부품",
                   "자동차 차량, 부품 및 서비스 소매", "의류 및 액세서리", "의류 및 액세서리 소매",
                   "가정용 가구", "가정용 가구 소매", "가정용 전자 제품",
                   "레스토랑 및 바", "호텔, 모텔 및 크루즈 라인",
                   "여가 및 오락시설", "카지노 및 도박", "오락용 제품",
                   "장난감 및 어린이 제품", "제화", "직물 및 가죽제품",
                   "기타 교육 서비스 제공", "초, 중, 고등 교육기관", "전문 및 비즈니스 교육",
                   "기타 전문 소매", "백화점", "할인점",
                   "주택 건설", "주택 개조 제품 및 서비스 소매",
                   "컴퓨터 및 전자 제품 소매", "지상 및 해상 여객 운송", "항공사"]
    },
    "필수소비재 (식음료, 유통, 가정용품, 개인용품, 담배)": {
        "krx": ["식음료", "유통", "가정용품", "개인용품", "담배", "생활용품", "화장품",
                "식품", "곡물", "전분", "음료", "도축", "육류", "수산물", "사료",
                "소매", "낙농", "작물", "가정용 기기"],
        "nasdaq": ["Consumer Staples", "Food", "Beverage", "Retail", "Household", "Personal", "Tobacco",
                   "식음료", "유통", "가정용품", "개인용품", "담배", "생활용품", "화장품",
                   # FDR 한국어 Industry 매핑
                   "식품 가공", "식품 소매 및 유통", "무알콜 음료", "양조업", "증류주 및 포도주",
                   "가전제품, 도구 및 가정 용품", "가정용 제품", "개인 생활 필수 용품",
                   "개인 서비스", "소비재 대기업", "어업 및 농업", "농화학제",
                   "의약품 소매", "비즈니스 지원 용품", "타이어 및 고무 제품"]
    },
    "헬스케어 (제약, 생명공학(바이오), 의료기기, 헬스케어 서비스 및 장비)": {
        "krx": ["제약", "바이오", "생명공학", "의료기기", "헬스케어", "약품", "의료", "의약",
                "생물학", "연구개발"],
        "nasdaq": ["Healthcare", "Pharmaceutical", "Biotechnology", "Medical", "Health Care",
                   "제약", "바이오", "생명공학", "의료기기", "헬스케어",
                   # FDR 한국어 Industry 매핑
                   "생명 공학 및 의학 연구", "의료 장비, 물품 및 유통",
                   "첨단 의료 장비 및 기술", "의료 시설 및 서비스", "의료 관리"]
    },
    "금융 (은행, 보험, 다각화된 금융 서비스, 소비자 금융)": {
        "krx": ["은행", "보험", "금융", "증권", "지주", "신탁", "집합투자"],
        "nasdaq": ["Financial", "Bank", "Insurance", "Consumer Finance", "Capital Markets",
                   "은행", "보험", "금융", "증권", "지주",
                   # FDR 한국어 Industry 매핑
                   "기업 금융 서비스", "소비자 대출", "투자 관리 및 펀드 운영",
                   "투자 은행 및 중개 서비스", "투자 지주 회사",
                   "생명 및 건강 보험", "손해보험", "복합보험 및 중개인", "재보험",
                   "금융, 상품 시장 운영 및 서비스 제공", "다각적 투자 서비스",
                   "연금", "뮤추얼 펀드", "폐쇄형 펀드", "영국 투자 신탁",
                   "온라인 소액 투자 중개"]
    },
    "산업재 (자본재, 기계, 상업/전문 서비스, 운송 및 물류)": {
        "krx": ["산업재", "기계", "상업", "운송", "물류", "건설", "조선", "항공",
                "선박", "보트", "엔지니어링", "도매", "중개", "무기", "총포탄",
                "경비", "경호", "폐기물", "설비", "공사", "디자인", "컨설팅", "경영",
                "사업지원"],
        "nasdaq": ["Industrial", "Capital Goods", "Machinery", "Commercial Services", "Transportation", "Logistics", "Aerospace",
                   "산업재", "기계", "상업", "운송", "물류", "건설", "조선", "항공",
                   # FDR 한국어 Industry 매핑
                   "산업용 기계 및 장비", "중장비 및 차량", "중전기장비",
                   "건설 및 엔지니어링", "건설 자재", "건설 자재 및 비품",
                   "항공우주 및 방위", "경영 지원 서비스", "고용 서비스",
                   "배달, 우편, 항공 화물 및 육상 물류", "지상 화물 및 물류",
                   "해양 화물 및 물류", "공항 운영 및 서비스", "항만 운영 및 서비스",
                   "다각적 산업용 제품 도매", "상업 인쇄 서비스",
                   "환경 서비스 및 장비"]
    },
    "소재 (화학, 건설자재, 금속 및 채광, 종이/포장재)": {
        "krx": ["화학", "건설자재", "금속", "채광", "종이", "포장재", "철강", "비철금속",
                "고무", "플라스틱", "시멘트", "석회", "유리", "합성고무", "비료", "농약",
                "요업", "나무", "직물", "방적", "섬유"],
        "nasdaq": ["Material", "Chemical", "Construction Material", "Metals", "Mining", "Paper", "Packaging",
                   "화학", "건설자재", "금속", "채광", "종이", "포장재", "철강", "비철금속",
                   # FDR 한국어 Industry 매핑
                   "다각적 화학 산업", "상품 화학", "특수 화학제",
                   "철 및 강철", "알루미늄", "금", "금 제외 귀금속 및 광물",
                   "다각적 채굴", "특수 채굴 및 금속", "채굴 지원 서비스 및 장비",
                   "종이 제품", "종이 포장재", "용기(종이 제외) 및 포장재",
                   "임업 및 목재 제품"]
    },
    "에너지 (석유/가스 탐사 및 생산, 정제, 에너지 장비 및 서비스)": {
        "krx": ["에너지", "석유", "가스", "정제", "연료"],
        "nasdaq": ["Energy", "Oil", "Gas", "Exploration", "Refining", "Energy Equipment",
                   "에너지", "석유", "가스", "정제",
                   # FDR 한국어 Industry 매핑
                   "오일 관련 서비스 및 장비", "오일 및 가스 수송 서비스",
                   "오일 및 가스 시추", "오일, 가스 정제 및 마케팅",
                   "오일, 가스 탐사 및 생산", "통합 오일 및 가스",
                   "석탄", "우라늄"]
    },
    "유틸리티 (전력, 가스, 수도, 다각화된 재생에너지)": {
        "krx": ["전력", "수도", "유틸리티", "재생에너지", "환경", "전기", "발전", "태양광",
                "풍력", "증기", "냉·온수", "공기조절"],
        "nasdaq": ["Utility", "Electric", "Water", "Renewable",
                   "전력", "수도", "유틸리티", "재생에너지", "환경",
                   # FDR 한국어 Industry 매핑 (SMR 등 누락 방지)
                   "전력 유틸리티", "복합 유틸리티", "천연가스 유틸리티", "수자원 유틸리티",
                   "민자 발전 사업", "재생 가능 에너지 장비 및 서비스", "재생 가능 연료"]
    },
    "부동산 (부동산 관리 및 개발, 리츠(REITs))": {
        "krx": ["부동산", "리츠", "리츠(REITs)", "건설업"],
        "nasdaq": ["Real Estate", "REIT", "Property Management", "Development",
                   "부동산", "리츠", "리츠(REITs)", "건설업",
                   # FDR 한국어 Industry 매핑
                   "부동산 서비스", "부동산 임대, 개발 및 운영",
                   "상업용 REITs", "주거용 REITs", "복합부동산 REITs", "특수 REITs"]
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

                import re
                for _, row in krx_filtered.iterrows():
                    stock_name = row[name_col]
                    # 우선주 제외 (이름 끝이 '우', '우B', '우C' 등)
                    if re.search(r'우[A-C]?$', stock_name):
                        continue
                    # 스팩(SPAC)/기업인수목적/리츠 우선주 등 제외
                    skip_keywords = ['스팩', 'SPAC', '기업인수', '인수목적', '우선주']
                    if any(kw in stock_name for kw in skip_keywords):
                        continue
                    suffix = ".KS" if row[market_col] == 'KOSPI' else ".KQ"
                    ticker = f"{row['Code']}{suffix}"
                    krx_tickers.append(ticker)
                    ticker_to_name[ticker] = stock_name

            krx_tickers = list(set(krx_tickers))
            print(f"  → {len(krx_tickers)}개 종목 발견")
        except Exception as e:
            print(f"  [오류] KRX 데이터 처리 실패: {e}")

    # 2. 미국 주식 (NASDAQ, NYSE, AMEX) — 전역 캐시 사용
    if market_type in ["ALL", "US", "NASDAQ"] and not DF_US.empty:
        print(f"[{theme_name}] 미국 시장 종목 선정 중...")
        try:
            nasdaq = DF_US.copy()
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
# 데이터 캐시 시스템: 한 번 다운로드 → 저장 → 재사용
# ============================================================
CACHE_FILE = "stock_data_cache.pkl"


def collect_all_tickers(market_type="ALL"):
    """11개 테마의 모든 고유 티커를 한 번에 수집 (네트워크 호출 없음)"""
    all_krx = []
    all_us = []
    ticker_to_name = {}
    theme_ticker_map = {}

    for theme_name in THEMES.keys():
        krx, us, names = get_market_tickers(theme_name, market_type)
        theme_ticker_map[theme_name] = {"krx": krx, "us": us}
        all_krx.extend(krx)
        all_us.extend(us)
        ticker_to_name.update(names)

    all_krx = list(set(all_krx))
    all_us = list(set(all_us))
    print(f"\n[수집 완료] 전체 고유 종목: 한국 {len(all_krx)}개 + 미국 {len(all_us)}개 = 총 {len(all_krx) + len(all_us)}개")
    return all_krx, all_us, ticker_to_name, theme_ticker_map


def download_and_cache_all(all_krx, all_us):
    """전 종목 OHLCV + 시가총액을 한 번에 다운로드하고 캐시 저장"""
    cache = {"ohlcv": {}, "market_caps": {}, "timestamp": datetime.datetime.now()}

    all_tickers = all_krx + all_us
    # 우선주/잘못된 티커 사전 필터링 (공백 포함 티커는 Yahoo Finance에서 404 에러 발생)
    all_tickers = [t for t in all_tickers if ' ' not in t]
    if not all_tickers:
        return cache

    # yfinance 에러 로그 억제 (상장폐지 종목 등의 불필요한 에러 메시지 숨김)
    yf_logger = logging.getLogger('yfinance')
    prev_yf_level = yf_logger.level
    yf_logger.setLevel(logging.CRITICAL)

    # 1. 전 종목 OHLCV 일괄 다운로드 (단 1회의 yf.download)
    print(f"\n[다운로드] 전체 {len(all_tickers)}개 종목 OHLCV 일괄 다운로드 중...", flush=True)
    try:
        all_data = yf.download(all_tickers, period="5y", interval="1d", progress=True, threads=True)
    except Exception as e:
        logger.warning(f"일괄 다운로드 실패: {e}")
        return cache

    if all_data.empty:
        return cache

    is_multi = isinstance(all_data.columns, pd.MultiIndex)

    print(f"  → OHLCV 데이터 추출 중...", flush=True)

    if is_multi:
        # swaplevel로 (Column, Ticker) → (Ticker, Column) 변환 (O(1) 메타데이터 변경)
        swapped = all_data.swaplevel(axis=1)
        available = swapped.columns.get_level_values(0).unique()
        total_available = len(available)
        for idx, ticker in enumerate(available):
            try:
                df = swapped[ticker].dropna()
                if not df.empty and len(df) > 0:
                    cache["ohlcv"][ticker] = df
            except Exception:
                pass
            if (idx + 1) % 500 == 0 or (idx + 1) == total_available:
                pct = (idx + 1) / total_available * 100
                sys.stdout.write(f"\r  → OHLCV 추출: {idx+1}/{total_available} ({pct:.0f}%)")
                sys.stdout.flush()
    else:
        # 단일 종목인 경우
        df = all_data.copy()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)
        if not df.empty:
            ticker = all_tickers[0] if all_tickers else None
            if ticker:
                cache["ohlcv"][ticker] = df

    sys.stdout.write("\n")
    print(f"  → OHLCV 데이터: {len(cache['ohlcv'])}개 종목 추출 완료", flush=True)

    # 1-b. 누락 종목 배치 재시도 (최대 200개, 50개씩 묶어서 다운로드)
    missing_tickers = [t for t in all_tickers if t not in cache["ohlcv"]]
    if missing_tickers:
        MAX_RETRY = 200
        BATCH_SIZE = 50
        if len(missing_tickers) > MAX_RETRY:
            print(f"  → 누락 종목 {len(missing_tickers)}개 중 {MAX_RETRY}개만 재시도 (나머지 생략)", flush=True)
            missing_tickers = missing_tickers[:MAX_RETRY]
        else:
            print(f"  → 누락 종목 {len(missing_tickers)}개 배치 재다운로드 중...", flush=True)

        retry_success = 0
        for batch_start in range(0, len(missing_tickers), BATCH_SIZE):
            batch = missing_tickers[batch_start:batch_start + BATCH_SIZE]
            batch_num = batch_start // BATCH_SIZE + 1
            total_batches = (len(missing_tickers) + BATCH_SIZE - 1) // BATCH_SIZE
            sys.stdout.write(f"\r  → 배치 재시도: [{batch_num}/{total_batches}] {len(batch)}개 종목...")
            sys.stdout.flush()
            try:
                df_batch = yf.download(batch, period="5y", interval="1d", progress=False, threads=True)
                if not df_batch.empty:
                    if isinstance(df_batch.columns, pd.MultiIndex):
                        swapped = df_batch.swaplevel(axis=1)
                        for ticker in batch:
                            try:
                                if ticker in swapped.columns.get_level_values(0):
                                    df_t = swapped[ticker].dropna()
                                    if not df_t.empty:
                                        cache["ohlcv"][ticker] = df_t
                                        retry_success += 1
                            except Exception:
                                pass
                    elif len(batch) == 1:
                        df_single = df_batch.copy()
                        if isinstance(df_single.columns, pd.MultiIndex):
                            df_single.columns = df_single.columns.droplevel(1)
                        df_single = df_single.dropna()
                        if not df_single.empty:
                            cache["ohlcv"][batch[0]] = df_single
                            retry_success += 1
            except Exception:
                pass
        sys.stdout.write(f"\r  → 재시도 완료: {retry_success}/{len(missing_tickers)}개 복구                \n")
        print(f"  → 최종 OHLCV 데이터: {len(cache['ohlcv'])}개 종목", flush=True)

    # 2. 미국 주식 시가총액 조회 (ThreadPoolExecutor 병렬 처리)
    us_in_cache = [t for t in all_us if t in cache["ohlcv"]]
    if us_in_cache:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        print(f"\n[시가총액] 미국 주식 {len(us_in_cache)}개 시가총액 조회 중...", flush=True)

        def _fetch_mcap(ticker):
            try:
                mc = yf.Ticker(ticker).fast_info.market_cap
                if mc and mc > 0:
                    return ticker, int(mc)
            except Exception:
                pass
            return ticker, 0

        success_count = 0
        total_us = len(us_in_cache)
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(_fetch_mcap, t): t for t in us_in_cache}
            for i, future in enumerate(as_completed(futures)):
                ticker, mc = future.result()
                if mc > 0:
                    cache["market_caps"][ticker] = mc
                    success_count += 1
                if (i + 1) % 50 == 0 or (i + 1) == total_us:
                    pct = (i + 1) / total_us * 100
                    sys.stdout.write(f"\r  → 시가총액 조회: {i+1}/{total_us} ({pct:.0f}%) | 성공: {success_count}")
                    sys.stdout.flush()

        sys.stdout.write("\n")
        print(f"  → 미국 주식 시가총액: {success_count}/{total_us}개 조회 완료", flush=True)
    else:
        print(f"  → 미국 주식 시가총액: 캐시에 미국 종목 없음 (건너뜀)", flush=True)

    # yfinance 로그 레벨 복원
    yf_logger.setLevel(prev_yf_level)

    # 3. 캐시 파일 저장
    with open(CACHE_FILE, "wb") as f:
        pickle.dump(cache, f)

    size_mb = os.path.getsize(CACHE_FILE) / (1024 * 1024)
    print(f"[저장 완료] {len(cache['ohlcv'])}개 종목 캐시 → {CACHE_FILE} ({size_mb:.1f}MB)")
    return cache


def load_cache():
    """24시간 이내 캐시가 있으면 로드, 없거나 만료되면 None 반환"""
    if not os.path.exists(CACHE_FILE):
        return None
    try:
        with open(CACHE_FILE, "rb") as f:
            cache = pickle.load(f)
        cached_time = cache.get("timestamp")
        if cached_time:
            elapsed = (datetime.datetime.now() - cached_time).total_seconds()
            hours_ago = elapsed / 3600
            if elapsed < 24 * 3600:  # 24시간 이내
                n = len(cache.get("ohlcv", {}))
                print(f"[캐시] 유효한 캐시 발견 ({hours_ago:.1f}시간 전, {n}개 종목). 다운로드를 건너뜁니다.")
                return cache
            else:
                print(f"[캐시] 캐시 만료 ({hours_ago:.0f}시간 경과). 새로 다운로드합니다.")
                return None
        else:
            return None
    except Exception as e:
        logger.warning(f"캐시 로드 실패: {e}")
        return None


# ============================================================
# 디스코드 전송 (테마별 한국/미국 결과를 하나로 묶어 전송)
# ============================================================
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
BASE_DASHBOARD_URL = "http://localhost:5173"

labels = {
    "monthly_pattern": "🛡️ 월봉 지지 후 상승 (바닥권)",
    "top70_pattern_match": "🔥 최신 트렌드 상승 패턴 (조건)",
    "top70_shape_match": "📈 최신 트렌드 상승 패턴 (모양)",
    "cloud_twist": "🟢 양운 전환 (당일)",
    "cloud_twist_1w": "❇️ 1주 내 양운 전환: 음운에서 양운 크로스오버",
    "ma200_support_breakout": "📈 200일선: 지지 또는 돌파",
    "5yr_high_breakout": "🚀 5년 전고점 돌파: 새로운 주가 레벨 진입"
}

def translate_to_ko(text):
    if not text or text in ['No title', 'No summary']: return text
    for attempt in range(2):  # 2회 재시도
        try:
            url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=ko&dt=t&q={requests.utils.quote(text)}"
            res = requests.get(url, timeout=8)
            if res.status_code == 200:
                translated = "".join([x[0] for x in res.json()[0]])
                # 자연스러운 한국어 후처리
                translated = translated.replace(' 의 ', '의 ').replace(' 을 ', '을 ').replace(' 를 ', '를 ')
                translated = translated.replace(' 이 ', '이 ').replace(' 가 ', '가 ')
                translated = re.sub(r'\s+', ' ', translated).strip()
                return translated
            elif res.status_code == 429:
                import time as _t; _t.sleep(2)  # Rate limit → 2초 대기 후 재시도
                continue
        except requests.exceptions.Timeout:
            import time as _t; _t.sleep(1)
            continue
        except Exception as e:
            if attempt == 0:
                import time as _t; _t.sleep(1)
                continue
            break
    return text

def format_news_concise(news_items, max_items=3):
    """뉴스 항목을 핵심 제목만 간결하게 한국어로 변환합니다.
    기존: 제목 전체 + 요약 전체를 그대로 번역 → 너무 길고 번역체
    개선: 제목만 번역 후 한 줄로 표시 (핵심 포인트만)
    """
    if not news_items:
        return None
    formatted = []
    for n in news_items[:max_items]:
        title = n.get('content', {}).get('title', '')
        if not title or title == 'No title':
            continue
        ko_title = translate_to_ko(title)
        # 제목이 너무 길면 마침표/쉼표 기준으로 앞부분만 사용
        if len(ko_title) > 80:
            for sep in ['. ', ', ', ' - ']:
                idx = ko_title.find(sep)
                if 20 < idx < 80:
                    ko_title = ko_title[:idx]
                    break
        formatted.append(f"🔹 {ko_title}")
    return "\n".join(formatted) if formatted else None

def get_realtime_data():
    _rd_start = _global_time.time()
    print("[데이터] 실시간 시장 데이터를 가져오는 중... (약 30개 항목, 예상 ~2분)")
    print("  → [1/4] 매크로 지표 조회 (DXY, CPI, PCE, 고용, Fed 금리 등)...", flush=True)
    data = {}
    
    # DXY
    try:
        dxy = yf.Ticker('DX-Y.NYB').fast_info.last_price
        data['DXY'] = f"{round(dxy, 2):.2f}"
    except Exception:
        data['DXY'] = "97.86"

    # FRED Macro Indicators
    # ── 공식 발표일 룩업 테이블 (BLS/BEA/FOMC 2026년 스케줄) ──
    # key: (year, reference_month) → value: "발표일 문자열"
    CPI_RELEASE = {
        (2026,1):"2/11",(2026,2):"3/11",(2026,3):"4/10",(2026,4):"5/12",(2026,5):"6/10",
        (2026,6):"7/14",(2026,7):"8/12",(2026,8):"9/11",(2026,9):"10/14",(2026,10):"11/10",(2026,11):"12/10",
        (2025,12):"1/14",(2025,11):"12/11",(2025,10):"11/13",(2025,9):"10/10",
    }
    PCE_RELEASE = {
        (2025,12):"2/20",(2026,1):"3/13",(2026,2):"4/9",(2026,3):"4/30",(2026,4):"5/28",
        (2026,5):"6/25",(2026,6):"7/31",(2026,7):"8/28",(2026,8):"9/30",(2026,9):"10/30",(2026,10):"11/25",(2026,11):"12/23",
    }
    NFP_RELEASE = {
        (2025,12):"1/9",(2026,1):"2/11",(2026,2):"3/6",(2026,3):"4/3",(2026,4):"5/8",(2026,5):"6/5",
        (2026,6):"7/2",(2026,7):"8/7",(2026,8):"9/4",(2026,9):"10/2",(2026,10):"11/6",(2026,11):"12/4",
    }
    FOMC_DATES = {
        (2026,1):"1/28",(2026,3):"3/18",(2026,4):"4/29",(2026,6):"6/17",
        (2026,7):"7/29",(2026,9):"9/16",(2026,10):"10/28",(2026,12):"12/9",
    }
    def _lookup_release(table, ref_date, fallback_fmt=True):
        """FRED 기준월 인덱스로 공식 발표일을 찾아 MM/DD 형식으로 반환"""
        key = (ref_date.year, ref_date.month)
        val = table.get(key)
        if val:
            # '5/28' → '05/28' 제로패딩 통일
            parts = val.split('/')
            if len(parts) == 2:
                return f"{int(parts[0]):02d}/{int(parts[1]):02d}"
            return val
        if fallback_fmt:
            return ref_date.strftime('%m/%d')
        return ''

    def _fetch_cnbc_quote(*symbols):
        """CNBC API에서 실시간 시세 조회 (DGS2, Fed금리, VIX 등)"""
        try:
            sym_str = '|'.join(symbols)
            url = f"https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol?symbols={sym_str}&requestMethod=itv&noform=1&partnerId=2&fund=1&exthrs=1&output=json"
            res = requests.get(url, timeout=8, headers={'User-Agent': 'Mozilla/5.0'})
            if res.status_code == 200:
                result = {}
                for q in res.json().get('FormattedQuoteResult', {}).get('FormattedQuote', []):
                    sym = q.get('symbol', '')
                    last = q.get('last', '').replace('%', '').replace(',', '')
                    try:
                        result[sym] = float(last)
                    except ValueError:
                        pass
                return result
        except Exception:
            pass
        return {}

    def _fetch_fred_api(series_id, limit=1):
        """FRED API에서 경제지표 실시간 조회 (.env의 FRED_API_KEY 필요)"""
        api_key = os.getenv('FRED_API_KEY', '')
        if not api_key:
            return None, None
        try:
            url = f"https://api.stlouisfed.org/fred/series/observations?series_id={series_id}&api_key={api_key}&file_type=json&sort_order=desc&limit={limit}"
            res = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
            if res.status_code == 200:
                obs = res.json().get('observations', [])
                if obs and obs[0].get('value') not in (None, '.', ''):
                    return float(obs[0]['value']), obs[0].get('date', '')
        except Exception:
            pass
        return None, None

    try:
        import FinanceDataReader as fdr
        import pandas as pd
        
        try:
            cpi = fdr.DataReader('FRED:CPIAUCSL')
            cpi_yoy = (cpi.iloc[-1,0] / cpi.iloc[-13,0] - 1) * 100
            data['CPI_YOY'] = f"{cpi_yoy:.1f}%"
            data['CPI_DATE'] = _lookup_release(CPI_RELEASE, cpi.index[-1])
        except Exception:
            data['CPI_YOY'] = "3.3%"
            data['CPI_DATE'] = ''
        
        try:
            pce = fdr.DataReader('FRED:PCEPI')
            pce_yoy = (pce.iloc[-1,0] / pce.iloc[-13,0] - 1) * 100
            data['PCE_YOY'] = f"{pce_yoy:.1f}%"
            data['PCE_DATE'] = _lookup_release(PCE_RELEASE, pce.index[-1])
        except Exception:
            data['PCE_YOY'] = "3.5%"
            data['PCE_DATE'] = ''
        
        try:
            payems = fdr.DataReader('FRED:PAYEMS')
            nfp = payems.iloc[-1,0] - payems.iloc[-2,0]
            data['NFP'] = f"{nfp:.0f}K"
            data['NFP_DATE'] = _lookup_release(NFP_RELEASE, payems.index[-1])
        except Exception:
            data['NFP'] = "178K"
            data['NFP_DATE'] = ''
        
        try:
            unrate = fdr.DataReader('FRED:UNRATE')
            data['UNRATE'] = f"{unrate.iloc[-1,0]:.1f}%"
            data['UNRATE_DATE'] = _lookup_release(NFP_RELEASE, unrate.index[-1])
        except Exception:
            data['UNRATE'] = "4.3%"
            data['UNRATE_DATE'] = ''
        
        try:
            # FEDFUNDS: Fed 실효금리 (단일 값) — FinanceDataReader에서 작동 확인됨
            fedfunds = fdr.DataReader('FRED:FEDFUNDS')
            eff_rate = fedfunds.iloc[-1, 0]
            import math
            fed_upper = math.ceil(eff_rate * 4) / 4
            fed_lower = fed_upper - 0.25
            data['FED_RATE'] = f"Fed {fed_lower:.2f}~{fed_upper:.2f}%"
            data['FED_DATE'] = _lookup_release(FOMC_DATES, fedfunds.index[-1])
        except Exception:
            # FRED API 폴백: 직접 DFEDTARU/DFEDTARL 조회
            upper, _ = _fetch_fred_api('DFEDTARU')
            lower, _ = _fetch_fred_api('DFEDTARL')
            if upper is not None and lower is not None:
                data['FED_RATE'] = f"Fed {lower:.2f}~{upper:.2f}%"
                data['FED_DATE'] = ''
            else:
                # CNBC API 폴백
                try:
                    cnbc = _fetch_cnbc_quote('US3M')
                    rate_3m = cnbc.get('US3M')
                    if rate_3m and 2.0 <= rate_3m <= 8.0:
                        import math
                        fed_upper = math.ceil(rate_3m * 4) / 4
                        fed_lower = fed_upper - 0.25
                        data['FED_RATE'] = f"Fed {fed_lower:.2f}~{fed_upper:.2f}%"
                    else:
                        data['FED_RATE'] = "Fed 3.50~3.75%"
                except Exception:
                    data['FED_RATE'] = "Fed 3.50~3.75%"
                data['FED_DATE'] = ''
        
        try:
            nfci = fdr.DataReader('FRED:NFCI')
            data['NFCI'] = f"{nfci.iloc[-1,0]:.2f}"
            data['NFCI_DATE'] = nfci.index[-1].strftime('%m/%d')
        except Exception:
            # FRED API 폴백: NFCI 실시간 조회
            nfci_val, nfci_date = _fetch_fred_api('NFCI')
            if nfci_val is not None:
                data['NFCI'] = f"{nfci_val:.2f}"
                # FRED 날짜 포맷: 2026-06-05 → 06/05
                data['NFCI_DATE'] = nfci_date[5:].replace('-', '/') if nfci_date else ''
            else:
                # VIX 기반 추정 폴백
                from datetime import datetime
                try:
                    cnbc_vix = _fetch_cnbc_quote('.VIX')
                    vix_val = cnbc_vix.get('.VIX')
                    if vix_val is None:
                        vix_val = yf.Ticker('^VIX').fast_info.last_price
                    if vix_val < 15: nfci_est = -0.70
                    elif vix_val < 18: nfci_est = -0.50
                    elif vix_val < 22: nfci_est = -0.30
                    elif vix_val < 25: nfci_est = -0.10
                    else: nfci_est = 0.10
                    data['NFCI'] = f"{nfci_est:.2f}"
                except Exception:
                    data['NFCI'] = "-0.52"
                data['NFCI_DATE'] = datetime.now().strftime('%m/%d')
        
        try:
            ism = fdr.DataReader('FRED:NAPM')
            data['PMI'] = f"{ism.iloc[-1,0]:.1f}"
            data['PMI_DATE'] = ism.index[-1].strftime('%m/%d')
        except Exception:
            # PMI는 yfinance에 없음 — 기본값 사용 (월간 수동 업데이트 필요)
            data['PMI'] = "54.0"
            data['PMI_DATE'] = '06/01'
    except Exception:
        data['CPI_YOY'] = "3.3%"
        data['CPI_DATE'] = ''
        data['PCE_YOY'] = "3.5%"
        data['PCE_DATE'] = ''
        data['NFP'] = "178K"
        data['NFP_DATE'] = ''
        data['UNRATE'] = "4.3%"
        data['UNRATE_DATE'] = ''
        data['FED_RATE'] = "Fed 3.50~3.75%"
        data['FED_DATE'] = ''
        data['NFCI'] = "-0.52"
        data['NFCI_DATE'] = ''
        data['PMI'] = "54.0"
        data['PMI_DATE'] = '06/01'

    print("  → [2/4] 시장 지표 조회 (KRW, VIX, Gold, Silver, WTI 등)...", flush=True)
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

    print("  → [3/4] 채권, 크립토, 뉴스 및 Fed 발언 조회...", flush=True)
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
        tnx_news_str = format_news_concise(tnx_news)
        data['TNX_NEWS'] = tnx_news_str if tnx_news_str else "- 최근 10년물 국채 관련 특이 뉴스 없음."
    except Exception:
         data['TNX_NEWS'] = "- 최근 10년물 국채 관련 특이 뉴스 없음."

    # 2-Year Yield (FRED DGS2) & News (SHY)
    try:
        import FinanceDataReader as fdr
        dgs2 = float(fdr.DataReader('FRED:GS2').iloc[-1,0])
        data['DGS2'] = f"{round(dgs2, 3):.3f}"
    except Exception:
        # FRED API 폴백: DGS2 실시간
        dgs2_val, _ = _fetch_fred_api('DGS2')
        if dgs2_val is not None:
            data['DGS2'] = f"{dgs2_val:.3f}"
        else:
            # CNBC API 폴백: US 2-Year Treasury
            try:
                cnbc_2y = _fetch_cnbc_quote('US2Y')
                val_2y = cnbc_2y.get('US2Y')
                if val_2y:
                    data['DGS2'] = f"{val_2y:.3f}"
                else:
                    data['DGS2'] = "4.035"
            except Exception:
                data['DGS2'] = "4.035"
        
    try:
        shy_news = yf.Ticker('SHY').news[:3]
        shy_news_str = format_news_concise(shy_news)
        data['DGS2_NEWS'] = shy_news_str if shy_news_str else "- 최근 2년물 국채 관련 특이 뉴스 없음."
    except Exception:
        data['DGS2_NEWS'] = "- 최근 2년물 국채 관련 특이 뉴스 없음."

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
        btc_news_str = format_news_concise(btc_news)
        data['BTC_NEWS'] = btc_news_str if btc_news_str else "- 최근 비트코인 관련 특이 뉴스 없음."
    except Exception:
        data['BTC_NEWS'] = "- 최근 비트코인 관련 특이 뉴스 없음."

    # Macro / Geopolitical News
    # Macro / Geopolitical News (Top 3 Highly Trusted from SPY)
    try:
        spy_news = yf.Ticker('SPY').news[:3]
        macro_news_str = format_news_concise(spy_news)
        if macro_news_str:
            # 📰 이모지로 교체 (매크로 뉴스 구분)
            data['MACRO_NEWS'] = macro_news_str.replace('🔹', '📰')
        else:
            data['MACRO_NEWS'] = "- 최근 24시간 내 특이 뉴스 없음."
    except Exception as e:
        data['MACRO_NEWS'] = "- 뉴스 데이터를 불러올 수 없습니다."
        
    # Fed Speak Fetch
    try:
        import urllib.parse
        import requests
        import xml.etree.ElementTree as ET
        
        q = urllib.parse.quote('(Fed OR FOMC) AND (says OR said OR expects OR points) when:3d')
        res = requests.get(f'https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en')
        root = ET.fromstring(res.text)
        items = root.findall('.//item')[:2]
        fed_speak_list = []
        for i in items:
            title = i.find('title').text if i.find('title') is not None else ''
            title = title.rsplit(' - ', 1)[0]
            ko_title = translate_to_ko(title)
            fed_speak_list.append(f" 🗣️ {ko_title}")
        
        if fed_speak_list:
            data['FED_SPEAK'] = "\n\n🎙️ [연준 위원 및 FOMC 주요 발언]\n" + "\n".join(fed_speak_list)
        else:
            data['FED_SPEAK'] = "\n\n🎙️ [연준 위원 및 FOMC 주요 발언]\n 🗣️ 최근 3일 내 주요 발언 없음"
    except Exception as e:
        data['FED_SPEAK'] = ""


        
    # PE Data (Trailing PE) — Yahoo Finance v7 Quote API 배치 조회 (단 1회 호출)
    print("  → [4/4] 섹터별 PE 밸류에이션 조회 (11개 ETF, ~12초 소요)...", flush=True)
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
    import time as _time
    total_etfs = len(etf_symbols)
    
    # 방법 1: Yahoo Finance v7 Quote API 배치 호출 (전 ETF를 1회 요청으로 조회)
    pe_fetched = False
    try:
        symbols_str = ",".join(etf_symbols.keys())
        quote_url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbols_str}"
        quote_headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        quote_res = requests.get(quote_url, headers=quote_headers, timeout=10)
        if quote_res.status_code == 200:
            quotes = quote_res.json().get('quoteResponse', {}).get('result', [])
            for q in quotes:
                sym = q.get('symbol', '')
                name = etf_symbols.get(sym, '')
                if name:
                    pe = q.get('trailingPE', 0)
                    if pe and pe > 0:
                        data['PE'][name] = round(pe, 1)
                        sys.stdout.write(f"\r    PE: {name} ({sym}) → {pe:.1f}배 ✅          ")
                        sys.stdout.flush()
            # 조회 성공 여부 확인
            if len(data['PE']) >= total_etfs * 0.5:  # 절반 이상 성공하면 OK
                pe_fetched = True
                print(f"\r    PE: v7 Quote API로 {len(data['PE'])}/{total_etfs}개 조회 성공          ")
    except Exception as e:
        logger.warning(f"v7 Quote API PE 조회 실패: {e}")
    
    # 방법 2: 실패 시 yfinance .info 개별 호출 (폴백)
    if not pe_fetched:
        print("    PE: v7 API 실패 → yfinance .info 개별 조회로 전환...", flush=True)
        for idx, (sym, name) in enumerate(etf_symbols.items()):
            if name in data['PE']:  # v7에서 이미 성공한 건 스킵
                continue
            sys.stdout.write(f"\r    PE: [{idx+1}/{total_etfs}] {name} ({sym})...          ")
            sys.stdout.flush()
            try:
                info = yf.Ticker(sym).info
                pe = info.get('trailingPE') or info.get('forwardPE')
                if pe and pe > 0:
                    data['PE'][name] = round(pe, 1)
                _time.sleep(1.5)
            except:
                pass
    
    # 누락된 섹터는 기본값 설정
    for sym, name in etf_symbols.items():
        if name not in data['PE']:
            data['PE'][name] = 20.0
            logger.warning(f"PE 조회 실패: {name} ({sym}) → 기본값 20.0배 사용")
    sys.stdout.write("\n")
    _rd_elapsed = _global_time.time() - _rd_start
    _rd_m, _rd_s = divmod(int(_rd_elapsed), 60)
    print(f"  ✅ 실시간 데이터 수집 완료 ({_rd_m}분 {_rd_s}초 소요)", flush=True)

    return data


def get_top70_krx_gainers():
    print("\n[분석] 당일 한국 주식 상승률 상위 70 종목 분석을 시작합니다...")
    try:
        # 최신 데이터를 위해 새로 다운로드
        fresh_krx = fdr.StockListing('KRX')
        if fresh_krx.empty:
            return "- KRX 시세 데이터를 불러올 수 없어 분석할 수 없습니다.", []
        
        # 6자리 종목코드만 필터링 (우선주 등 제외 처리 보완 가능하나 기본 유지)
        fresh_krx = fresh_krx[fresh_krx['Code'].str.len() == 6]
        
        # 상승률(ChagesRatio) 기준 내림차순 정렬하여 상위 70종목 추출
        top70 = fresh_krx.sort_values('ChagesRatio', ascending=False).head(70)
        top70['Rank'] = range(1, len(top70) + 1)
        
        # 섹터 정보를 위해 기존 DF_KRX_DESC와 병합
        if not DF_KRX_DESC.empty:
            top70 = pd.merge(top70, DF_KRX_DESC, on='Code', how='left')
        else:
            top70['Sector'] = ''
            top70['Industry'] = ''
        
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

        top70['Theme'] = top70.apply(classify_theme, axis=1)
        theme_counts = top70['Theme'].value_counts()
        
        # 디스코드 보고서 생성
        report_lines = []
        report_lines.append(f"🔍 [당일 상승률 상위 70종목 주요 섹터 분포]")
        for theme, count in theme_counts.head(5).items():
            t_name = theme if theme == '기타/확인불가' or theme.endswith('관련주') else theme + ' 관련주'
            report_lines.append(f"  └ {t_name}: {count}종목")
            
        report_lines.append(f"\n📈 [상승률 상위 70종목 섹터별 상세 표]")
        for theme, count in theme_counts.items():
            t_name = theme if theme == '기타/확인불가' or theme.endswith('관련주') else theme + ' 관련주'
            report_lines.append(f"\n📁 **[{t_name}]** ({count}종목)")
            
            theme_stocks = top70[top70['Theme'] == theme]
            for _, row in theme_stocks.iterrows():
                rank = row['Rank']
                name = str(row.get('Name_x', row.get('Name', row['Code'])))
                code = str(row['Code'])
                market = "KS" if str(row.get('Market_x', row.get('Market', ''))) == 'KOSPI' else "KQ"
                chg = float(row.get('ChagesRatio', 0.0))
                report_lines.append(f"  └ {rank:02d}위 | {name} ({code}.{market}) (+{chg:.2f}%)")
            
        # 프론트엔드 대시보드용 데이터
        top70_data = []
        for idx, row in top70.iterrows():
            top70_data.append({
                "rank": row['Rank'],
                "code": row['Code'],
                "name": row.get('Name_x', row.get('Name', row['Code'])),
                "sector": str(row['Sector']) if pd.notna(row.get('Sector')) else '',
                "industry": str(row['Industry']) if pd.notna(row.get('Industry')) else (str(row['Industry_y']) if pd.notna(row.get('Industry_y')) else ''),
                "marcap": int(row['Marcap']) if pd.notna(row['Marcap']) else 0,
                "change_ratio": float(row['ChagesRatio']) if pd.notna(row['ChagesRatio']) else 0.0
            })
            
        return "\n".join(report_lines), top70_data
    except Exception as e:
        logger.warning(f"Top 70 분석 실패: {e}")
        return f"- 분석 중 오류 발생: {e}", []

def get_top70_us_gainers():
    print("\n[분석] 당일 미국 주식 상승률 상위 70 종목 분석을 시작합니다...")
    try:
        url = 'https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?formatted=true&lang=en-US&region=US&scrIds=day_gainers&count=70'
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}, timeout=10)
        quotes = res.json().get('finance', {}).get('result', [{}])[0].get('quotes', [])
        
        top70_info = []
        # 업종 정보 사전 구축 (네트워크 호출 대신 DF_US 캐시 사용)
        us_industry_map = dict(zip(DF_US['Symbol'], DF_US['Industry'])) if not DF_US.empty else {}

        import yfinance as yf
        import time
        import pandas as pd
        
        for idx, q in enumerate(quotes[:70], 1):
            sym = q.get('symbol', '')
            name = q.get('shortName', sym)
            ko_name = translate_to_ko(name)
            ko_name = ko_name if ko_name else name
            chg_obj = q.get('regularMarketChangePercent', 0.0)
            chg = chg_obj.get('raw', 0.0) if isinstance(chg_obj, dict) else float(chg_obj)
            
            # DF_US에서 업종 정보 즉시 조회 (기존 .info 호출 제거로 ~10분 단축)
            industry = str(us_industry_map.get(sym, 'Unknown'))
            sector = industry
                
            top70_info.append({"rank": idx, "sym": sym, "name": ko_name, "chg": chg, "sector": sector, "industry": industry})

        top70_df = pd.DataFrame(top70_info)
        if top70_df.empty:
            return "- 데이터를 불러올 수 없습니다.", []
            
        sector_counts = top70_df['sector'].value_counts()

        report_lines = []
        report_lines.append(f"🔍 [당일 상승률 상위 종목 주요 섹터 분포]")
        for sec, count in sector_counts.head(5).items():
            s_name = translate_to_ko(sec) if sec != 'Unknown' else '기타/확인불가'
            s_name = s_name if s_name == '기타/확인불가' or s_name.endswith('관련주') else s_name + ' 관련주'
            report_lines.append(f"  └ {s_name}: {count}종목")

        report_lines.append(f"\n📈 [상승률 상위 70종목 섹터별 상세 표]")
        for sec, count in sector_counts.items():
            s_name = translate_to_ko(sec) if sec != 'Unknown' else '기타/확인불가'
            s_name = s_name if s_name == '기타/확인불가' or s_name.endswith('관련주') else s_name + ' 관련주'
            report_lines.append(f"\n📁 **[{s_name}]** ({count}종목)")
            
            sec_stocks = top70_df[top70_df['sector'] == sec]
            for _, row in sec_stocks.iterrows():
                rank = row['rank']
                sym = row['sym']
                name = row['name']
                chg = row['chg']
                report_lines.append(f"  └ {rank:02d}위 | {sym} {name} (+{chg:.2f}%)")
        
        return "\n".join(report_lines), [info['sym'] for info in top70_info]
    except Exception as e:
        logger.warning(f"US Top 70 분석 실패: {e}")
        return f"- 미국 시장 분석 중 오류 발생: {e}", []

def send_to_discord(top70_krx_text, top70_us_text):
    if not DISCORD_WEBHOOK_URL:
        print("\n[안내] 디스코드 웹훅 URL이 설정되지 않아 메시지를 전송하지 않습니다. (.env 파일을 확인하세요)")
        return

    d = get_realtime_data()

    # 날짜 정보 포맷팅 (각 지표의 최신 데이터 기준일 — MM/DD 기준 통일)
    _cd = d.get('CPI_DATE', '')
    _pd = d.get('PCE_DATE', '')
    date_inflation = f" (📅 CPI {_cd} / PCE {_pd} 기준)" if _cd or _pd else ""
    _nd = d.get('NFP_DATE', '')
    date_employment = f" (📅 {_nd} 기준)" if _nd else ""
    _pmd = d.get('PMI_DATE', '')
    date_pmi = f" (📅 {_pmd} 기준)" if _pmd else ""
    _fd = d.get('FED_DATE', '')
    date_fed = f" (📅 {_fd} 기준)" if _fd else ""
    _nfd = d.get('NFCI_DATE', '')
    date_nfci = f" (📅 {_nfd} 기준)" if _nfd else ""

    vix = d['VIX']
    gold = d['GOLD']
    silver = d['SILVER']
    copper = d['COPPER']
    wti = d['WTI']
    tnx = d['TNX']
    btc = d['BTC']
    dxy = d.get('DXY', '97.86')
    krw = d.get('KRW', '1,470')
    
    # 버핏 지수 추산 (VTI 가격을 프록시로 사용)
    # VTI_BASE_PRICE = 362.87 : 2026년 1월 1일 기준 VTI 종가
    # BUFFETT_BASE_PCT = 231.0 : 해당 시점의 실제 버핏 지수(총 시가총액/GDP * 100)
    VTI_BASE_PRICE = 362.87
    BUFFETT_BASE_PCT = 231.0
    try:
        vti_price = yf.Ticker('VTI').fast_info.last_price
        buffett_indicator = round((vti_price / VTI_BASE_PRICE) * BUFFETT_BASE_PCT, 1)
    except Exception:
        buffett_indicator = BUFFETT_BASE_PCT
        
    buffett_alert = ""
    if buffett_indicator >= 200.0:
        buffett_alert = f"\n\n🚨 긴급 역발상 특보: 워런 버핏 지수 극단적 과열 경고\n👉 현재 지수: {buffett_indicator}% (위험 수준 200% 초과)\n⚠️ 버크셔 해서웨이 동향: 애플(AAPL), 뱅크오브아메리카(BAC) 등 주요 지분 대량 매각 후 4,000억 달러 이상 역대 최대 현금 확보. 시장 거품에 대한 강력한 경고로 해석되며, 추격 매수 중단 및 현금 비중 확대 필수."
    elif buffett_indicator <= 130.0:
        buffett_alert = f"\n🚨 긴급 역발상 특보: 워런 버핏 지수 바닥권 진입\n👉 현재 지수: {buffett_indicator}% (극단적 공포 및 기회 구간)\n⚠️ 버크셔 해서웨이 동향: 지수가 130% 이하로 바닥권에 진입하면 버핏은 공격적 매수를 준비합니다. 역사적으로 이런 구간에서 버크셔는 '우량 금융주(골드만삭스, BAC)', '필수소비재', '에너지(옥시덴탈, 셰브론)' 및 해자를 갖춘 '미디어/브랜드' 기업들을 대거 매집했습니다. 펀더멘털 우량주 분할 매수 타점입니다."
        
        
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
        tnx_float = float(tnx)
        dgs2_float = float(d.get('DGS2', '4.000'))
        spread = tnx_float - dgs2_float
        
        if spread < 0.0:
            forecast_result = f"장단기 금리 역전 (스프레드 {spread:+.3f}%p). 🚨 역사적으로 경기 침체의 가장 강력한 선행 지표이며, 머지않아 연준의 강력한 '금리 인하' 사이클이 시작될 확률이 높습니다."
        elif spread <= 0.3:
            forecast_result = f"수익률 곡선 평탄화 (스프레드 {spread:+.3f}%p). 경기 둔화 우려 증가 및 연준의 점진적 완화 스탠스 가능성."
        else:
            forecast_result = f"정상적인 수익률 곡선 (스프레드 {spread:+.3f}%p). 안정적인 경제 성장 기대."

        rate_forecast_text = f"""📌 [장단기 금리차 (10년물 - 2년물) 분석]
현재 미 10년물 국채 금리는 {tnx_float:.3f}%이며, 미 2년물 국채 금리는 {dgs2_float:.3f}%입니다. 
양자의 차이(스프레드)는 **{spread:+.3f}%p**입니다.

💡 과거 50년 데이터를 분석해 보면:
- **금리 인상(긴축) 사이클**: 연준이 정책금리를 올리면서 2년물 금리가 급등해 10년물 금리를 '역전'(스프레드 마이너스)하는 현상이 자주 발생했습니다.
- **금리 인하(완화) 사이클**: 역전된 금리차가 다시 '정상화(스프레드 0 이상 돌파)'되는 시점 전후로 연준이 경기 방어를 위해 급격한 금리 인하를 단행했으며, 이때 증시의 변동성도 가장 컸습니다.
👉 현재 상황 분석: {forecast_result}"""
    except Exception as e:
        rate_forecast_text = f"📌 [장단기 금리차 분석]\n데이터 수집 오류로 분석을 생략합니다. ({e})"

    messages = [
        f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 안티그레비티 통합 전략 리포트 (1/10)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━{buffett_alert}

📊 주요 경제 및 유동성 지표

🍎 물가 (CPI / PCE): {d.get('CPI_YOY', '3.3%')} / {d.get('PCE_YOY', '3.5%')}{date_inflation}

👷 고용 (NFP / 실업률): {d.get('NFP', '178K')} / {d.get('UNRATE', '4.3%')}{date_employment}

🏭 경기 (ISM PMI): {d.get('PMI', '54.0')}{date_pmi}

💵 금리: {d.get('FED_RATE', 'Fed 3.50~3.75%')}{date_fed}

💧 유동성 NFCI: {d.get('NFCI', '-0.52')}{date_nfci}{d.get('FED_SPEAK', '')}""",

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
🇺🇸 미 국채 2년물 금리 (DGS2) : {d.get('DGS2', '4.000')}%
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{rate_forecast_text}

📌 [증시 영향 및 전망]
10년물 국채금리는 주식 등 자산 가치의 '할인율'로 작용하며, 2년물 금리는 '연준의 통화정책(금리 인상/인하)'을 가장 민감하게 반영합니다. 장단기 금리차가 역전되었다가 정상화되는 구간에서는 시장의 방향성이 크게 바뀔 수 있으므로 리스크 관리가 필수적입니다.

🗞️ [최근 2년물 국채 관련 뉴스 (통화정책 선행지표)]
{d.get('DGS2_NEWS', '- 최근 뉴스 없음')}

🗞️ [최근 10년물 국채 관련 뉴스 (시장금리 벤치마크)]
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
🟢 11개 GICS 섹터 맞춤 전략 (PE 기반 동적 판단)
{chr(10).join(['🟢 확대  ' + ' / '.join([n for n, p in pe_data.items() if n != '시장 전체' and p < 16]) or '해당 없음', '🟡 중립  ' + ' / '.join([n for n, p in pe_data.items() if n != '시장 전체' and 16 <= p < 18]) or '해당 없음', '🔴 축소  ' + ' / '.join([n for n, p in pe_data.items() if n != '시장 전체' and p >= 18]) or '해당 없음'])}

💡 전략 근거 (실시간 데이터 기반)
시장 전체 P/E {market_pe:.1f}배 | VIX {vix} | 유가 ${wti}
PE 16배 미만 섹터 → 저평가 구간, 비중 확대 유리
PE 18배 이상 섹터 → 차익 실현 압력 존재, 비중 축소 권고
고금리 환경에서 부동산·임의소비재 취약, 에너지·소재 방어력 우위""",

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
현재 시장: Trailing P/E {market_pe:.1f}배 | VIX {vix} | 유가 ${wti}

💰 현금 확보
{'⚠️ PE ' + f'{market_pe:.0f}배 과열 구간 — 5점(광기) 섹터 추격 매수 중단, 현금 비중 30%↑ 확보' if market_pe >= 19 else '✅ PE ' + f'{market_pe:.0f}배 적정 수준 — 기존 현금 비중 유지, 우량주 분할 매수 가능'}

🔄 로테이션
{'고평가 섹터(PE 18↑) → 저평가 섹터(PE 16↓)로 리밸런싱 권고' if market_pe >= 18 else '현재 밸류에이션 적정 — 기존 포트폴리오 유지, 선별적 비중 조절'}

🎯 타점 대기
200일선 지지 + 양운 전환 동반 종목만 보수적 접근

⚡ 예외 매수
{'VIX ' + f'{vix} 고변동성 — 변동성 축소 시까지 신규 진입 자제' if float(vix) >= 25 else '펀더멘털 견고 + 경영진 $100K↑ 내부자 매수 기업만 분할 스윙 허용'}""",

        f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 안티그레비티 통합 전략 리포트 (9/10)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🇰🇷 당일 한국 주식 상승률 상위 70 종목 분석
{top70_krx_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🇺🇸 당일 미국 주식 상승률 상위 70 종목 분석
{top70_us_text}""",

        f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 안티그레비티 통합 전략 리포트 (10/10)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📝 안티그레비티 최종 종합 요약
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📍 시장 현황: P/E {market_pe:.1f}배 | VIX {vix} | DXY {dxy} | 10Y {tnx}% | WTI ${wti} | BTC ${btc}

{'🚨 시장 과열 경고: PE ' + f'{market_pe:.0f}배로 고평가 구간입니다. 차익 실현 압력이 높으며 추격 매수를 자제하고 현금 비중 확대가 필요합니다.' if market_pe >= 19 else '✅ 밸류에이션 적정: PE ' + f'{market_pe:.0f}배로 합리적 수준입니다. 펀더멘털이 견고한 우량주 중심 선별 매수가 가능합니다.' if market_pe < 17 else '⚠️ 밸류에이션 주의: PE ' + f'{market_pe:.0f}배로 중립~과열 경계입니다. 섹터별 차별화 대응이 필요합니다.'}

{'🔥 VIX ' + f'{vix}으로 공포 구간 — 변동성이 극심하므로 신규 진입 시 분할 매수 필수' if float(vix) >= 25 else '😌 VIX ' + f'{vix}으로 안정 구간 — 시장 변동성이 낮아 포지션 구축에 유리한 환경' if float(vix) < 18 else '⚡ VIX ' + f'{vix}으로 경계 구간 — 포지션 규모를 줄이고 리스크 관리에 집중'}

결론: 200일선 지지 + 일목균형표 양운 전환이 동반된 우량 가치주 위주로 보수적 접근을 권고합니다.

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
                part_str = f" (부분 {chunk_idx+1}/{len(chunks)})" if len(chunks) > 1 else ""
                if part_str:
                    chunk = f"**{part_str.strip()}**\n{chunk}"
                
                payload = {"content": chunk}
                response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
                if response.status_code in [200, 204]:
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
    parser.add_argument('--force', action='store_true', help="캐시를 무시하고 강제 다운로드")
    parser.add_argument('--offline', action='store_true', help="오프라인 모드: 캐시만 사용, 네트워크 요청 0건 (테스트용)")
    parser.add_argument('--no-discord', action='store_true', help="디스코드 리포트 전송을 건너뜁니다 (KRX 단독 실행 시 중복 전송 방지용)")
    args = parser.parse_args()

    # 진행 상황 추적기 초기화
    TRACKER = StageTracker(total_stages=6 if not args.offline else 2)

    all_scan_results = []
    skip_scan = False
    top70_krx_text = "- 오프라인 모드: 당일 급등주 분석 생략"
    top70_us_text = "- 오프라인 모드: 당일 급등주 분석 생략"
    top70_data = []
    top70_us_data = []

    if args.offline:
        print("\n" + "=" * 50)
        print(" 🔌 오프라인 모드: 캐시만 사용 (네트워크 요청 0건)")
        print("=" * 50)
        cache = load_cache()
        if cache is None:
            print("\n[오류] 캐시 파일이 없습니다. 먼저 온라인으로 한 번 실행해주세요:")
            print("       python analyze_ichimoku.py")
            sys.exit(1)
    else:
        # 당일 상위 70종목 분석 데이터 가져오기
        TRACKER.start_stage("당일 급등주 분석 (한국 + 미국 Top 70)")
        top70_krx_text, top70_data = get_top70_krx_gainers()
        top70_us_text, top70_us_data = get_top70_us_gainers()
        TRACKER.end_stage(f"한국 {len(top70_data)}개 + 미국 {len(top70_us_data)}개 급등주 분석 완료")

        # 급등주 선행 패턴(TOP70) 템플릿 빌드 (여기서 호출해야 분석 시 매칭 가능)
        if not skip_scan:
            TRACKER.start_stage("급등주 선행 패턴 템플릿 빌드")
            krx_top = [t['code'] for t in top70_data][:70] if top70_data else []
            us_top = top70_us_data[:70] if top70_us_data else []
            build_top70_templates(krx_top, us_top)
            TRACKER.end_stage(f"{len(TOP70_TEMPLATES)}개 템플릿 생성")

    if os.path.exists("scan_results.json") and not args.offline:
        try:
            with open("scan_results.json", "r", encoding="utf-8") as f:
                cached_data = json.load(f)
                cached_time_str = cached_data.get("timestamp", "")
                if cached_time_str:
                    cached_time = datetime.datetime.strptime(cached_time_str, "%Y-%m-%d %H:%M:%S")
        except Exception as e:
            logger.warning(f"캐시 읽기 실패: {e}")

    if not skip_scan:
        # ── [최적화] 전체 티커 수집 → 일괄 다운로드 → 캐시 ──
        TRACKER.start_stage("전체 테마 종목 수집")
        all_krx, all_us, ticker_to_name, theme_ticker_map = collect_all_tickers(args.market)
        TRACKER.end_stage(f"한국 {len(all_krx)}개 + 미국 {len(all_us)}개 = 총 {len(all_krx)+len(all_us)}개")

        if not args.offline:
            # 캐시 확인 (당일 캐시가 있으면 다운로드 스킵)
            cache = None if args.force else load_cache()
            if cache is None:
                TRACKER.start_stage("전 종목 OHLCV + 시가총액 일괄 다운로드 (가장 오래 걸림)")
                cache = download_and_cache_all(all_krx, all_us)
                TRACKER.end_stage(f"{len(cache.get('ohlcv', {}))}개 종목 데이터 캐시 완료")
            else:
                TRACKER.start_stage("데이터 캐시 로드 (다운로드 건너뜀)")
                TRACKER.end_stage(f"{len(cache.get('ohlcv', {}))}개 종목 캐시 사용")

        TRACKER.start_stage(f"{len(THEMES)}개 테마별 일목균형표 분석 (캐시 사용)")
        theme_list = list(THEMES.keys())
        for theme_idx, theme_name in enumerate(theme_list):
            elapsed_total = _global_time.time() - TRACKER.start_time
            t_mins, t_secs = divmod(int(elapsed_total), 60)
            print(f"\n{'='*50}")
            print(f" 📊 [{theme_idx+1}/{len(theme_list)}] {theme_name}")
            print(f"    대상 시장: {args.market} | 경과: {t_mins}분 {t_secs}초")
            print(f"{'='*50}")

            krx_tickers = theme_ticker_map[theme_name]["krx"]
            nasdaq_tickers = theme_ticker_map[theme_name]["us"]

            # 미국 시장 분석
            results_nasdaq = {}
            if nasdaq_tickers:
                print(f"\n[미국] {theme_name} 테마 총 {len(nasdaq_tickers)}개의 종목에 대해 일목균형표 분석을 시작합니다.")
                results_nasdaq = analyze_stocks(nasdaq_tickers, ticker_to_name, cache)

            # 한국 시장 분석
            results_krx = {}
            if krx_tickers:
                print(f"\n[한국] {theme_name} 테마 총 {len(krx_tickers)}개의 종목에 대해 일목균형표 분석을 시작합니다.")
                results_krx = analyze_stocks(krx_tickers, ticker_to_name, cache)

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

    if not skip_scan:
        # 웹 대시보드용 JSON 파일 저장 (루트 + frontend/public 양쪽에 저장)
        output_data = {
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data": all_scan_results,
            "top30": top70_data  # 프론트엔드 호환성을 위해 키는 'top30' 유지
        }

        # 루트에 저장 (FastAPI가 읽는 경로)
        with open("scan_results.json", "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=4)

        # frontend/public에도 저장 (Vite 개발서버가 읽는 경로)
        os.makedirs("frontend/public", exist_ok=True)
        with open("frontend/public/scan_results.json", "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=4)

        print("\n[완료] scan_results.json 저장 완료 (루트 + frontend/public)")
        TRACKER.end_stage("테마별 분석 + 결과 저장 완료")

    if args.no_discord:
        print("\n[안내] --no-discord 옵션으로 디스코드 전송을 건너뜁니다.")
    elif not args.offline:
        # 최종 디스코드 9분할 리포트 전송
        TRACKER.start_stage("디스코드 리포트 전송 (실시간 데이터 + 리포트)")
        send_to_discord(top70_krx_text, top70_us_text)
        TRACKER.end_stage("디스코드 전송 완료")
    else:
        print("\n[오프라인] 디스코드 전송 생략")

    TRACKER.print_total()
    print(f"\n[완료] 프로그램이 성공적으로 종료되었습니다! 대시보드: {BASE_DASHBOARD_URL}")

