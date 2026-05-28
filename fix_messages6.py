import sys
import re

with open('analyze_ichimoku.py', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. We need to inject the rate_forecast_text logic right before `messages = [`
rate_logic = '''
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
        rate_forecast_text = f"📌 [앞으로의 금리의 전망]\\n데이터 수집 오류로 분석을 생략합니다. ({e})"

    messages = ['''

text = text.replace('    messages = [', rate_logic)

# 2. We need to inject {rate_forecast_text} before 📌 [현재 상황 및 배경] in message 3
msg3_target = '''━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 [현재 상황 및 배경]
10년물 국채금리는 글로벌 자산의 '무위험 수익률(할인율)'로'''

msg3_replacement = '''━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{rate_forecast_text}

📌 [현재 상황 및 배경]
10년물 국채금리는 글로벌 자산의 '무위험 수익률(할인율)'로'''

text = text.replace(msg3_target, msg3_replacement)

with open('analyze_ichimoku.py', 'w', encoding='utf-8') as f:
    f.write(text)

print("Updated analyze_ichimoku.py with rate_forecast_text")
