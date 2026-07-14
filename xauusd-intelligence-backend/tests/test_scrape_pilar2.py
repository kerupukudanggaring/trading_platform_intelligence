import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import scrape_pilar2


class ScrapePilar2Tests(unittest.TestCase):
    def test_parse_sentiment_from_dukascopy_payload(self):
        payload = [{"title": "XAU/USD", "long": "70.17", "short": "29.83"}]

        data = scrape_pilar2.parse_sentiment(payload)

        self.assertEqual(data["percent_long"], 70.17)
        self.assertEqual(data["percent_short"], 29.83)

    def test_parse_sentiment_fallback_html(self):
        html = "<div>XAU/USD 70.17% 29.83%</div>"

        data = scrape_pilar2.parse_sentiment(html)

        self.assertEqual(data["percent_long"], 70.17)
        self.assertEqual(data["percent_short"], 29.83)


if __name__ == "__main__":
    unittest.main()
