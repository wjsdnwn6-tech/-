import sys

with open('analyze_ichimoku.py', 'r', encoding='utf-8') as f:
    text = f.read()

target = 'f"""📊 안티그레비티 통합 전략 리포트 ('
replacement = 'f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n📊 안티그레비티 통합 전략 리포트 ('

# Count to make sure we replace exactly 10
count = text.count(target)
if count != 10:
    print(f"Warning: Found {count} occurrences, expected 10.")
    # Proceeding anyway just in case some are different, but we should replace them.

new_text = text.replace(target, replacement)

with open('analyze_ichimoku.py', 'w', encoding='utf-8') as f:
    f.write(new_text)

print(f"Replaced {count} headers successfully.")
