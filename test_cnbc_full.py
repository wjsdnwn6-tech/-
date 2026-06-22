import requests

url = "https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol?symbols=.DXY|KRW=|.VIX|@GC.1|@SI.1|@HG.1|@CL.1|US10Y|US2Y|BTC.CM=&requestMethod=itv&noform=1&partnerId=2&fund=1&exthrs=1&output=json"
res = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
if res.status_code == 200:
    data = res.json()
    quotes = data.get('FormattedQuoteResult', {}).get('FormattedQuote', [])
    print("Fetched:", [q.get('symbol') for q in quotes])
else:
    print("Failed")
