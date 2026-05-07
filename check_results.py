import json

with open("frontend/dist/scan_results.json", "r", encoding="utf-8") as f:
    data = json.load(f)

themes = data.get("data", [])
print(f"Total themes: {len(themes)}")

for theme in themes:
    name = theme.get("theme", "")
    signals = theme.get("signals", {})
    print(f"\n[{name}]")
    for sig_name, sig_data in signals.items():
        count = len(sig_data) if isinstance(sig_data, list) else 0
        if count > 0:
            tickers = [x.get("ticker", "?") for x in sig_data[:5]]
            print(f"  {sig_name}: {count} stocks -> {tickers}")
        else:
            print(f"  {sig_name}: 0")
