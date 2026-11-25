"""Generate a SYNTHETIC dataset that mimics the patterns in ACDC's Iran case study.

Wallets, trades and prices are invented. The structure follows the report:
day-specific "strike by <date>" markets, insiders buying cheap YES shares in the
hours before the event and holding, a sharp simultaneous price jump across the
markets that resolved YES, and skilled traders who pile in and take profit early.
Background markets (election, Fed, a speech market) give the detector something to
not flag. Use it to test the code offline, then swap in real data from fetch_data.py.
"""
from pathlib import Path

import numpy as np
import pandas as pd

rng = np.random.default_rng(21)
T = pd.Timestamp
H = pd.Timedelta(hours=1)


def wallet():
    return "0x" + "".join(rng.choice(list("0123456789abcdef"), 40))


RETAIL = [wallet() for _ in range(400)]
WHALES = [wallet() for _ in range(25)]
INSIDERS = [wallet() for _ in range(4)]        # 3 with a prior record, 1 brand new
FOLLOWERS = [wallet() for _ in range(4)]       # skilled traders who react to the spike

trades, markets = [], []


def logit(p):
    return np.log(p / (1 - p))


def sigmoid(x):
    return 1 / (1 + np.exp(-x))


def add(w, mid, outcome, side, price, usd, ts):
    price = float(np.clip(price, 0.01, 0.99))
    trades.append(dict(wallet=w, market_id=mid, outcome=outcome, side=side,
                       price=round(price, 3), size=round(usd / price, 2), timestamp=ts))


def price_at(path, ts):
    """YES price at a moment in time (hourly path, linear inside the hour)."""
    h = ts.floor("h")
    i = path.index.get_indexer([h])[0]
    if i < 0:
        return path.iloc[-1]
    nxt = path.iloc[min(i + 1, len(path) - 1)]
    frac = (ts - h) / H
    return path.iloc[i] + (nxt - path.iloc[i]) * frac


def market(event, title, opened, end, resolved, winner, p0, p_end, jumps=None,
           event_time=None, activity=6):
    mid = "0x" + "".join(rng.choice(list("0123456789abcdef"), 64))
    markets.append(dict(market_id=mid, event=event, title=title, opened_at=opened,
                        scheduled_end=end, resolved_at=resolved, winning_outcome=winner))
    hours = pd.date_range(opened.floor("h"), resolved.floor("h"), freq="h")
    stop = event_time or resolved
    n_pre = max(1, ((stop - opened) / H))
    x, xs = logit(p0), []
    drift = (logit(p_end) - logit(p0)) / n_pre
    for h in hours:
        x += drift + rng.normal(0, 0.07)
        x += (jumps or {}).get(h, 0)
        xs.append(0.97 if event_time is not None and h >= event_time.floor("h") else sigmoid(x))
    path = pd.Series(xs, index=hours)

    for h in hours:
        busy = activity * (3 if h < opened + 6 * H else 1)   # burst when the market opens
        for _ in range(rng.poisson(busy)):
            ts = h + pd.Timedelta(seconds=int(rng.integers(0, 3600)))
            if ts >= resolved:
                continue
            p = price_at(path, ts)
            if rng.random() < 0.06:
                # whales mostly back the favourite
                w, usd = rng.choice(WHALES), rng.uniform(2_000, 15_000)
                fav = "Yes" if p >= 0.5 else "No"
                outcome = fav if rng.random() < 0.85 else ("No" if fav == "Yes" else "Yes")
            else:
                w = rng.choice(RETAIL)
                usd = rng.uniform(2_600, 7_000) if rng.random() < 0.02 else rng.lognormal(5, 1)
                outcome = "Yes" if rng.random() < 0.5 else "No"
            px = (p if outcome == "Yes" else 1 - p) + rng.normal(0, 0.01)
            add(w, mid, outcome, "BUY", px, usd, ts)
            sell_prob = 0.6 if w in WHALES else 0.08
            if rng.random() < sell_prob:
                later = ts + pd.Timedelta(hours=float(rng.uniform(1, 30)))
                if later < min(resolved, stop):
                    p2 = price_at(path, later)
                    px2 = p2 if outcome == "Yes" else 1 - p2
                    shares = usd / px
                    add(w, mid, outcome, "SELL", px2, shares * rng.uniform(0.5, 1) * px2, later)
    return mid, path


# --- Earlier event: gives three insiders a winning track record -------------
for day in [12, 13, 14]:
    opened, end = T("2025-05-09 12:00", tz="UTC"), T(f"2025-05-{day + 1} 04:00", tz="UTC")
    if day < 13:
        market("Naval blockade", f"Naval blockade announced by May {day}?", opened, end, end,
               "No", 0.15, 0.02)
    else:
        ev = T("2025-05-13 15:00", tz="UTC")
        mid, path = market("Naval blockade", f"Naval blockade announced by May {day}?", opened,
                           end, ev + 0.5 * H, "Yes", 0.2, 0.08,
                           jumps={T("2025-05-13 12:00", tz="UTC"): 1.2}, event_time=ev)
        for w in INSIDERS[:3]:
            ts = T("2025-05-13 11:00", tz="UTC") + pd.Timedelta(minutes=int(rng.integers(0, 110)))
            add(w, mid, "Yes", "BUY", price_at(path, ts), rng.uniform(4_000, 12_000), ts)

# --- The Iran-style event -----------------------------------------------------
STRIKE = T("2025-06-21 22:40", tz="UTC")
RESOLVE = STRIKE + 50 * pd.Timedelta(minutes=1)
opened = T("2025-06-17 14:00", tz="UTC")
EVENT = "US military strike on Iran (June 2025)"
spike_jumps = {T("2025-06-21 19:00", tz="UTC"): 0.35,
               T("2025-06-21 20:00", tz="UTC"): 0.3,
               T("2025-06-21 21:00", tz="UTC"): 1.4}

for day, weekday in [(19, "Thursday"), (20, "Friday")]:
    end = T(f"2025-06-{day + 1} 04:00", tz="UTC")
    mid, path = market(EVENT, f"US military strike on Iran by June {day}?", opened, end, end,
                       "No", 0.14 if day == 19 else 0.3, 0.02)
    if day == 20:   # the report's single losing longshot, placed at market open
        add(rng.choice(RETAIL), mid, "Yes", "BUY", 0.33, 3_100, opened + 2 * H)

for day, p0 in [(21, 0.1), (22, 0.12), (23, 0.14)]:
    end = T(f"2025-06-{day + 1} 04:00", tz="UTC")
    mid, path = market(EVENT, f"US military strike on Iran by June {day}?", opened, end, RESOLVE,
                       "Yes", p0, 0.07, jumps=spike_jumps, event_time=STRIKE)
    # Insiders: split buys over the 3-4 hours before the strike, never sell
    for w in INSIDERS:
        budget = rng.uniform(8_000, 45_000)
        for _ in range(int(rng.integers(3, 7))):
            ts = T("2025-06-21 18:00", tz="UTC") + pd.Timedelta(minutes=int(rng.integers(0, 230)))
            add(w, mid, "Yes", "BUY", price_at(path, ts) + 0.01, budget / 5, ts)
    # Followers: buy after the spike, sell most of it once the news breaks
    for w in FOLLOWERS:
        ts = T("2025-06-21 21:10", tz="UTC") + pd.Timedelta(minutes=int(rng.integers(0, 60)))
        px = price_at(path, ts)
        usd = rng.uniform(3_000, 9_000)
        add(w, mid, "Yes", "BUY", px, usd, ts)
        add(w, mid, "Yes", "SELL", 0.93, usd / px * rng.uniform(0.8, 1) * 0.93, STRIKE + 20 * pd.Timedelta(minutes=1))

# --- Background markets the detector should mostly leave alone ------------------
market("Northland governor race", "Will Candidate A win the 2025 Northland governor race?",
       T("2025-05-20 12:00", tz="UTC"), T("2025-06-11 03:00", tz="UTC"),
       T("2025-06-11 03:00", tz="UTC"), "Yes", 0.3, 0.55, activity=5)
market("Fed decision June 2025", "Fed rate cut at the June 2025 FOMC meeting?",
       T("2025-05-25 12:00", tz="UTC"), T("2025-06-18 18:00", tz="UTC"),
       T("2025-06-18 18:00", tz="UTC"), "No", 0.12, 0.02, activity=5)
market("Press briefing words", "Will the President say 'tariff' during the June 13 press briefing?",
       T("2025-06-11 12:00", tz="UTC"), T("2025-06-13 20:00", tz="UTC"),
       T("2025-06-13 20:00", tz="UTC"), "No", 0.6, 0.3, activity=4)

# --- Simulated case modelled on public charges (April 2026): a service member ------
# A brand-new account makes 13 longshot "Yes" bets on a U.S. military operation in
# Venezuela in the days before it happens, then the markets resolve weeks early.
# Wallet, amounts and timing are invented; only the pattern follows the reporting.
SOLDIER = wallet()
VZ_EVENT = "U.S. military operation in Venezuela (Jan 2026)"
RAID = T("2026-01-03 06:00", tz="UTC")
VZ_RESOLVE = RAID + 2 * H
vz_open = T("2025-12-01 12:00", tz="UTC")
vz_jumps = {T("2026-01-02 23:00", tz="UTC"): 0.25}
vz_titles = [("US military operation removes Maduro by January 31?", T("2026-01-31 23:00", tz="UTC"), 0.07),
             ("US military forces in Venezuela by January 31?", T("2026-01-31 23:00", tz="UTC"), 0.09),
             ("US military strike on Venezuela by January 15?", T("2026-01-15 23:00", tz="UTC"), 0.08)]
vz = []
for title, end, p0 in vz_titles:
    mid, path = market(VZ_EVENT, title, vz_open, end, VZ_RESOLVE, "Yes", p0, p0 * 0.9,
                       jumps=vz_jumps, event_time=RAID, activity=1)
    vz.append((mid, path))
# 13 bets over the week before the operation, never sold
bet_times = sorted(T("2025-12-27 15:00", tz="UTC") + pd.Timedelta(minutes=int(m))
                   for m in rng.integers(0, 6 * 24 * 60, 13))
for i, ts in enumerate(bet_times):
    mid, path = vz[i % 3]
    add(SOLDIER, mid, "Yes", "BUY", rng.uniform(0.065, 0.095), rng.uniform(2_800, 3_200), ts)
# A few honest longshot winners weeks earlier: they should NOT be held
for k in range(3):
    mid, path = vz[k]
    ts = T("2025-12-04 10:00", tz="UTC") + pd.Timedelta(hours=int(rng.integers(0, 240)))
    add(RETAIL[k * 7], mid, "Yes", "BUY", price_at(path, ts), rng.uniform(2_600, 3_400), ts)

out = Path(__file__).parent / "data" / "demo"
out.mkdir(parents=True, exist_ok=True)
tr = pd.DataFrame(trades).sort_values("timestamp")
mk = pd.DataFrame(markets)
tr.to_csv(out / "trades.csv", index=False)
mk.to_csv(out / "markets.csv", index=False)

# Mock responses from an ID-verification vendor (demo only: no real people or biometrics)
ident = {SOLDIER: {"doc": "U.S. passport", "selfie": 98, "liveness": "Passed",
                   "screen": "Occupation: active-duty U.S. armed forces",
                   "conflict": "This market is decided by the U.S. military"}}
for w, job in zip(INSIDERS, ["Defense contractor employee", "Government official",
                             "Defense contractor employee", "No watchlist match"]):
    ident[w] = {"doc": "Passport", "selfie": int(rng.integers(93, 99)), "liveness": "Passed",
                "screen": f"Occupation: {job}" if job != "No watchlist match" else job,
                "conflict": "Possible access to non-public military plans" if job != "No watchlist match" else ""}
import json
(out / "demo_identities.json").write_text(json.dumps(ident, indent=1))
print(f"Wrote {len(tr):,} trades across {len(mk)} markets to {out}/")
print("Planted insider wallets:", ", ".join(w[:8] for w in INSIDERS), "| soldier case:", SOLDIER[:8])
