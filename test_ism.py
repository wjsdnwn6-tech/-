import requests

url = "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-report-on-business/pmi/manufacturing/"
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
try:
    res = requests.get(url, headers=headers, timeout=10)
    print("ISM Status:", res.status_code)
    if res.status_code == 200:
        import re
        # Look for a number pattern
        match = re.search(r'PMI\s*<sup>&reg;</sup>\s*at\s*([\d\.]+)', res.text)
        if match:
            print("Found PMI:", match.group(1))
        else:
            print("No regex match. HTML length:", len(res.text))
            if "PMI" in res.text:
                print("But PMI string is present.")
except Exception as e:
    print("Error:", e)
