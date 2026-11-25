"""Run the full pipeline. Usage:  python detector.py data/demo"""
import sys
from pathlib import Path

import pandas as pd

from classify import classify_markets
from scoring import score
from signals import exit_rates, find_longshots, prepare, price_spikes, wallet_profiles


def load(folder: str):
    folder = Path(folder)
    return pd.read_csv(folder / "trades.csv"), pd.read_csv(folder / "markets.csv")


def run(trades: pd.DataFrame, markets: pd.DataFrame) -> dict:
    t, m = prepare(trades, markets)
    m = classify_markets(m)
    longshots = find_longshots(t)
    spikes = price_spikes(t)
    exits = exit_rates(t)
    wallets = wallet_profiles(t, longshots)
    alerts = score(longshots, m, spikes, wallets, t, exits)
    return {"trades": t, "markets": m, "longshots": longshots, "spikes": spikes,
            "exits": exits, "wallets": wallets, "alerts": alerts}


def short(wallet: str) -> str:
    return f"{wallet[:6]}…{wallet[-4:]}" if isinstance(wallet, str) and len(wallet) > 12 else wallet


if __name__ == "__main__":
    folder = sys.argv[1] if len(sys.argv) > 1 else "data/demo"
    r = run(*load(folder))
    a = r["alerts"]
    print(f"{len(r['trades']):,} trades | {len(r['markets'])} markets | "
          f"{len(r['longshots'])} longshot bets | {int(r['spikes']['spike'].sum())} price spikes\n")
    print(a["status"].value_counts().to_string(), "\n")
    cols = ["status", "live_score", "review_score", "wallet", "title", "outcome", "usd", "avg_price"]
    view = a[cols].head(20).copy()
    view["wallet"] = view["wallet"].map(short)
    view["title"] = view["title"].str.slice(0, 42)
    print(view.to_string(index=False, float_format=lambda x: f"{x:,.2f}"))
