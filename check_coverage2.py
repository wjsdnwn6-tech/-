import FinanceDataReader as fdr
import pandas as pd

krx_desc = fdr.StockListing('KRX-DESC')
krx_price = fdr.StockListing('KRX')
merged = pd.merge(krx_price, krx_desc, on='Code', how='left')
big = merged[merged['Marcap'] >= 100_000_000_000]

all_kws = [
    "소프트웨어","IT","반도체","전자","컴퓨터","정보기술","하드웨어",
    "전지","이차전지","영상","음향","측정","정밀기기","케이블","절연선","마그네틱","광학","전구","조명","정보 서비스",
    "통신","미디어","엔터테인먼트","방송","영화","인터넷","게임","오디오","출판","녹음","광고","창작","예술",
    "자동차","내구소비재","의류","레저","호텔","레스토랑","여행","소비재","봉제","의복","가구","가죽","가방","신발","악기","숙박","오락","음식점","교습","학원","교육",
    "식음료","유통","가정용품","개인용품","담배","생활용품","화장품","식품","곡물","전분","음료","도축","육류","수산물","사료","소매","낙농","작물","가정용 기기",
    "제약","바이오","생명공학","의료기기","헬스케어","약품","의료","의약","생물학","연구개발",
    "은행","보험","금융","증권","지주","신탁","집합투자",
    "산업재","기계","상업","운송","물류","건설","조선","항공","선박","보트","엔지니어링","도매","중개","무기","총포탄","경비","경호","폐기물","설비","공사","디자인","컨설팅","경영","사업지원",
    "화학","건설자재","금속","채광","종이","포장재","철강","비철금속","고무","플라스틱","시멘트","석회","유리","합성고무","비료","농약","요업","나무","직물","방적","섬유",
    "에너지","석유","가스","정제","연료",
    "전력","수도","유틸리티","재생에너지","환경","전기","발전","태양광","풍력","증기",
    "부동산","리츠","건설업"
]

mask = pd.Series(False, index=big.index)
for kw in all_kws:
    mask = mask | big['Industry'].str.contains(kw, na=False, regex=False)
uncovered = big[~mask]

name_col = 'Name_x' if 'Name_x' in uncovered.columns else 'Name'

with open('coverage_result.txt', 'w', encoding='utf-8') as f:
    f.write(f'=== Coverage Result ===\n')
    f.write(f'Covered: {mask.sum()} / {len(big)} ({mask.sum()/len(big)*100:.1f}%)\n')
    f.write(f'Still uncovered: {len(uncovered)}\n\n')
    if len(uncovered) > 0:
        f.write('=== Remaining uncovered (top 10 by market cap) ===\n')
        for _, row in uncovered.nlargest(10, 'Marcap').iterrows():
            code = row['Code']
            name = row[name_col]
            cap = row['Marcap'] / 1e12
            ind = row['Industry']
            f.write(f'  {code} {name} | {cap:.1f}조 | {ind}\n')

print('Done! Check coverage_result.txt')
