"""Two-stage scoring.

LIVE SCORE (0-100): only uses what was knowable when the bet was placed, so it
could run in real time. Market risk tier, precision, bet size, price, price spikes,
the wallet's PAST longshot record, and wallet age.

REVIEW SCORE (0-100): computed after the market resolves. Did it win, how close to
resolution was it placed, did the market resolve early (event came before the
scheduled end), and did the wallet hold to settlement instead of taking profit.

STATUS
  Escalate -> high live score AND won AND high review score (hold payout, check identity)
  Review   -> high live score (not lost), or medium live score with a high review score
  Cleared  -> the bet lost
  Low      -> everything else
"""
import numpy as np
import pandas as pd

import config as C

TIER_POINTS = {"high": 25, "medium": 15, "low": 5, "unknown": 10}


def _live(row, spikes, prior, first_seen, buys, data_start):
    pts, why = 0.0, []

    tier = row["risk_tier"]
    pts += TIER_POINTS.get(tier, 10)
    why.append(f"{row['outcome_maker'].title()}-decided market ({tier} risk)")

    if row["precision"] == "high":
        pts += 10
        why.append("Day-specific market")

    size_pts = min(15, 15 * np.log10(row["usd"] / C.LONGSHOT_MIN_USD + 1) / np.log10(41))
    pts += size_pts
    if size_pts >= 8:
        why.append(f"Large bet (${row['usd']:,.0f})")

    pts += 10 * max(0, (C.LONGSHOT_MAX_PRICE - row["avg_price"]) / C.LONGSHOT_MAX_PRICE)

    s = spikes[(spikes["market_id"] == row["market_id"]) & spikes["spike"]
               & (spikes["hour"] >= row["hour"] - pd.Timedelta(hours=1))
               & (spikes["hour"] <= row["hour"] + pd.Timedelta(hours=1))]
    if len(s):
        pts += 10
        why.append("Price spiked around the bet")
        if s["event_spikes_this_hour"].max() >= 2:
            pts += 5
            why.append("Related markets spiked at the same time")

    p = prior[(prior["wallet"] == row["wallet"]) & (prior["resolved_at"] < row["first_trade"])]
    if len(p) >= 2:
        wins = int((p["won"] == True).sum())  # noqa: E712
        if wins / len(p) >= C.INSIDER_MIN_WIN_RATE:
            pts += 20
            why.append(f"Wallet won {wins} of {len(p)} previous longshots")

    # Account-age and concentration signals need enough history to judge against
    enough_history = (row["first_trade"] - data_start) >= pd.Timedelta(hours=C.NEW_WALLET_HOURS)
    seen = first_seen.get(row["wallet"])
    if enough_history and seen is not None and (row["first_trade"] - seen) <= pd.Timedelta(hours=C.NEW_WALLET_HOURS):
        pts += 5
        why.append("New account (under 14 days old)")

    b = buys.get(row["wallet"])
    if enough_history and b is not None:
        b = b[b["timestamp"] <= row["last_trade"]]
        if len(b) >= C.CONCENTRATION_MIN_BUYS:
            share = b.loc[b["event"] == row["event"], "usd"].sum() / b["usd"].sum()
            if share >= C.CONCENTRATION_SHARE:
                pts += 10
                why.append("Wallet bets almost only on this event")

    return round(min(pts, 100)), why


def _review(row, exits):
    if pd.isna(row["won"]):
        return np.nan, ["Market not resolved yet"]
    if not row["won"]:
        return 0, ["Bet lost"]

    pts, why = 0, ["Bet won"]
    h = row["hours_to_resolution"]
    if h <= 12:
        pts += 30
        why.append(f"Placed {h:.1f}h before resolution")
    elif h <= 24:
        pts += 20
        why.append(f"Placed {h:.1f}h before resolution")
    elif h <= 72:
        pts += 10

    if row["resolved_early"] and h <= C.EARLY_RESOLUTION_WINDOW_H:
        pts += 25
        why.append("Market resolved early, soon after the bet")

    e = exits.get((row["wallet"], row["market_id"], row["outcome"]))
    if e is not None and e <= C.HELD_TO_SETTLEMENT:
        pts += 25
        why.append("Held the position to settlement")
    elif e is not None:
        why.append(f"Sold {e:.0%} before close (profit-taking)")

    lwr, n = row.get("wallet_longshot_win_rate"), row.get("wallet_longshots", 0)
    if n >= 2 and lwr >= C.INSIDER_MIN_WIN_RATE:
        pts += 20
        why.append(f"Wallet longshot win rate {lwr:.0%}")

    return min(pts, 100), why


def score(longshots, markets, spikes, wallets, trades, exits):
    if longshots.empty:
        return longshots.assign(live_score=[], review_score=[], status=[], reasons=[])

    ls = longshots.merge(markets[["market_id", "outcome_maker", "risk_tier", "precision"]],
                         on="market_id", how="left")
    ls = ls.merge(wallets[["wallet", "longshot_win_rate", "longshots"]]
                  .rename(columns={"longshot_win_rate": "wallet_longshot_win_rate",
                                   "longshots": "wallet_longshots"}),
                  on="wallet", how="left")
    ls["wallet_longshots"] = ls["wallet_longshots"].fillna(0)

    prior = longshots[longshots["won"].notna()][["wallet", "resolved_at", "won"]]
    first_seen = trades.groupby("wallet")["timestamp"].min().to_dict()
    bt = trades[trades["side"] == "BUY"][["wallet", "timestamp", "event", "usd"]]
    buys = {w: g for w, g in bt[bt["wallet"].isin(set(longshots["wallet"]))].groupby("wallet")}
    exit_map = exits.set_index(["wallet", "market_id", "outcome"])["exit_rate"].to_dict()

    data_start = trades["timestamp"].min()
    live = ls.apply(lambda r: _live(r, spikes, prior, first_seen, buys, data_start), axis=1)
    review = ls.apply(lambda r: _review(r, exit_map), axis=1)
    ls["live_score"] = [x[0] for x in live]
    ls["review_score"] = [x[0] for x in review]
    ls["live_reasons"] = ["; ".join(x[1]) for x in live]
    ls["review_reasons"] = ["; ".join(x[1]) for x in review]
    ls["status"] = ls.apply(_status, axis=1)
    order = {"Escalate": 0, "Review": 1, "Low": 2, "Cleared": 3}
    return (ls.assign(_o=ls["status"].map(order))
              .sort_values(["_o", "live_score"], ascending=[True, False])
              .drop(columns="_o").reset_index(drop=True))


def _status(r):
    if r["won"] is False or r["won"] == 0:
        return "Cleared"
    if (r["live_score"] >= C.LIVE_HIGH and r["won"] == True  # noqa: E712
            and r["review_score"] >= C.REVIEW_ESCALATE):
        return "Escalate"
    if r["live_score"] >= C.LIVE_HIGH or (
            r["live_score"] >= C.LIVE_MEDIUM and r["review_score"] >= C.REVIEW_ESCALATE):
        return "Review"
    return "Low"
