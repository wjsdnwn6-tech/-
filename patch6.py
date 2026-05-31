import re

with open('analyze_ichimoku.py', 'r', encoding='utf-8') as f:
    content = f.read()

# KRX Patch
krx_target = '''        report_lines.append(f"\\n📈 [상승률 상위 30종목 표]")
        for idx, (_, row) in enumerate(top30.iterrows(), 1):
            name = str(row.get('Name_x', row.get('Name', row['Code'])))
            code = str(row['Code'])
            market = "KS" if str(row.get('Market_x', row.get('Market', ''))) == 'KOSPI' else "KQ"
            chg = float(row.get('ChagesRatio', 0.0))
            theme = str(row.get('Theme', '-'))
            t_name = theme if theme == '기타/확인불가' or theme.endswith('관련주') else theme + ' 관련주'
            report_lines.append(f"{idx:02d}위 | {name} ({code}.{market}) (+{chg:.2f}%) | {t_name}")'''

krx_replacement = '''        report_lines.append(f"\\n📈 [상승률 상위 30종목 섹터별 분류]")
        theme_groups = {}
        for idx, (_, row) in enumerate(top30.iterrows(), 1):
            name = str(row.get('Name_x', row.get('Name', row['Code'])))
            chg = float(row.get('ChagesRatio', 0.0))
            theme = str(row.get('Theme', '-'))
            t_name = theme if theme == '기타/확인불가' or theme.endswith('관련주') else theme + ' 관련주'
            
            if t_name not in theme_groups:
                theme_groups[t_name] = []
            theme_groups[t_name].append(f"{name}(+{chg:.1f}%)")
            
        sorted_themes = sorted(theme_groups.items(), key=lambda x: len(x[1]), reverse=True)
        for t_name, stocks in sorted_themes:
            report_lines.append(f"\\n🔹 **{t_name}** ({len(stocks)}종목)")
            chunks = [stocks[i:i + 4] for i in range(0, len(stocks), 4)]
            for chunk in chunks:
                report_lines.append("  └ " + ", ".join(chunk))'''

if krx_target in content:
    content = content.replace(krx_target, krx_replacement)
else:
    print("Failed to find KRX target.")


# US Patch
us_target = '''        report_lines.append(f"\\n📈 [상승률 상위 종목 표]")
        for idx, info in enumerate(top30_info, 1):
            sec_display = translate_to_ko(info['sector']) if info['sector'] != 'Unknown' else '기타/확인불가'
            s_name = sec_display if sec_display == '기타/확인불가' or sec_display.endswith('관련주') else sec_display + ' 관련주'
            chg = float(info['chg'])
            report_lines.append(f"{idx:02d}위 | {info['sym']} {info['name']} (+{chg:.2f}%) | {s_name}")'''

us_replacement = '''        report_lines.append(f"\\n📈 [상승률 상위 종목 섹터별 분류]")
        theme_groups = {}
        for idx, info in enumerate(top30_info, 1):
            sec_display = translate_to_ko(info['sector']) if info['sector'] != 'Unknown' else '기타/확인불가'
            s_name = sec_display if sec_display == '기타/확인불가' or sec_display.endswith('관련주') else sec_display + ' 관련주'
            chg = float(info['chg'])
            
            if s_name not in theme_groups:
                theme_groups[s_name] = []
            theme_groups[s_name].append(f"{info['sym']}(+{chg:.1f}%)")
            
        sorted_themes = sorted(theme_groups.items(), key=lambda x: len(x[1]), reverse=True)
        for s_name, stocks in sorted_themes:
            report_lines.append(f"\\n🔹 **{s_name}** ({len(stocks)}종목)")
            chunks = [stocks[i:i + 4] for i in range(0, len(stocks), 4)]
            for chunk in chunks:
                report_lines.append("  └ " + ", ".join(chunk))'''

if us_target in content:
    content = content.replace(us_target, us_replacement)
else:
    print("Failed to find US target.")

with open('analyze_ichimoku.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Formatting successfully updated.")
