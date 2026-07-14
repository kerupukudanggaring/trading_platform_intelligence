import requests

url = 'https://www.myfxbook.com/community/outlook'
headers = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9,id;q=0.8',
    'Referer': 'https://www.myfxbook.com/',
}
resp = requests.get(url, headers=headers, timeout=20)
print('status', resp.status_code)
text = resp.text
print('contains symbolname="XAUUSD"', 'symbolname="XAUUSD"' in text)
print('contains XAUUSD', 'XAUUSD' in text)
print(text[:400].replace('\n', ' '))
