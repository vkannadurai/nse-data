# nse-data

Auto-fetches NSE PCR, VIX and Max Pain every 5 minutes during market hours.
Used by **Arivu Nilai** — Stock Intelligence Level tool.

## Data available

`pcr.json` — updated every 5 min (Mon-Fri 9:15–15:30 IST):

```json
{
  "timestamp": "2026-06-10 10:30:00 IST",
  "market_open": true,
  "NIFTY":     { "pcr": 1.24, "ce_oi": 85000000, "pe_oi": 105000000, "max_pain": 23200 },
  "BANKNIFTY": { "pcr": 0.98, "ce_oi": 42000000, "pe_oi": 41000000,  "max_pain": 54000 },
  "vix": 15.6,
  "status": "ok"
}
```

## Arivu Nilai integration

In Arivu Nilai → Setup → NSE Data URL → paste:
```
https://raw.githubusercontent.com/vkannadurai/nse-data/main/pcr.json
```

## How it works

GitHub Actions runs `fetch_pcr.py` every 5 minutes.
Script warms up an NSE browser session, fetches option chain, calculates PCR + Max Pain.
Result committed to `pcr.json` in this repo.
Arivu Nilai fetches from `raw.githubusercontent.com` — no CORS issues.

## Author
Annadurai V K (Accenture) — Arivu Nilai project
