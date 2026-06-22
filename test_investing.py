import requests
from bs4 import BeautifulSoup
import re

url = "https://kr.investing.com/economic-calendar/ism-manufacturing-pmi-173"
headers = {'User-Agent': 'Mozilla/5.0'}
try:
    res = requests.get(url, headers=headers)
    soup = BeautifulSoup(res.text, 'html.parser')
    # find the latest value
    # it's usually in a table with id 'historyTab' or 'historicEvents'
    table = soup.find('table', {'id': 'historicEvents'})
    if table:
        rows = table.find('tbody').find_all('tr')
        if rows:
            tds = rows[0].find_all('td')
            actual = tds[2].text.strip()
            print("PMI:", actual)
    else:
        # Check if there is another element
        div = soup.find('div', id='historicEvents')
        print("Not found table, html len:", len(res.text))
except Exception as e:
    print("Error:", e)
