import requests

def _fetch_fred_api(series_id, limit=1):
    api_key = "30a43f5d9b174fbf3c07ea81950ebd29"
    try:
        url = f"https://api.stlouisfed.org/fred/series/observations?series_id={series_id}&api_key={api_key}&file_type=json&sort_order=desc&limit={limit}"
        res = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        print("Status code:", res.status_code)
        if res.status_code == 200:
            obs = res.json().get('observations', [])
            if obs and obs[0].get('value') not in (None, '.', ''):
                return float(obs[0]['value']), obs[0].get('date', '')
    except Exception as e:
        print("Error:", e)
    return None, None

print(_fetch_fred_api('NAPM'))
print(_fetch_fred_api('DGS2'))
print(_fetch_fred_api('DGS10'))
