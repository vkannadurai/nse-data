"""
fetch_pcr.py
Fetches PCR, VIX and Max Pain from NSE option chain.
Runs on GitHub Actions every 5 minutes during market hours.
Output: pcr.json (committed to repo root)
Author: vka — Arivu Nilai
"""

import json, time, datetime, os, sys, random
try:
    import requests
except ImportError:
    os.system("pip install requests --quiet")
    import requests

# ── IST helpers ───────────────────────────────────────────────────────────────
def now_ist():
    return datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)

def is_market_open():
    n = now_ist()
    if n.weekday() >= 5:
        return False
    mins = n.hour * 60 + n.minute
    return 555 <= mins <= 935  # 9:15 to 15:35 IST

# ── Browser-like session ──────────────────────────────────────────────────────
def make_session():
    s = requests.Session()
    # Rotate user agents to avoid detection
    uas = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    ]
    s.headers.update({
        "User-Agent": random.choice(uas),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Cache-Control": "max-age=0",
    })
    return s

def warm_up_session(s):
    """Visit NSE homepage first to get session cookies — critical for API access"""
    try:
        r = s.get("https://www.nseindia.com", timeout=10)
        time.sleep(random.uniform(1.5, 3.0))
        # Visit option chain page to set more cookies
        s.headers.update({
            "Referer": "https://www.nseindia.com/",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
        })
        s.get("https://www.nseindia.com/option-chain", timeout=10)
        time.sleep(random.uniform(1.0, 2.0))
        return True
    except Exception as e:
        print(f"Warm-up error: {e}")
        return False

# ── Fetch NSE option chain ────────────────────────────────────────────────────
def fetch_option_chain(s, symbol="NIFTY"):
    url = f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}"
    try:
        r = s.get(url, timeout=15)
        if r.status_code == 200:
            return r.json()
        print(f"Option chain {symbol}: HTTP {r.status_code}")
        return None
    except Exception as e:
        print(f"Option chain {symbol} error: {e}")
        return None

# ── Calculate PCR from option chain ──────────────────────────────────────────
def calc_pcr(data):
    if not data:
        return None, None, None
    try:
        filtered = data.get("filtered", {})
        ce_oi = filtered.get("CE", {}).get("totOI", 0)
        pe_oi = filtered.get("PE", {}).get("totOI", 0)
        if ce_oi > 0:
            pcr = round(pe_oi / ce_oi, 3)
        else:
            pcr = None
        # Underlying value (spot)
        spot = (data.get("records", {}).get("underlyingValue")
                or filtered.get("CE", {}).get("underlyingValue")
                or 0)
        return pcr, int(ce_oi), int(pe_oi)
    except Exception as e:
        print(f"PCR calc error: {e}")
        return None, None, None

# ── Calculate Max Pain ────────────────────────────────────────────────────────
def calc_max_pain(data):
    if not data:
        return None
    try:
        records = data.get("records", {}).get("data", [])
        strikes = {}
        for r in records:
            k = r.get("strikePrice", 0)
            if not k:
                continue
            ce_oi = r.get("CE", {}).get("openInterest", 0) or 0
            pe_oi = r.get("PE", {}).get("openInterest", 0) or 0
            strikes[k] = {"ce": ce_oi, "pe": pe_oi}
        if not strikes:
            return None
        # Max pain = strike where total $ pain for option buyers is maximum for sellers
        all_strikes = sorted(strikes.keys())
        min_pain = float("inf")
        max_pain_strike = None
        for test_k in all_strikes:
            pain = 0
            for k, v in strikes.items():
                # CE pain: all CE buyers above test_k lose
                if k < test_k:
                    pain += v["ce"] * (test_k - k)
                # PE pain: all PE buyers below test_k lose
                if k > test_k:
                    pain += v["pe"] * (k - test_k)
            if pain < min_pain:
                min_pain = pain
                max_pain_strike = test_k
        return max_pain_strike
    except Exception as e:
        print(f"Max pain error: {e}")
        return None

# ── Fetch VIX from Yahoo Finance (backup) ────────────────────────────────────
def fetch_vix_yahoo():
    try:
        r = requests.get(
            "https://query2.finance.yahoo.com/v8/finance/chart/%5EINDIAVIX?range=1d&interval=1d",
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
            timeout=10
        )
        if r.status_code == 200:
            d = r.json()
            res = d.get("chart", {}).get("result", [{}])[0]
            meta = res.get("meta", {})
            v = meta.get("regularMarketPrice") or meta.get("previousClose") or meta.get("chartPreviousClose")
            if v and v > 0:
                return round(float(v), 2)
    except Exception as e:
        print(f"VIX Yahoo error: {e}")
    return None

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    ist = now_ist()
    ist_str = ist.strftime("%Y-%m-%d %H:%M:%S IST")
    market_open = is_market_open()

    print(f"Fetch started: {ist_str} | Market: {'OPEN' if market_open else 'CLOSED'}")

    result = {
        "timestamp": ist_str,
        "market_open": market_open,
        "NIFTY": {"pcr": None, "ce_oi": None, "pe_oi": None, "max_pain": None},
        "BANKNIFTY": {"pcr": None, "ce_oi": None, "pe_oi": None, "max_pain": None},
        "vix": None,
        "status": "ok",
        "error": None
    }

    # Always fetch VIX (works even when market closed)
    vix = fetch_vix_yahoo()
    if vix:
        result["vix"] = vix
        print(f"VIX: {vix}")

    # Fetch PCR only during market hours (NSE API returns stale data otherwise)
    if market_open:
        s = make_session()
        warmed = warm_up_session(s)
        print(f"Session warmed: {warmed}")

        # NIFTY
        ndata = fetch_option_chain(s, "NIFTY")
        if ndata:
            pcr, ce_oi, pe_oi = calc_pcr(ndata)
            max_pain = calc_max_pain(ndata)
            result["NIFTY"] = {
                "pcr": pcr,
                "ce_oi": ce_oi,
                "pe_oi": pe_oi,
                "max_pain": max_pain
            }
            print(f"NIFTY PCR: {pcr} | CE OI: {ce_oi} | PE OI: {pe_oi} | Max Pain: {max_pain}")
        else:
            result["error"] = "NSE option chain blocked"
            print("NIFTY: NSE blocked this run")

        time.sleep(random.uniform(2, 4))

        # BANKNIFTY
        bdata = fetch_option_chain(s, "BANKNIFTY")
        if bdata:
            bpcr, bce, bpe = calc_pcr(bdata)
            bmax = calc_max_pain(bdata)
            result["BANKNIFTY"] = {
                "pcr": bpcr,
                "ce_oi": bce,
                "pe_oi": bpe,
                "max_pain": bmax
            }
            print(f"BANKNIFTY PCR: {bpcr} | Max Pain: {bmax}")
    else:
        print("Market closed — skipping PCR fetch")
        result["status"] = "market_closed"

    # Write output
    out = json.dumps(result, indent=2)
    with open("pcr.json", "w") as f:
        f.write(out)
    print(f"Written pcr.json: {out[:200]}")

if __name__ == "__main__":
    main()
