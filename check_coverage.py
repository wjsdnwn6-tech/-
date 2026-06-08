import FinanceDataReader as fdr
import pandas as pd

krx_price = fdr.StockListing('KRX')
krx_desc = fdr.StockListing('KRX-DESC')
merged = pd.merge(krx_price, krx_desc, on='Code', how='left')
big = merged[merged['Marcap'] >= 100_000_000_000]  # 시가총액 1000억 이상

print(f"전체 KRX 종목: {len(merged)}개")
print(f"시가총액 1000억 이상: {len(big)}개")
print()

THEMES_KRX = {
    "IT": ["소프트웨어", "IT", "반도체", "전자", "컴퓨터", "정보기술", "하드웨어"],
    "커뮤니케이션": ["통신", "미디어", "엔터테인먼트", "방송", "영화", "인터넷", "게임"],
    "임의소비재": ["자동차", "내구소비재", "의류", "레저", "호텔", "레스토랑", "여행", "소비재"],
    "필수소비재": ["식음료", "유통", "가정용품", "개인용품", "담배", "생활용품", "화장품"],
    "헬스케어(기존)": ["제약", "바이오", "생명공학", "의료기기", "헬스케어"],
    "헬스케어(수정)": ["제약", "바이오", "생명공학", "의료기기", "헬스케어", "약품", "의료", "의약", "생물학"],
    "금융": ["은행", "보험", "금융", "증권", "지주"],
    "산업재": ["산업재", "기계", "상업", "운송", "물류", "건설", "조선", "항공"],
    "소재": ["화학", "건설자재", "금속", "채광", "종이", "포장재", "철강", "비철금속"],
    "에너지": ["에너지", "석유", "가스", "정제"],
    "유틸리티(기존)": ["전력", "수도", "유틸리티", "재생에너지", "환경"],
    "유틸리티(수정)": ["전력", "수도", "유틸리티", "재생에너지", "환경", "전기", "발전", "가스", "태양광", "풍력"],
    "부동산": ["부동산", "리츠", "리츠(REITs)", "건설업"],
}

all_matched = set()
i_col = 'Industry'

for theme, kws in THEMES_KRX.items():
    mask = pd.Series(False, index=big.index)
    for kw in kws:
        mask = mask | big[i_col].str.contains(kw, na=False, regex=False)
    matched = big[mask]
    count = len(matched)
    if '기존' not in theme:
        for code in matched['Code']:
            all_matched.add(code)
    print(f"  {theme}: {count}개 종목")
    if count > 0 and count <= 5:
        print(f"    → {matched['Name_x'].tolist() if 'Name_x' in matched.columns else matched['Name'].tolist()}")

print(f"\n전체 커버: {len(all_matched)} / {len(big)} 종목 ({len(all_matched)/len(big)*100:.1f}%)")
print(f"미스캔 종목: {len(big) - len(all_matched)}개")

# 미스캔 종목 샘플
uncovered = big[~big['Code'].isin(all_matched)]
if len(uncovered) > 0:
    name_col = 'Name_x' if 'Name_x' in uncovered.columns else 'Name'
    print(f"\n=== 미스캔 종목 샘플 (상위 20개) ===")
    top20 = uncovered.nlargest(20, 'Marcap')
    for _, row in top20.iterrows():
        cap_b = row['Marcap'] / 1e12
        print(f"  {row['Code']} {row[name_col]:20s} | 시총 {cap_b:.1f}조 | Industry: {row[i_col]}")
