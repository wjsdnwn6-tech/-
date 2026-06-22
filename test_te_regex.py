import requests
import re

url = "https://tradingeconomics.com/united-states/business-confidence"
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}
res = requests.get(url, headers=headers)
print("Status:", res.status_code)

if res.status_code == 200:
    text = res.text
    # Search for patterns like ISM Manufacturing PMI or 54.0
    matches = re.findall(r'ISM Manufacturing PMI.*?(?=</tr>)', text, re.IGNORECASE | re.DOTALL)
    if matches:
        print("Found row:", matches[0])
    else:
        print("Not found row. Searching for 54.0...")
        matches2 = re.findall(r'<td[^>]*>.*?54\.0.*?</td>', text, re.IGNORECASE | re.DOTALL)
        for m in matches2[:5]:
            print("Match 54.0:", m)
