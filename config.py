"""All thresholds in one place. Defaults follow the ACDC report (April 2026)."""

# Signal 1: longshot bets (ACDC definition)
LONGSHOT_MAX_PRICE = 0.35      # average price <= $0.35 (implied probability <= 35%)
LONGSHOT_MIN_USD = 2_500       # >= $2,500 bought by one wallet within one clock hour

# Signal 2: sudden price acceleration
SPIKE_Z = 2.0                  # hourly price change more than 2 standard deviations above the market's mean

# Signal 3: wallet behaviour (win rate vs exit rate)
INSIDER_MIN_WIN_RATE = 0.80    # share of BUY trades on the winning outcome
INSIDER_MAX_EXIT_RATE = 0.20   # shares sold before close / shares bought
HELD_TO_SETTLEMENT = 0.05      # exit rate at or below this counts as "held to the end"

# Extra signals (not in the report)
NEW_WALLET_HOURS = 14 * 24     # account opened in the last two weeks
CONCENTRATION_SHARE = 0.90     # 90%+ of a wallet's money so far is in this one event...
CONCENTRATION_MIN_BUYS = 3     # ...across at least 3 buys
EARLY_RESOLUTION_WINDOW_H = 7 * 24   # bet placed within 7 days of a market that resolved early

# Score thresholds
LIVE_HIGH = 60                 # live score at or above this -> flag for review
LIVE_MEDIUM = 40
REVIEW_ESCALATE = 60           # post-resolution review score at or above this -> escalate
