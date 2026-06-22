import requests
import json

url = "https://finance.yahoo.com/calendar/economic"
headers = {'User-Agent': 'Mozilla/5.0'}
res = requests.get(url, headers=headers)
print("Status:", res.status_code)
print("Length:", len(res.text))
if "ISM Manufacturing PMI" in res.text:
    print("Found ISM Manufacturing PMI in Yahoo Calendar!")
else:
    print("Not found in Yahoo Calendar text")
