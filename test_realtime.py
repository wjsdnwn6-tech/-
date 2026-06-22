import sys
sys.path.append('C:\\Users\\User\\Desktop\\kkkkk')
import analyze_ichimoku

# We just want to call the get_realtime_data function and see the PMI and Treasury yields
data = analyze_ichimoku.get_realtime_data()
print("DGS2:", data.get('DGS2'))
print("TNX:", data.get('TNX'))
print("PMI:", data.get('PMI'))
print("PMI_DATE:", data.get('PMI_DATE'))
