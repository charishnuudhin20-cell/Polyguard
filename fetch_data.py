"""Pull real Polymarket data for one or more events into data/<name>/.

Usage
  python fetch_data.py --event-slug <slug> [<slug> ...] --name iran_june_2025

The slug is the last part of the event URL: polymarket.com/event/<slug>.
Tip: include a few earlier events in the same category so wallets have a history.

APIs used (public, no key): Gamma API for events/markets, Data API for trades.
Polymarket is migrating some endpoints to v2; if a request fails, check
https://docs.polymarket.com for the current paths and adjust GAMMA/DATA below.
"""
import argparse
import json
import time
from pathlib import Path

import pandas as pd
import requests

GAMMA = "https://gamma-api.polymarket.com"
DATA = "https://data-api.polymarket.com"
PAGE = 500


def get_json(url, params):
    for attempt in range(5):
        r = requests.get(url, params=params, timeout=30)
        if r.status_code == 429:                   # rate limited: back off and retry
            time.sleep(2 ** attempt)
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()


def unwrap(payload):
    """Handle both plain lists and the newer {"data": [...]} envelope."""
    return payload.get("data", []) if isinstance(payload, dict) else payload


def _list(value):
    return json.loads(value) if isinstance(value, str) else (value or [])


def fetch_event(slug):
    events = unwrap(get_json(f"{GAMMA}/events", {"slug": slug}))
    if not events:
        raise ValueError(f"no event found for '{slug}'")
    ev = events[0]
    rows = []
    for m in ev.get("markets", []):
        outcomes, prices = _list(m.get("outcomes")), [float(p) for p in _list(m.get("outcomePrices"))]
        winner = None
        if m.get("closed") and prices and max(prices) > 0.95:
            winner = outcomes[prices.index(max(prices))]
        rows.append(dict(
            market_id=m["conditionId"], event=ev.get("title", slug), title=m.get("question"),
            opened_at=m.get("startDate") or m.get("createdAt"), scheduled_end=m.get("endDate"),
            resolved_at=m.get("closedTime") or (m.get("endDate") if m.get("closed") else None),
            winning_outcome=winner))
    return rows


def fetch_trades(condition_id, include_maker=False, max_rows=200_000):
    rows, offset = [], 0
    while offset < max_rows:
        params = {"market": condition_id, "limit": PAGE, "offset": offset,
                  "takerOnly": str(not include_maker).lower()}
        try:
            batch = unwrap(get_json(f"{DATA}/trades", params))
        except requests.HTTPError as e:
            print(f"   stopped at offset {offset}: {e}")   # some deployments cap deep offsets
            break
        if not batch:
            break
        rows += batch
        offset += PAGE
        time.sleep(0.2)
    return rows


def normalise(raw):
    t = pd.DataFrame(raw)
    if t.empty:
        return t
    t = t.rename(columns={"proxyWallet": "wallet", "conditionId": "market_id"})
    t["timestamp"] = pd.to_datetime(t["timestamp"], unit="s", utc=True)
    t["price"] = t["price"].astype(float)
    t["size"] = t["size"].astype(float)
    keys = [c for c in ["transactionHash", "wallet", "asset", "side", "size", "price"] if c in t]
    t = t.drop_duplicates(keys)
    return t[["wallet", "market_id", "outcome", "side", "price", "size", "timestamp"]]


DATA_DIR = Path(__file__).parent / "data"
COLUMNS = ["wallet", "market_id", "outcome", "side", "price", "size", "timestamp"]


def fetch_to_folder(slugs, name, include_maker=False, log=print):
    """Download events + trades and save them as data/<name>/. Used by the app and the CLI."""
    markets, trades = [], []
    for slug in slugs:
        log(f"Event: {slug}")
        for m in fetch_event(slug):
            markets.append(m)
            raw = fetch_trades(m["market_id"], include_maker)
            log(f"   {len(raw):>6} trades  {m['title']}")
            t = normalise(raw)
            if not t.empty:
                trades.append(t)
    if not trades:
        raise ValueError("those events have no trades yet")
    out = DATA_DIR / name
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(markets).to_csv(out / "markets.csv", index=False)
    all_trades = pd.concat(trades, ignore_index=True)[COLUMNS]
    all_trades.to_csv(out / "trades.csv", index=False)
    return f"Loaded {len(all_trades):,} trades across {len(markets)} markets into '{name}'."


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--event-slug", nargs="+", required=True)
    ap.add_argument("--name", required=True, help="folder name under data/")
    ap.add_argument("--include-maker", action="store_true",
                    help="also pull maker-side fills (more complete, but check for double counting)")
    args = ap.parse_args()

    print(fetch_to_folder(args.event_slug, args.name, args.include_maker))
    print("Now start the dashboard and pick this dataset in the sidebar.")


if __name__ == "__main__":
    main()
