import re

with open('analyze_ichimoku.py', 'r', encoding='utf-8') as f:
    content = f.read()

replacements = [
    # KRX limit
    ("fresh_krx.sort_values('ChagesRatio', ascending=False).head(30)", 
     "fresh_krx.sort_values('ChagesRatio', ascending=False).head(70)"),
    ("당일 한국 주식 상승률 상위 30 종목 분석", "당일 한국 주식 상승률 상위 70 종목 분석"),
    ("당일 상승률 상위 30종목 주요 섹터 분포", "당일 상승률 상위 70종목 주요 섹터 분포"),
    ("상승률 상위 30종목 섹터별 분류", "상승률 상위 70종목 섹터별 분류"),
    
    # US limit
    ("count=30'", "count=70'"),
    ("for q in quotes[:30]:", "for q in quotes[:70]:"),
    ("당일 미국 주식 상승률 상위 30 종목 분석", "당일 미국 주식 상승률 상위 70 종목 분석"),
    
    # Labels
    ('"top30_pattern_match": "🔥 급등주 선행 패턴 일치 (조건)",',
     '"top30_pattern_match": "🔥 최신 차트 트렌드 패턴 일치(조건)",'),
    ('"top30_shape_match": "📈 급등주 선행 패턴 일치 (모양)",',
     '"top30_shape_match": "📈 최신 차트 트렌드 패턴 일치(모양)",')
]

for old, new in replacements:
    if old in content:
        content = content.replace(old, new)
        print(f"Successfully replaced: {old[:20]}...")
    else:
        print(f"Failed to find: {old[:20]}...")

with open('analyze_ichimoku.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Patch 9 applied.")
