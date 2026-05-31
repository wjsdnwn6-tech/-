import re

with open('analyze_ichimoku.py', 'r', encoding='utf-8') as f:
    content = f.read()

target1 = '''    all_scan_results = []
    skip_scan = False'''

replacement1 = '''    all_scan_results = []
    skip_scan = False
    
    # 1. Top 30 급등주 수집 및 디스코드 리포트 텍스트 생성
    top30_krx_text, top30_data = get_top30_krx_gainers()
    top30_us_text, us_top30_tickers = get_top30_us_gainers()'''

content = content.replace(target1, replacement1)

target2 = '''    if not skip_scan:
        for theme_name in THEMES.keys():'''

replacement2 = '''    if not skip_scan:
        # 2. 전체 주식 스캔 전, Top 30 종목들을 바탕으로 패턴 템플릿(옵션 A+B) 추출
        build_top30_templates([d['code'] for d in top30_data], us_top30_tickers)
        
        for theme_name in THEMES.keys():'''

content = content.replace(target2, replacement2)

with open('analyze_ichimoku.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Main execution logic patched successfully.")
