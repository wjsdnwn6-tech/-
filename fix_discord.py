import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('analyze_ichimoku.py', 'r', encoding='utf-8') as f:
    content = f.read()

# ── 메시지 1: 매크로 지표 수정 ──
# Fed 금리
content = content.replace("Fed 4.50% (동결)", "Fed 3.50~3.75%")
# CPI
content = content.replace("(CPI / PCE): 3.8% / 3.5%", "(CPI / PCE): 3.3% / 3.5%")
content = content.replace("에너지 급등 → 인플레 재점화 → 연준 매파 선회. P/E 부담 + 단기 조정 트리거",
                          "인플레이션 여전히 목표(2%) 상회. 연준 금리 인하 신중 모드 지속")
# NFP / 실업률 / PMI
content = content.replace("(NFP / 실업률 / PMI): 165K / 4.1% / 48.5", "(NFP / 실업률 / PMI): 178K / 4.3% / 52.7")
content = content.replace("고용 둔화 + PMI 50↓ = 경기 둔화 초입. 스태그플레이션 우려 → 가치주·필수소비재 자금 이동",
                          "고용 증가세 둔화 + 실업률 4.3% 상승. PMI 52.7(확장) but 원자재 가격(Prices 84.6) 급등 → 비용 압박")
# Fed 금리 인사이트
content = content.replace("Higher for Longer. 한계 기업 신용 리스크↑. FCF 우량 대형주 쏠림 양극화",
                          "연준 3.75%까지 인하했으나 추가 인하 속도 둔화. 물가 안정 전까지 신중한 스탠스 유지")
# NFCI
content = content.replace("유동성 NFCI: -0.45", "유동성 NFCI: -0.52")
content = content.replace("완화적이나 유동성 축소 경계감 반영. 추세 반전 시 상승 모멘텀 저해",
                          "금융 환경 완화적 유지(-0.52). 유동성 풍부하나 인플레 재점화 시 급변 가능")

# ── 메시지 4: 원자재 수정 ──
content = content.replace("금 $4,646 / 은 $75.69", "금 $4,720 / 은 $79")
content = content.replace("구리 $6.07", "구리 $6.17")
content = content.replace("WTI $100.63", "WTI $92.78")
content = content.replace("심리적 저항선 돌파", "고유가 지속")
content = content.replace("지정학 갈등 + 공급망 타이트 → 밸류에이션 디레이팅 뇌관",
                          "지정학 리스크 + 공급 우려로 $90대 유지. 중동 휴전 진전 시 하락 가능")

# ── 메시지 5: 밸류에이션 수정 ──
# S&P 500 전체 P/E: Forward ~20.9
content = content.replace("시장 전체 P/E: 22.5배 → 5점 광기", "시장 전체 Forward P/E: 20.9배 → 5점 광기")
# IT P/E 업데이트
content = content.replace("**🔴 IT** → 29.5배", "**🔴 IT** → 37.9배")
content = content.replace("**🟢 금융** → 15.2배 · 2점 불안", "**🟢 금융** → 16.9배 · 3점 중립")

# ── 메시지 7: 유가 수정 ──
content = content.replace("유가 100달러 돌파로 인해 호르무즈 해협", "유가 $90대 지속과 호르무즈 해협")
content = content.replace("유가 100달러 재돌파의 핵심 촉매", "유가 $90대 유지의 핵심 요인")
content = content.replace("유가 $100 재돌파의 핵심 촉매", "유가 고공행진의 핵심 요인")

# ── 메시지 8: 행동 지침 수정 ──
content = content.replace("P/E 22.5배 광기 + 유가 $100 돌파", "Forward P/E 20.9배 + 유가 $93 고공")

# ── 유가 $100 관련 전체 업데이트 ──
content = content.replace("유가 $100 돌파 + 스태그플레이션", "유가 $93 고공 + 비용 압박")
content = content.replace("유가 $100 돌파로 연준 인하 사이클 붕괴", "유가 $93대 지속으로 인플레 하방 경직성 강화")

with open('analyze_ichimoku.py', 'w', encoding='utf-8') as f:
    f.write(content)

import py_compile
try:
    py_compile.compile('analyze_ichimoku.py', doraise=True)
    print("Syntax: OK")
except py_compile.PyCompileError as e:
    print(f"Error: {e}")

print("All indicators updated!")
