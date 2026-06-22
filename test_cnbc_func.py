import requests

def _fetch_cnbc_quote(*symbols):
    """CNBC API에서 실시간 시세 조회 (DGS2, Fed금리, VIX 등)"""
    try:
        sym_str = '|'.join(symbols)
        url = f"https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol?symbols={sym_str}&requestMethod=itv&noform=1&partnerId=2&fund=1&exthrs=1&output=json"
        res = requests.get(url, timeout=8, headers={'User-Agent': 'Mozilla/5.0'})
        if res.status_code == 200:
            result = {}
            for q in res.json().get('FormattedQuoteResult', {}).get('FormattedQuote', []):
                sym = q.get('symbol', '')
                last = q.get('last', '').replace('%', '').replace(',', '')
                try:
                    result[sym] = float(last)
                except ValueError:
                    pass
            return result
        else:
            print("Status Code:", res.status_code)
    except Exception as e:
        print("Exception:", e)
    return {}

print("Result:", _fetch_cnbc_quote('.DXY', 'KRW=', '.VIX', '@GC.1', '@SI.1', '@HG.1', '@CL.1', 'US10Y', 'US2Y', 'BTC.CM='))
