import sys
import sqlite3
import argparse

# 터미널 출력 시 이모지 등 유니코드 에러 방지
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
import yfinance as yf
from datetime import datetime
import os
import json

DB_NAME = "paper_trading.db"
INITIAL_SEED = 100_000_000  # 기본 가상계좌 자본금 1억원
FX_RATE = 1400              # 고정 환율 (가상거래 시뮬레이션 - 환율 변동으로 인한 수익률 혼동 방지)

TICKER_NAMES_CACHE = "ticker_names.json"

def is_korean(ticker):
    return ticker.endswith('.KS') or ticker.endswith('.KQ')

def get_stock_name(ticker):
    """종목 이름 조회 (한국=한국어, 미국=영어, 캐시 사용)"""
    cache = {}
    if os.path.exists(TICKER_NAMES_CACHE):
        try:
            with open(TICKER_NAMES_CACHE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
        except Exception:
            pass

    if ticker in cache:
        return cache[ticker]

    name = ticker
    if is_korean(ticker):
        # 한국 주식: FinanceDataReader에서 한국어 이름 조회 + 전체 캐싱
        try:
            import FinanceDataReader as fdr
            code = ticker.replace('.KS', '').replace('.KQ', '')
            df_krx = fdr.StockListing('KRX')
            match = df_krx[df_krx['Code'] == code]
            if not match.empty:
                name = match.iloc[0]['Name']
            # KRX 전체 종목을 한번에 캐시 (다음부터 즉시 조회)
            for _, row in df_krx.iterrows():
                for suffix in ['.KS', '.KQ']:
                    key = f"{row['Code']}{suffix}"
                    if key not in cache:
                        cache[key] = row['Name']
        except Exception:
            pass
    else:
        # 미국 주식: yfinance에서 영어 이름 조회
        try:
            info = yf.Ticker(ticker).info
            name = info.get('shortName', info.get('longName', ticker))
        except Exception:
            pass

    # 캐시에 저장
    cache[ticker] = name
    try:
        with open(TICKER_NAMES_CACHE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    return name

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS account (
                    id INTEGER PRIMARY KEY,
                    cash REAL
                 )''')
    c.execute('''CREATE TABLE IF NOT EXISTS portfolio (
                    ticker TEXT PRIMARY KEY,
                    shares INTEGER,
                    avg_price_krw REAL
                 )''')
    c.execute('''CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    action TEXT,
                    ticker TEXT,
                    price_krw REAL,
                    shares INTEGER,
                    amount_krw REAL,
                    fee_krw REAL,
                    slippage_krw REAL
                 )''')
    
    # 초기 계좌 생성
    c.execute('SELECT cash FROM account WHERE id=1')
    if not c.fetchone():
        c.execute('INSERT INTO account (id, cash) VALUES (1, ?)', (INITIAL_SEED,))
    
    conn.commit()
    conn.close()

def get_current_price(ticker):
    try:
        tkr = yf.Ticker(ticker)
        return tkr.fast_info['lastPrice']
    except Exception as e:
        print(f"[오류] {ticker}의 현재 가격을 가져오지 못했습니다. {e}")
        return None

def get_market_fee(ticker):
    # 한국 주식: 수수료+세금 포함 보수적으로 0.23% (매수/매도 각각 0.115% 적용)
    # 미국 주식: 수수료 0.1% (매수/매도 각각)
    return 0.00115 if is_korean(ticker) else 0.0010

def do_buy(ticker):
    ticker = ticker.upper()  # 티커 자동 대문자 변환
    
    price = get_current_price(ticker)
    if price is None: return False
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    price_krw = price if is_korean(ticker) else price * FX_RATE
    
    c.execute('SELECT cash FROM account WHERE id=1')
    cash = c.fetchone()[0]
    
    # 전체 자본금의 1% = 1,000,000원 고정 배팅
    target_amount = INITIAL_SEED * 0.01
    
    if cash < target_amount:
        print(f"[실패] 현금이 부족합니다. 현재 잔고: {cash:,.0f}원")
        conn.close()
        return False
        
    # 슬리피지 0.2% (불리하게 매수)
    slippage_rate = 0.002
    execution_price_krw = price_krw * (1 + slippage_rate)
    
    shares = int(target_amount // execution_price_krw)
    if shares == 0:
        print(f"[실패] 1주도 살 수 없는 가격입니다. 1주 체결가: {execution_price_krw:,.0f}원")
        conn.close()
        return False
        
    fee_rate = get_market_fee(ticker)
    trade_amount = execution_price_krw * shares
    fee = trade_amount * fee_rate
    
    total_cost = trade_amount + fee
    if cash < total_cost:
        print("[실패] 수수료를 포함하면 잔고가 부족합니다.")
        conn.close()
        return False
        
    # 포트폴리오 업데이트
    c.execute('SELECT shares, avg_price_krw FROM portfolio WHERE ticker=?', (ticker,))
    row = c.fetchone()
    if row:
        curr_shares, avg_price = row
        new_shares = curr_shares + shares
        new_avg = ((curr_shares * avg_price) + trade_amount) / new_shares
        c.execute('UPDATE portfolio SET shares=?, avg_price_krw=? WHERE ticker=?', (new_shares, new_avg, ticker))
    else:
        c.execute('INSERT INTO portfolio (ticker, shares, avg_price_krw) VALUES (?, ?, ?)', (ticker, shares, execution_price_krw))
        
    # 계좌 잔고 차감
    c.execute('UPDATE account SET cash = cash - ? WHERE id=1', (total_cost,))
    
    # 내역 저장
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    slippage_cost = price_krw * slippage_rate * shares
    c.execute('''INSERT INTO history (timestamp, action, ticker, price_krw, shares, amount_krw, fee_krw, slippage_krw)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
              (timestamp, 'BUY', ticker, execution_price_krw, shares, total_cost, fee, slippage_cost))
              
    conn.commit()
    conn.close()
    
    print(f"\n✅ [매수 체결 완료] {ticker}")
    print(f" - 현재가: {price:,.2f} {'KRW' if is_korean(ticker) else 'USD'}")
    print(f" - 1주 체결가(원화, 0.2% 슬리피지 포함): {execution_price_krw:,.0f} 원")
    print(f" - 수량: {shares}주")
    print(f" - 수수료: {fee:,.0f} 원")
    print(f" - 총 지불 금액: {total_cost:,.0f} 원")
    return True

def do_sell(ticker):
    ticker = ticker.upper()  # 티커 자동 대문자 변환
    
    price = get_current_price(ticker)
    if price is None: return False
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    c.execute('SELECT shares, avg_price_krw FROM portfolio WHERE ticker=?', (ticker,))
    row = c.fetchone()
    if not row or row[0] == 0:
        print(f"[실패] 현재 보유하고 있는 {ticker} 주식이 없습니다.")
        conn.close()
        return False
        
    shares = row[0]
    avg_price_krw = row[1]
    
    price_krw = price if is_korean(ticker) else price * FX_RATE
    
    # 슬리피지 0.2% (불리하게 매도)
    slippage_rate = 0.002
    execution_price_krw = price_krw * (1 - slippage_rate)
    
    fee_rate = get_market_fee(ticker)
    trade_amount = execution_price_krw * shares
    fee = trade_amount * fee_rate
    
    total_revenue = trade_amount - fee
    buy_amount = avg_price_krw * shares
    profit = total_revenue - buy_amount
    profit_rate = (profit / buy_amount) * 100
    
    # 잔고 증가 및 포트폴리오 삭제 (전량 매도)
    c.execute('UPDATE account SET cash = cash + ? WHERE id=1', (total_revenue,))
    c.execute('DELETE FROM portfolio WHERE ticker=?', (ticker,))
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    slippage_cost = price_krw * slippage_rate * shares
    c.execute('''INSERT INTO history (timestamp, action, ticker, price_krw, shares, amount_krw, fee_krw, slippage_krw)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
              (timestamp, 'SELL', ticker, execution_price_krw, shares, total_revenue, fee, slippage_cost))
              
    conn.commit()
    conn.close()
    
    print(f"\n✅ [매도 체결 완료] {ticker} (전량 매도)")
    print(f" - 1주 체결가(원화, 0.2% 슬리피지 포함): {execution_price_krw:,.0f} 원")
    print(f" - 수량: {shares}주")
    print(f" - 수수료 및 세금: {fee:,.0f} 원")
    print(f" - 총 회수 금액: {total_revenue:,.0f} 원")
    print(f" - 수익금: {profit:,.0f} 원 ({profit_rate:.2f}%)")
    return True

def show_status():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    c.execute('SELECT cash FROM account WHERE id=1')
    row = c.fetchone()
    if not row:
        init_db()
        c.execute('SELECT cash FROM account WHERE id=1')
        row = c.fetchone()
        
    cash = row[0]
    
    print(f"\n💰 현재 가상계좌 현금: {cash:,.0f} 원")
    print("=====================================")
    
    c.execute('SELECT ticker, shares, avg_price_krw FROM portfolio')
    rows = c.fetchall()
    
    total_eval = cash
    if not rows:
        print("보유 중인 주식이 없습니다.")
    else:
        print("\n[현재 포트폴리오]")
        for ticker, shares, avg_price_krw in rows:
            price = get_current_price(ticker)
            if price is None: continue
            
            price_krw = price if is_korean(ticker) else price * FX_RATE
            eval_amount = price_krw * shares
            buy_amount = avg_price_krw * shares
            profit_rate = ((eval_amount - buy_amount) / buy_amount) * 100
            
            total_eval += eval_amount
            name = get_stock_name(ticker)
            print(f" * {ticker}({name}) | {shares}주 | 매수단가: {avg_price_krw:,.0f}원 | 현재가: {price_krw:,.0f}원 | 수익률: {profit_rate:+.2f}% | 평가금액: {eval_amount:,.0f}원")
            
    total_profit_rate = ((total_eval - INITIAL_SEED) / INITIAL_SEED) * 100
    print(f"\n총 자산 평가(현금+주식): {total_eval:,.0f} 원 | 총 수익률: {total_profit_rate:+.2f}%")
        
    c.execute('SELECT ticker FROM portfolio')
    held_tickers = set(row[0] for row in c.fetchall())

    # ── 현재 보유 종목의 매수 이력 (같은 날 같은 종목은 합산) ──
    c.execute('SELECT timestamp, action, ticker, shares, price_krw, amount_krw FROM history ORDER BY id DESC')
    hist_rows = c.fetchall()
    
    # 날짜+종목 기준으로 합산
    from collections import OrderedDict
    daily_buys = OrderedDict()
    for ts, action, tkr, shrs, prc, amt in hist_rows:
        if tkr in held_tickers and action == "BUY":
            date_key = ts.split(" ")[0]  # "2026-06-01 23:18:09" → "2026-06-01"
            group_key = (date_key, tkr)
            if group_key not in daily_buys:
                daily_buys[group_key] = {"shares": 0, "total_amount": 0}
            daily_buys[group_key]["shares"] += shrs
            daily_buys[group_key]["total_amount"] += amt

    print("\n[보유 종목 매수 이력]")
    if daily_buys:
        for (date, tkr), data in daily_buys.items():
            avg_price = data["total_amount"] / data["shares"] if data["shares"] > 0 else 0
            name = get_stock_name(tkr)
            print(f" * {date} | 매수 | {tkr}({name}) | {data['shares']}주 | 평균단가: {avg_price:,.0f}원 | 총액: {data['total_amount']:,.0f}원")
    else:
        print(" * 매수 이력이 없습니다.")

    # ── 매도 실현 손익 ──
    c.execute('SELECT ticker, action, amount_krw FROM history')
    ticker_pl = {}
    for tkr, action, amt in c.fetchall():
        if tkr not in ticker_pl:
            ticker_pl[tkr] = {'BUY': 0, 'SELL': 0}
        ticker_pl[tkr][action] += amt

    sold_tickers = {tkr: data for tkr, data in ticker_pl.items() if data['SELL'] > 0 and tkr not in held_tickers}

    if sold_tickers:
        print("\n[매도 실현 손익]")
        total_realized = 0
        for tkr, data in sold_tickers.items():
            profit = data['SELL'] - data['BUY']
            profit_rate = (profit / data['BUY']) * 100 if data['BUY'] > 0 else 0
            emoji = "🟢" if profit >= 0 else "🔴"
            total_realized += profit
            name = get_stock_name(tkr)
            print(f" {emoji} {tkr}({name}) | 매수총액: {data['BUY']:,.0f}원 → 매도총액: {data['SELL']:,.0f}원 | 실현손익: {profit:+,.0f}원 ({profit_rate:+.2f}%)")
        print(f"   ─────────────────────────────────")
        emoji_total = "🟢" if total_realized >= 0 else "🔴"
        print(f" {emoji_total} 총 실현 손익: {total_realized:+,.0f}원")

    conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Paper Trading System")
    parser.add_argument('action', choices=['buy', 'sell', 'status'], help="실행할 액션 (buy, sell, status)")
    parser.add_argument('--ticker', type=str, help="종목 티커 (예: AAPL, 005930.KS)")
    
    args = parser.parse_args()
    init_db()
    
    if args.action == 'buy':
        if not args.ticker:
            print("[오류] 매수할 종목의 티커를 --ticker 로 입력해주세요.")
        else:
            print("\n[안내] 장이 열려있을 경우, 현재가(최근 종가)를 기준으로 가정한 후 즉시 가상 매수합니다.")
            do_buy(args.ticker)
    elif args.action == 'sell':
        if not args.ticker:
            print("[오류] 매도할 종목의 티커를 --ticker 로 입력해주세요.")
        else:
            print("\n[안내] 장이 열려있을 경우, 현재가(최근 종가)를 기준으로 가정한 후 즉시 가상 매도합니다.")
            do_sell(args.ticker)
    elif args.action == 'status':
        show_status()