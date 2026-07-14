import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import scrape_pilar2_myfxbook


class ScrapePilar2MyfxbookTests(unittest.TestCase):
    def test_parse_sentiment_xauusd_row(self):
        html = '''
        <tr class="outlook-symbol-row" symbolid="51" symbolname="XAUUSD">
            <td id="symbolNameCellXAUUSD"><a href="/community/outlook/XAUUSD"> XAUUSD</a></td>
            <td>Short</td><td>53%</td>
            <td>Long</td><td>47%</td>
        </tr>
        '''

        data = scrape_pilar2_myfxbook.parse_sentiment(html)

        self.assertEqual(data["instrument"], "XAU/USD")
        self.assertEqual(data["percent_short"], 53.0)
        self.assertEqual(data["percent_long"], 47.0)

    def test_parse_sentiment_raises_if_no_xauusd_row(self):
        html = '<tr class="outlook-symbol-row" symbolid="52" symbolname="EURUSD"></tr>'

        with self.assertRaises(ValueError):
            scrape_pilar2_myfxbook.parse_sentiment(html)


if __name__ == "__main__":
    unittest.main()
