"""
fetch_pcr.py — NSE PCR + VIX + MaxPain fetcher
Author: VKA
Runs every 5 min via GitHub Actions (Mon-Fri 9:15-15:30 IST)
Writes to pcr.json in repo root
"""

import json, os, time, datetime
from pathlib import Path

try:
    import requests
except ImportError:
    os.system('pip install requests -q')
    import requests

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
OUTPUT = Path(__file__).parent / 'pcr.json'
SYMBOLS = ['NIFTY', 'BANKNIFTY']

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://www.nseindia.com/',
    'Connection': 'keep-alive',
}

def now_ist():
    return datetime.datetime.now(IST)

def ts():
    return now_ist().strftime('%Y-%m-%d %H:%M:%S IST')

def load_existing():
    try:
        return json.loads(OUTPUT.read_text())
    except:
        return {}

def get_nse_session():
    s = requests.Session()
    s.headers.update(HEADERS)
    try:
        s.get('https://www.nseindia.com', timeout=10)
        time.sleep(1)
        s.get('https://www.nseindia.com/option-chain', timeout=10)
        time.sleep(1)
        return s
    except Exception as e:
        print(f'Session setup failed: {e}')
        return s

def fetch_option_chain(session, symbol):
    url = f'https://www.nseindia.com/api/option-chain-indices?symbol={symbol}'
    try:
        r = session.get(url, timeout=15)
        if r.status_code != 200:
            print(f'{symbol} option chain: HTTP {r.status_code}')
            return None
        d = r.json()
        records = d.get('records', {}).get('data', [])
        if not records:
            return None
        ce_oi = sum(x.get('CE', {}).get('openInterest', 0) or 0 for x in records if 'CE' in x)
        pe_oi = sum(x.get('PE', {}).get('openInterest', 0) or 0 for x in records if 'PE' in x)
        pcr = round(pe_oi / ce_oi, 2) if ce_oi > 0 else None
        strikes = {}
        for x in records:
            strike = x.get('strikePrice', 0)
            if strike <= 0:
                continue
            ce = x.get('CE', {}).get('openInterest', 0) or 0
            pe = x.get('PE', {}).get('openInterest', 0) or 0
            strikes[strike] = {'ce': ce, 'pe': pe}
        max_pain = None
        if strikes:
            min_pain = float('inf')
            for s in strikes:
                pain = sum(max(0, s - k) * v['ce'] + max(0, k - s) * v['pe'] for k, v in strikes.items())
                if pain < min_pain:
                    min_pain = pain
                    max_pain = s
        return {'pcr': pcr, 'ce_oi': ce_oi, 'pe_oi': pe_oi, 'max_pain': max_pain}
    except Exception as e:
        print(f'{symbol} fetch error: {e}')
        return None

def fetch_vix(session):
    try:
        r = session.get('https://www.nseindia.com/api/allIndices', timeout=10)
        if r.status_code == 200:
            for item in r.json().get('data', []):
                if 'VIX' in item.get('index', '').upper():
                    return round(float(item.get('last', 0)), 2)
    except Exception as e:
        print(f'VIX fetch error: {e}')
    return None

def fetch_vix_yahoo(session):
    try:
        url = 'https://query1.finance.yahoo.com/v8/finance/chart/%5EINDIAVIX?interval=1d&range=1d'
        r = session.get(url, timeout=10)
        if r.status_code == 200:
            result = r.json()['chart']['result'][0]
            return round(float(result['meta']['regularMarketPrice']), 2)
    except Exception as e:
        print(f'Yahoo VIX error: {e}')
    return None

def main():
    print(f'[{ts()}] fetch_pcr.py starting')
    existing = load_existing()
    output = {
        'timestamp': ts(),
        'market_open': True,
        'vix': existing.get('vix'),
        'status': 'ok',
    }
    for sym in SYMBOLS:
        output[sym] = existing.get(sym, {'pcr': None, 'ce_oi': None, 'pe_oi': None, 'max_pain': None})

    session = get_nse_session()

    vix = fetch_vix(session) or fetch_vix_yahoo(session)
    if vix:
        output['vix'] = vix
        print(f'VIX: {vix}')
    else:
        print('VIX: unavailable')

    error = None
    any_success = False
    for sym in SYMBOLS:
        time.sleep(2)
        data = fetch_option_chain(session, sym)
        if data:
            output[sym] = data
            any_success = True
            print(f'{sym}: PCR={data["pcr"]} MaxPain={data["max_pain"]}')
        else:
            error = 'NSE option chain blocked'
            print(f'{sym}: failed')

    if not any_success and error:
        output['error'] = error

    OUTPUT.write_text(json.dumps(output, indent=2))
    print(f'[{ts()}] Done')

if __name__ == '__main__':
    main()
