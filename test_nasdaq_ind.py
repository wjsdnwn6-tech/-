import FinanceDataReader as fdr
import json

df = fdr.StockListing('NASDAQ')
industries = df['Industry'].dropna().unique().tolist()

with open('nasdaq_industries.json', 'w', encoding='utf-8') as f:
    json.dump(industries, f, ensure_ascii=False, indent=2)
