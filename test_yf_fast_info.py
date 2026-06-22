import yfinance as yf
try:
    print("TNX fast_info:", yf.Ticker('^TNX').fast_info.last_price)
except Exception as e:
    print("TNX Error:", e)

try:
    print("IRX fast_info:", yf.Ticker('^IRX').fast_info.last_price)
except Exception as e:
    print("IRX Error:", e)
