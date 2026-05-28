import yfinance as yf
ticker = "AAPL"
tkr = yf.Ticker(ticker)

try:
    print("fast_info attribute 'last_price':", tkr.fast_info.last_price)
except Exception as e:
    print("fast_info attribute 'last_price' failed:", e)

try:
    print("fast_info key 'lastPrice':", tkr.fast_info['lastPrice'])
except Exception as e:
    print("fast_info key 'lastPrice' failed:", e)
