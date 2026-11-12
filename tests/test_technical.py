import unittest
import pandas as pd
from autoval.technical import analyze_technical


class TechnicalTests(unittest.TestCase):
    def setUp(self):
        self.prices = pd.Series([100 + i*.15 + (i % 11) for i in range(260)],
                                index=pd.bdate_range("2025-01-01",periods=260))

    def test_shifted_position_no_same_day_trading(self):
        df,_=analyze_technical(self.prices)
        self.assertEqual(float(df["position"].iloc[-1]),float(df["signal"].iloc[-2]))

    def test_higher_cost_never_improves_growth_if_trades_exist(self):
        _,a=analyze_technical(self.prices,0)
        _,b=analyze_technical(self.prices,30)
        self.assertLessEqual(b["strategy_total_return_pct"],a["strategy_total_return_pct"])

    def test_missing_price_rejected(self):
        with self.assertRaises(ValueError):
            analyze_technical(self.prices.iloc[:30])

    def test_duplicate_dates_rejected(self):
        prices=self.prices.copy()
        prices.index=list(prices.index[:-1])+[prices.index[-2]]
        with self.assertRaises(ValueError):
            analyze_technical(prices)

if __name__=="__main__": unittest.main()
