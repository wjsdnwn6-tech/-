import re

with open('analyze_ichimoku.py', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Add get_top100_krx_patterns
func_code = '''
def get_top100_krx_patterns():
    print("\\n[분석] 당일 한국 주식 거래대금 상위 100 종목 패턴 분석을 시작합니다...")
    try:
        if DF_KRX_PRICE.empty:
            return "- KRX 시세 데이터가 없어 분석할 수 없습니다."
        krx = DF_KRX_PRICE.copy()
        krx = krx[krx['Code'].str.len() == 6]
        if 'Amount' in krx.columns:
            top100 = krx.sort_values('Amount', ascending=False).head(100)
        elif 'Volume' in krx.columns:
            top100 = krx.sort_values('Volume', ascending=False).head(100)
        else:
            top100 = krx.head(100)
        
        tickers = []
        ticker_to_name = {}
        for _, row in top100.iterrows():
            suffix = ".KS" if row.get('Market') == 'KOSPI' else ".KQ"
            ticker = f"{row['Code']}{suffix}"
            tickers.append(ticker)
            ticker_to_name[ticker] = row.get('Name', row['Code'])
        
        results = analyze_stocks(tickers, ticker_to_name)
        report_lines = []
        for pattern_key, label in labels.items():
            stocks = results.get(pattern_key, [])
            if stocks:
                names = [s['display'] for s in stocks[:7]]
                count = len(stocks)
                report_lines.append(f"{label}: 총 {count}종목 포착")
                report_lines.append(f"  └ 예시: {', '.join(names)}")
        if not report_lines:
            return "- 현재 뚜렷한 패턴이 포착된 상위 100 종목이 없습니다."
        return "\\n".join(report_lines)
    except Exception as e:
        logger.warning(f"Top 100 분석 실패: {e}")
        return f"- 분석 중 오류 발생: {e}"
'''

if 'def get_top100_krx_patterns():' not in text:
    text = text.replace('def send_to_discord():', func_code + '\\n\\ndef send_to_discord():')

# 2. Add top100_report to send_to_discord
if 'top100_report = get_top100_krx_patterns()' not in text:
    text = text.replace("d = get_realtime_data()\\n    vix = d['VIX']", "d = get_realtime_data()\\n    top100_report = get_top100_krx_patterns()\\n    vix = d['VIX']")

# 3. Replace (1/8) to (1/9) etc.
for i in range(1, 9):
    text = text.replace(f"({i}/8)", f"({i}/9)")

# 4. Add the 9th message
msg9 = '''        f"""📊 안티그레비티 통합 전략 리포트 (9/9)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🇰🇷 당일 한국 주식 거래대금 TOP 100 패턴 분석
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{top100_report}

💡 [분석 요약]
시장을 주도하는 거래대금 최상위 종목들 중 특정 기술적 패턴이 포착된 종목들입니다. 단기 트레이딩 및 주도주 파악에 활용하세요.""",

        f"""✅ 전체 스캔 및 분석 완료'''

if '당일 한국 주식 거래대금 TOP 100 패턴 분석' not in text:
    text = text.replace('        f"""✅ 전체 스캔 및 분석 완료', msg9)

# 5. Update bottom texts
text = text.replace('8분할로 한 번만 전송', '10분할로 한 번만 전송')
text = text.replace('8분할 리포트 전송', '9분할 리포트 전송')
text = text.replace('디스코드 8분할', '디스코드 9분할')

with open('analyze_ichimoku.py', 'w', encoding='utf-8') as f:
    f.write(text)

print("Modification complete!")
