import requests
from bs4 import BeautifulSoup
import re

url = "https://tradingeconomics.com/united-states/business-confidence"
headers = {'User-Agent': 'Mozilla/5.0'}
res = requests.get(url, headers=headers)
soup = BeautifulSoup(res.text, 'html.parser')

try:
    table = soup.find('table', {'id': 'calendar'})
    if not table:
        table = soup.find('table', class_='table table-hover')
    
    # Or just find the first row containing 'ISM Manufacturing PMI'
    td = soup.find('td', text=re.compile('ISM Manufacturing PMI', re.I))
    if td:
        print("Found via TD:", td.find_next('td').text.strip())
    else:
        print("Not found via TD")
        # Try finding the 'Actual' value from the chart header or latest value
        div = soup.find('div', id='ctl00_ContentPlaceHolder1_ctl00_ctl01_Panel1')
        print(div)
except Exception as e:
    print(e)
