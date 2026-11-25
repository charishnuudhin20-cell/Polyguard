"""The report's three red flags, as functions.

Expected columns
  trades : wallet, market_id, outcome, side (BUY/SELL), price, size (shares), timestamp
  markets: market_id, event, title, opened_at, scheduled_end, resolved_at, winning_outcome
"""
import numpy as np
import pandas as pd

import config as C

HOUR = pd.Timedelta(hours=1)


def prepare(trades: pd.DataFrame, markets: pd.DataFrame):
    m = markets.copy()
    for col in ["opened_at", "scheduled_end", "resolved_at"]:
        m[col] = pd.to_datetime(m[col], utc=True, errors="coerce", format="mixed")

    t = trades.copy()
    t["timestamp"] = pd.to_datetime(t["timestamp"], utc=True, format="mixed")
    t["side"] = t["side"].str.upper()
    t["usd"] = t["price"] * t["size"]
    t = t.merge(m[["market_id", "event", "title", "scheduled_end", "resolved_at", "winning_outcome"]],
                on="market_id", how="left")
    # Ignore anything after resolution
    t = t[t["resolved_at"].isna() | (t["timestamp"] <= t["resolved_at"])]
    return t.sort_values("timestamp").reset_index(drop=True), m


# ---------------------------------------------------------------- Signal 1
def find_longshots(t: pd.DataFrame) -> pd.DataFrame:
    """One wallet buying >= $2,500 of one outcome within a clock hour at an average
    price <= $0.35. Grouping by hour catches bets split into many small orders."""
    buys = t[t["side"] == "BUY"].copy()
    buys["hour"] = buys["timestamp"].dt.floor("h")
    g = (buys.groupby(["wallet", "market_id", "outcome", "hour"])
             .agg(usd=("usd", "sum"), shares=("size", "sum"), n_trades=("usd", "size"),
                  first_trade=("timestamp", "min"), last_trade=("timestamp", "max"))
             .reset_index())
    g["avg_price"] = g["usd"] / g["shares"]
    ls = g[(g["usd"] >= C.LONGSHOT_MIN_USD) & (g["avg_price"] <= C.LONGSHOT_MAX_PRICE)].copy()

    meta = t.drop_duplicates("market_id")[["market_id", "event", "title", "scheduled_end",
                                             "resolved_at", "winning_outcome"]]
    ls = ls.merge(meta, on="market_id", how="left")
    ls["hours_to_resolution"] = (ls["resolved_at"] - ls["last_trade"]) / HOUR
    ls["resolved_early"] = ls["resolved_at"] < ls["scheduled_end"] - pd.Timedelta(hours=6)
    ls["won"] = np.where(ls["winning_outcome"].notna(), ls["outcome"] == ls["winning_outcome"], np.nan)
    return ls.reset_index(drop=True)


# ---------------------------------------------------------------- Signal 2
def price_spikes(t: pd.DataFrame, outcome: str = "Yes") -> pd.DataFrame:
    """Hourly change in the BUY price of one outcome; flag rises more than SPIKE_Z
    standard deviations above that market's own average change."""
    b = t[(t["side"] == "BUY") & (t["outcome"] == outcome)].copy()
    b["hour"] = b["timestamp"].dt.floor("h")
    h = (b.groupby(["event", "market_id", "hour"])
          .agg(usd=("usd", "sum"), shares=("size", "sum")).reset_index())
    h["price"] = h["usd"] / h["shares"]
    h = h.sort_values(["market_id", "hour"])
    h["change"] = h.groupby("market_id")["price"].diff()
    stats = h.groupby("market_id")["change"].agg(["mean", "std"])
    h = h.join(stats, on="market_id")
    h["z"] = (h["change"] - h["mean"]) / h["std"].replace(0, np.nan)
    h["spike"] = (h["z"] > C.SPIKE_Z) & (h["change"] > 0)
    # Same-hour spikes across related markets (the report's Iran pattern)
    h["event_spikes_this_hour"] = h.groupby(["event", "hour"])["spike"].transform("sum")
    return h.drop(columns=["mean", "std"]).reset_index(drop=True)


# ---------------------------------------------------------------- Signal 3
def exit_rates(t: pd.DataFrame) -> pd.DataFrame:
    """Per wallet, market and outcome: shares sold before close / shares bought."""
    pos = (t.pivot_table(index=["wallet", "market_id", "outcome"], columns="side",
                         values="size", aggfunc="sum", fill_value=0)
             .reset_index())
    for col in ["BUY", "SELL"]:
        if col not in pos:
            pos[col] = 0.0
    pos = pos[pos["BUY"] > 0]
    pos["exit_rate"] = (pos["SELL"] / pos["BUY"]).clip(upper=1)
    return pos[["wallet", "market_id", "outcome", "BUY", "SELL", "exit_rate"]]


def wallet_profiles(t: pd.DataFrame, longshots: pd.DataFrame) -> pd.DataFrame:
    """Win rate vs exit rate, the report's Figure 15. Uses resolved markets only."""
    r = t[t["winning_outcome"].notna()]
    buys = r[r["side"] == "BUY"].assign(won=lambda d: d["outcome"] == d["winning_outcome"])
    sells = r[r["side"] == "SELL"]

    w = buys.groupby("wallet").agg(n_buys=("won", "size"), n_winning_buys=("won", "sum"),
                                   usd_bought=("usd", "sum"), shares_bought=("size", "sum"))
    w["shares_sold"] = sells.groupby("wallet")["size"].sum()
    w = w.fillna({"shares_sold": 0})
    w["win_rate"] = w["n_winning_buys"] / w["n_buys"]
    w["exit_rate"] = (w["shares_sold"] / w["shares_bought"]).clip(upper=1)

    ls = longshots[longshots["won"].notna()]
    w["longshots"] = ls.groupby("wallet").size()
    w["longshot_wins"] = ls[ls["won"] == True].groupby("wallet").size()  # noqa: E712
    w = w.fillna({"longshots": 0, "longshot_wins": 0})
    w["longshot_win_rate"] = np.where(w["longshots"] > 0, w["longshot_wins"] / w["longshots"], np.nan)
    w["first_seen"] = t.groupby("wallet")["timestamp"].min()
    w["group"] = w.apply(_quadrant, axis=1)
    return w.reset_index()


def _quadrant(row) -> str:
    high_win = row["win_rate"] >= C.INSIDER_MIN_WIN_RATE
    low_exit = row["exit_rate"] <= C.INSIDER_MAX_EXIT_RATE
    if high_win and low_exit:
        return "Insider pattern (wins, holds)"
    if high_win:
        return "Skilled trader (wins, sells early)"
    if row["win_rate"] <= 0.2 and low_exit:
        return "Retail (loses, holds)"
    return "Mixed"
