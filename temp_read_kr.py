import json

with open('scan_results.json', 'r', encoding='utf-8', errors='ignore') as f:
    d = json.load(f)

kr_top30 = d.get('top30', [])
kr_str = ' / '.join([f"{x.get('name', 'N/A')} ({x.get('code', 'N/A')})" for x in kr_top30])

with open('temp_kr_out.txt', 'w', encoding='utf-8') as f:
    f.write(kr_str)

import yfinance as yf
# We also need US top 30
# Can we fetch US top 30?
