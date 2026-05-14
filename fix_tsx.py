import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('analyze_ichimoku.py', 'rb') as f:
    data = f.read()
data = data.replace(b'localhost:5173', b'localhost:5174')
data = data.replace(b'127.0.0.1:5173', b'127.0.0.1:5174')
with open('analyze_ichimoku.py', 'wb') as f:
    f.write(data)

try:
    open('analyze_ichimoku.py', 'r', encoding='utf-8').read()
    print("OK")
except:
    print("FAIL")
