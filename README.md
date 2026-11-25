# PolyGuard

A prototype compliance tool for Polymarket. PolyGuard flags likely insider bets as they
happen and holds suspicious winnings until the winner verifies their identity. It turns
the three insider-trading signals from the Anti-Corruption Data Collective's report
*Insider Risks in Polymarket Political Markets* (April 2026) into a working system.

Built for ADM 3355 FinTech (Telfer School of Management, University of Ottawa), Fall 2026.

## How to run it (no programming needed)

1. Install Python from [python.org/downloads](https://www.python.org/downloads/).
   On Windows, tick **Add python.exe to PATH** on the first screen.
2. Download this project and unzip it.
3. Double-click the start file:
   - Windows: `start_windows.bat`
   - Mac: `start_mac.command` (if macOS blocks it, right-click it and choose **Open**)
4. Keep the black window open. PolyGuard opens in your browser at `localhost:8501`.
   The first start takes 2 to 5 minutes while it installs what it needs.

PolyGuard opens with a **synthetic demo dataset** modelled on the report's June 2025 Iran
case study. Wallets and amounts in it are invented.

To analyse real data, open **Load real Polymarket data** in the left sidebar, paste one or
more event links from polymarket.com, and click **Download and analyse**.

## What's in the dashboard

| Tab | What it does |
|---|---|
| Flagged bets | Every large longshot bet with a live score, a review score and plain-English reasons |
| Payout holds | Winnings of escalated bets, held until the winner's ID is checked; analysts mark each case as ID requested, released or reported |
| Market replay | Every bet on a market over time, plus hourly price spikes across related markets |
| Wallet behaviour | Win rate vs. how much a wallet sold early; the insider pattern sits top left |
| How scoring works | The scoring rules |

## How it works

| File | What it does |
|---|---|
| `config.py` | Every threshold (longshot size and price, spike sensitivity, score cut-offs) |
| `classify.py` | Rates each market by who decides the outcome (group / individual / public) and whether it is day-specific |
| `signals.py` | Signal 1 longshot bets, Signal 2 price spikes, Signal 3 wallet win rate vs exit rate |
| `scoring.py` | Live score (knowable when the bet is placed) and review score (after resolution), then a status |
| `detector.py` | Runs the whole pipeline; also prints a report with `python detector.py data/demo` |
| `app.py` | The dashboard |
| `fetch_data.py` | Downloads events and trades from Polymarket's public APIs |
| `make_demo_data.py` | Builds the synthetic demo dataset (runs automatically on first launch) |

**Status meanings.** *Escalate*: high live score, the bet won, and the wallet behaved like
an insider (bet shortly before resolution, held to settlement). These go to the hold queue.
*Review*: worth a look. *Low*: nothing notable. *Cleared*: the bet lost.

## Limits

- A winning longshot can come from luck, skill or mispricing. Every flag means
  "needs human review", not proof.
- Market classification uses keywords; a language model would be more accurate.
- Wallets funded from the same source are not linked yet.
- Hold-queue decisions are kept only while the page is open, and no money moves.
- Polymarket's API changes over time. If downloads fail, compare the URLs at the top of
  `fetch_data.py` with [docs.polymarket.com](https://docs.polymarket.com).

## AI use

This prototype was built with help from Claude (Anthropic), an AI assistant, as disclosed
in our report's appendix.
