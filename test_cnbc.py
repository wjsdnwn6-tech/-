import requests

url = "https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol?symbols=US10Y|US2Y&requestMethod=itv&noform=1&partnerId=2&fund=1&exthrs=1&output=json"
res = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
if res.status_code == 200:
    for q in res.json().get('FormattedQuoteResult', {}).get('FormattedQuote', []):
        sym = q.get('symbol', '')
        last = q.get('last', '')
        print(f"{sym}: {last}")
else:
    print("Failed")
