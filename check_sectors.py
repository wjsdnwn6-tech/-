import FinanceDataReader as fdr

krx_desc = fdr.StockListing('KRX-DESC')

with open('krx_sectors.txt', 'w', encoding='utf-8') as f:
    f.write('=== Sector ===\n')
    for v in sorted(krx_desc['Sector'].dropna().unique()):
        f.write(v + '\n')

    f.write('\n=== Industry (healthcare keywords test) ===\n')
    kws = ['제약', '바이오', '생명공학', '의료기기', '헬스케어', '약품', '의료']
    for kw in kws:
        matches = krx_desc[krx_desc['Industry'].str.contains(kw, na=False)]
        f.write(f'{kw}: {len(matches)} matches\n')
        if len(matches) > 0:
            f.write(f'  samples: {matches["Industry"].head(3).tolist()}\n')

    # Sector에서도 검색
    f.write('\n=== Sector healthcare keywords test ===\n')
    for kw in kws:
        matches = krx_desc[krx_desc['Sector'].str.contains(kw, na=False)]
        f.write(f'{kw} in Sector: {len(matches)} matches\n')

    f.write('\n=== All unique Sector values ===\n')
    for v in sorted(krx_desc['Sector'].dropna().unique()):
        f.write(f'  "{v}"\n')

print('Done! Check krx_sectors.txt')
