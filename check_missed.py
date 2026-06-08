import FinanceDataReader as fdr
import pandas as pd

krx_desc = fdr.StockListing('KRX-DESC')
krx_price = fdr.StockListing('KRX')
merged = pd.merge(krx_price, krx_desc, on='Code', how='left')
big = merged[merged['Marcap'] >= 100_000_000_000]

all_kws = ['소프트웨어','IT','반도체','전자','컴퓨터','정보기술','하드웨어','통신','미디어','엔터테인먼트','방송','영화','인터넷','게임','자동차','내구소비재','의류','레저','호텔','레스토랑','여행','소비재','식음료','유통','가정용품','개인용품','담배','생활용품','화장품','약품','의료','의약','생물학','은행','보험','금융','증권','지주','산업재','기계','상업','운송','물류','건설','조선','항공','화학','건설자재','금속','채광','종이','포장재','철강','비철금속','에너지','석유','가스','정제','전력','수도','유틸리티','재생에너지','환경','전기','발전','태양광','풍력','부동산','리츠','건설업']
mask = pd.Series(False, index=big.index)
for kw in all_kws:
    mask = mask | big['Industry'].str.contains(kw, na=False, regex=False)
uncovered = big[~mask]

name_col = 'Name_x' if 'Name_x' in uncovered.columns else 'Name'
industries = uncovered['Industry'].dropna().unique()

with open('missed_industries.txt', 'w', encoding='utf-8') as f:
    f.write(f'Covered: {mask.sum()} / {len(big)} ({mask.sum()/len(big)*100:.1f}%)\n')
    f.write(f'Uncovered: {len(uncovered)}\n\n')
    f.write('=== Uncovered Industry values ===\n')
    for ind in sorted(industries):
        cnt = len(uncovered[uncovered['Industry']==ind])
        f.write(f'  [{cnt}] {ind}\n')
    f.write(f'\n=== Top 20 uncovered by market cap ===\n')
    for _, row in uncovered.nlargest(20, 'Marcap').iterrows():
        code = row['Code']
        name = row[name_col]
        cap = row['Marcap'] / 1e12
        ind = row['Industry']
        f.write(f'  {code} {name} | {cap:.1f}조 | {ind}\n')

print('Done! Check missed_industries.txt')
