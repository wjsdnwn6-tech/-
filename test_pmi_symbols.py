import FinanceDataReader as fdr

try:
    print(fdr.DataReader('FRED:MAN_PMI').tail())
except Exception as e:
    pass

try:
    print(fdr.DataReader('FRED:PMI').tail())
except Exception as e:
    pass
