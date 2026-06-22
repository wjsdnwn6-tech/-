import FinanceDataReader as fdr

try:
    ism = fdr.DataReader('FRED:NAPM')
    print("NAPM:", ism.tail())
except Exception as e:
    print("Error:", e)
