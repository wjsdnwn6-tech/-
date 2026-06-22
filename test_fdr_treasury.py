import FinanceDataReader as fdr
print(fdr.DataReader('FRED:GS2').tail())
print(fdr.DataReader('FRED:GS10').tail())
