import re

with open('analyze_ichimoku.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_code = '''            if len(TOP30_TEMPLATES) > 0:
                current_feat = extract_current_features(df)
                if is_pattern_matched(current_feat, TOP30_TEMPLATES):
                    signals.append("top30_pattern_match")'''

new_code = '''            if len(TOP30_TEMPLATES) > 0:
                current_feat = extract_current_features(df)
                cond_match, shape_match = is_pattern_matched(current_feat, TOP30_TEMPLATES)
                if cond_match:
                    signals.append("top30_pattern_match")
                if shape_match:
                    signals.append("top30_shape_match")'''

if old_code in content:
    content = content.replace(old_code, new_code)
    
    # 딕셔너리에 top30_shape_match 라벨과 텍스트 변경
    content = content.replace('"top30_pattern_match": "🔥 급등 전조 패턴 (Top 30 그림자 매칭)",', '"top30_pattern_match": "🔥 급등주 선행 패턴 일치 (조건)",\n    "top30_shape_match": "📈 급등주 선행 패턴 일치 (모양)",')
    
    # 혹시 옛날 텍스트로 저장되어있을 경우 대비
    content = content.replace('"top30_pattern_match": "🔥 당일 급등 전조 패턴 (Top 30 그림자 매칭)",', '"top30_pattern_match": "🔥 급등주 선행 패턴 일치 (조건)",\n    "top30_shape_match": "📈 급등주 선행 패턴 일치 (모양)",')
    content = content.replace('"top30_pattern_match": "🔥 급등 전조 패턴 (Top 30 그림자 매칭)"', '"top30_pattern_match": "🔥 급등주 선행 패턴 일치 (조건)",\n    "top30_shape_match": "📈 급등주 선행 패턴 일치 (모양)"')

    with open('analyze_ichimoku.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Call site patched successfully.")
else:
    print("Could not find the old code snippet.")
