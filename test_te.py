import requests
from bs4 import BeautifulSoup
import re

url = "https://tradingeconomics.com/united-states/business-confidence"
headers = {'User-Agent': 'Mozilla/5.0'}
res = requests.get(url, headers=headers)
soup = BeautifulSoup(res.text, 'html.parser')

try:
    # Find the table row containing ISM Manufacturing PMI
    tables = soup.find_all('table', class_='table table-hover')
    found = False
    for table in tables:
        for row in table.find_all('tr'):
            if row.get('class') and 'datatable-row' in row.get('class'):
                continue # Header row
            cells = row.find_all('td')
            if cells:
                text = cells[0].get_text(strip=True)
                if 'ISM Manufacturing PMI' in text:
                    # Actual is usually the 2nd or 3rd cell depending on table
                    print("Row:", [c.get_text(strip=True) for c in cells])
                    found = True
                    break
        if found:
            break
            
    if not found:
        # Alternative method
        td = soup.find('td', string=re.compile('ISM Manufacturing PMI', re.I))
        if td:
            print("Row td:", [c.get_text(strip=True) for c in td.parent.find_all('td')])
except Exception as e:
    print(e)
