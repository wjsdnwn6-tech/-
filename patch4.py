import re

with open('analyze_ichimoku.py', 'r', encoding='utf-8') as f:
    content = f.read()

target = '''                    if is_breakout or is_support:
                        signals.append("ma200_support_breakout")
                except Exception as e:
                    logger.debug(f"{ticker} MA200 분석 오류: {e}")'''

if target not in content:
    # Try finding it dynamically
    idx = content.find('signals.append("ma200_support_breakout")')
    if idx != -1:
        end_idx = content.find('logger.debug', idx)
        end_idx = content.find('\n', end_idx)
        target = content[idx-50:end_idx]

injection = '''

            # Top 30 그림자 (급등 전조 패턴) 매칭 (옵션 A + B)
            if len(TOP30_TEMPLATES) > 0:
                current_feat = extract_current_features(df)
                if current_feat:
                    cond_match, shape_match = is_pattern_matched(current_feat, TOP30_TEMPLATES)
                    if cond_match:
                        signals.append("top30_pattern_match")
                    if shape_match:
                        signals.append("top30_shape_match")'''

if "top30_shape_match" not in content:
    try:
        idx = content.find('signals.append("ma200_support_breakout")')
        end_idx = content.find('logger.debug', idx)
        end_idx = content.find('\n', end_idx)
        target_exact = content[idx-100:end_idx]
        
        # We know it's right after logger.debug
        content = content[:end_idx] + injection + content[end_idx:]
        
        # update labels
        content = content.replace('"top30_pattern_match": "🔥 급등 전조 패턴 (Top 30 그림자 매칭)",', '"top30_pattern_match": "🔥 급등주 선행 패턴 일치 (조건)",\n    "top30_shape_match": "📈 급등주 선행 패턴 일치 (모양)",')
        content = content.replace('"top30_pattern_match": "🔥 당일 급등 전조 패턴 (Top 30 그림자 매칭)",', '"top30_pattern_match": "🔥 급등주 선행 패턴 일치 (조건)",\n    "top30_shape_match": "📈 급등주 선행 패턴 일치 (모양)",')
        
        # Add to the initial dictionary
        content = content.replace('"top30_pattern_match": []', '"top30_pattern_match": [],\n        "top30_shape_match": []')
        
        # Add to labels
        if "top30_shape_match" not in content:
             content = content.replace('"top30_pattern_match": "🔥 급등 전조 패턴 (Top 30 그림자 매칭)"', '"top30_pattern_match": "🔥 급등주 선행 패턴 일치 (조건)",\n    "top30_shape_match": "📈 급등주 선행 패턴 일치 (모양)"')

        with open('analyze_ichimoku.py', 'w', encoding='utf-8') as f:
            f.write(content)
        print("Successfully injected.")
    except Exception as e:
        print("Failed:", e)
else:
    print("Already injected.")
