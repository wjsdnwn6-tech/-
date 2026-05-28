import requests
import json
import yfinance as yf

# 1. Get KRX Top 30 from scan_results.json
try:
    with open('scan_results.json', 'r', encoding='utf-8', errors='ignore') as f:
        d = json.load(f)
    kr_top30 = d.get('top30', [])
    kr_str = ' / '.join([f"{x.get('name', '')} ({x.get('code', '')})" for x in kr_top30[:30]])
except Exception as e:
    kr_str = f"Error reading KRX data: {e}"

# 2. Get US Top 30 gainers
us_str = ""
try:
    url = 'https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?formatted=false&lang=en-US&region=US&scrIds=day_gainers&count=30'
    headers = {'User-Agent': 'Mozilla/5.0'}
    r = requests.get(url, headers=headers)
    data = r.json()
    quotes = data['finance']['result'][0]['quotes']
    
    us_stocks = []
    for q in quotes:
        symbol = q.get('symbol')
        name = q.get('shortName') or q.get('longName') or symbol
        us_stocks.append({'symbol': symbol, 'name': name})
    
    # Get sectors
    symbols = [x['symbol'] for x in us_stocks]
    # To speed up, we can use yf.Tickers
    tickers = yf.Tickers(' '.join(symbols))
    for stock in us_stocks:
        try:
            info = tickers.tickers[stock['symbol']].info
            stock['sector'] = info.get('sector', 'Unknown Sector')
        except:
            stock['sector'] = 'Unknown Sector'
            
    # Format US stocks
    us_str = ' / '.join([f"[{x['sector']}] {x['name']} ({x['symbol']})" for x in us_stocks])
except Exception as e:
    us_str = f"Error reading US data: {e}"

# Write result to a text file
with open('report9_output.txt', 'w', encoding='utf-8') as f:
    f.write(f"🇰🇷 한국 주식 상승률 상위 30종목:\n{kr_str}\n\n")
    f.write(f"🇺🇸 미국 주식 상승률 상위 30종목 및 섹터:\n{us_str}\n")
