"""PolyGuard dashboard. Easiest start: double-click start_windows.bat or start_mac.command.
Or from a terminal:  streamlit run app.py"""
import hashlib
import json
import re
import subprocess
import time
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import config as C
import detector
from signals import wallet_profiles

st.set_page_config(page_title="PolyGuard", page_icon="🛡️", layout="wide")
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;600;750&display=swap');
html, body, [class*="css"], .stMarkdown, .stDataFrame { font-family: 'Public Sans', system-ui, sans-serif; }
h1 { font-weight: 750; letter-spacing: -0.02em; }
div[data-testid="stMetricValue"] { font-weight: 750; }
.status-escalate { color: #b3261e; font-weight: 600; }
.pg-chip { display:inline-block; padding:2px 10px; margin:0 6px 6px 0; border-radius:999px;
           background:#fbe9e7; color:#8c1d18; font-size:0.85rem; }
.pg-badge { display:inline-block; padding:3px 12px; border-radius:999px; font-weight:600; font-size:0.85rem; }
.pg-ok { color:#1b6e3a; } .pg-warn { color:#b3261e; font-weight:600; }
</style>""", unsafe_allow_html=True)

COLORS = {"Escalate": "#b3261e", "Review": "#c98a14", "Low": "#7b8794", "Cleared": "#b8c2cc"}
GROUP_COLORS = {"Insider pattern (wins, holds)": "#b3261e",
                "Skilled trader (wins, sells early)": "#2f5d8a",
                "Retail (loses, holds)": "#3e4a56", "Mixed": "#c3cbd3"}
FONT = dict(family="Public Sans, system-ui, sans-serif", size=13, color="#15202b")
DATA = Path(__file__).parent / "data"


@st.cache_data(show_spinner="Running detector…")
def run(folder: str):
    return detector.run(*detector.load(folder))


def style(fig, height=420):
    fig.update_layout(template="simple_white", font=FONT, height=height,
                      margin=dict(l=10, r=10, t=40, b=10), legend_title_text="")
    return fig


short = detector.short

def list_datasets():
    if not DATA.exists():
        return []
    return sorted(p.name for p in DATA.glob("*") if (p / "trades.csv").exists())


def slug_from(text: str) -> str:
    """Accept a full polymarket.com link or just the slug."""
    text = text.strip().rstrip("/")
    m = re.search(r"polymarket\.com/event/([^/?#]+)", text)
    return m.group(1) if m else text.split("/")[-1].split("?")[0]


# ------------------------------------------------------------------ data
if not list_datasets():   # first launch: build the demo dataset automatically
    with st.spinner("Building the demo dataset (first launch only)…"):
        subprocess.run([sys.executable, str(Path(__file__).parent / "make_demo_data.py")], check=True)

datasets = list_datasets()

with st.sidebar:
    st.header("🛡️ PolyGuard")
    name = st.selectbox("Dataset", datasets,
                        index=datasets.index(st.session_state.get("just_loaded"))
                        if st.session_state.get("just_loaded") in datasets else 0)
    if name.startswith("demo"):
        st.warning("Synthetic demo data: an Iran-style case (ACDC report) and a simulated case "
                   "modelled on the April 2026 charges against a U.S. service member. Wallets, "
                   "amounts and identity checks are invented.")

    with st.expander("➕ Load real Polymarket data"):
        st.caption("Paste one or more event links from polymarket.com, one per line. "
                   "Add a few older events in the same category so wallets have a history.")
        links = st.text_area("Event links", placeholder="https://polymarket.com/event/…")
        new_name = st.text_input("Name this dataset", value="real_data")
        if st.button("Download and analyse", type="primary", disabled=not links.strip()):
            import fetch_data
            slugs = [slug_from(x) for x in links.splitlines() if x.strip()]
            folder_name = re.sub(r"[^A-Za-z0-9_-]+", "_", new_name).strip("_") or "real_data"
            try:
                with st.spinner("Downloading trades from Polymarket. Big events can take a few minutes…"):
                    summary = fetch_data.fetch_to_folder(slugs, folder_name)
                st.success(summary)
                st.session_state["just_loaded"] = folder_name
                st.cache_data.clear()
                st.rerun()
            except Exception as e:   # show a friendly message instead of a crash
                st.error(f"Couldn't download that event: {e}. Check the link, your internet "
                         "connection, and that the event exists on polymarket.com.")

    st.caption(f"Longshot: ≥ ${C.LONGSHOT_MIN_USD:,} in one hour at ≤ ${C.LONGSHOT_MAX_PRICE:.2f}. "
               f"Spike: hourly change > {C.SPIKE_Z:g} SD. Thresholds live in config.py.")

r = run(str(DATA / name))
alerts, trades, markets = r["alerts"], r["trades"], r["markets"]

st.title("PolyGuard")
st.write("Flags likely insider bets on Polymarket using the three signals from "
         "the Anti-Corruption Data Collective's April 2026 report, and holds suspicious "
         "winnings until the winner verifies their identity. A flag means "
         "*needs human review*, not proof of insider trading.")

if alerts.empty:
    st.info("No longshot bets found in this dataset, so there is nothing to flag. "
            "Try an event with a surprising outcome, or add more related events.")
    st.stop()

tab_markets, tab_alerts, tab_holds, tab_replay, tab_wallets, tab_method = st.tabs(
    ["Markets", "Flagged bets", "Payout holds", "Market replay", "Wallet behaviour", "How scoring works"])

esc = alerts[alerts["status"] == "Escalate"]

# ------------------------------------------------------------------ markets
with tab_markets:
    st.subheader("Every market gets an insider-risk rating before it goes live")
    st.write("Risk depends on who decides the outcome: a small group (military, central bank) is "
             "high risk, one person's own choices are medium, the voting public is low. The system "
             "suggests a tier; an analyst approves or changes it.")
    flag_n = alerts[alerts["status"].isin(["Escalate", "Review"])].groupby("market_id").size()
    mk = markets.copy()
    mk["flagged"] = mk["market_id"].map(flag_n).fillna(0).astype(int)
    order = {"high": 0, "medium": 1, "unknown": 2, "low": 3}
    mk = mk.assign(_o=mk["risk_tier"].map(order)).sort_values(["_o", "flagged"], ascending=[True, False])
    mk["final_tier"] = mk["risk_tier"].replace({"unknown": "medium"})
    mk["approved"] = False
    mk["who"] = mk["outcome_maker"].str.title()
    m_edit = st.data_editor(
        mk[["approved", "final_tier", "risk_tier", "who", "title", "precision", "flagged"]],
        key=f"markets_{name}", hide_index=True, width="stretch", height=420,
        disabled=["risk_tier", "who", "title", "precision", "flagged"],
        column_config={
            "approved": st.column_config.CheckboxColumn("Analyst approved", width="small"),
            "final_tier": st.column_config.SelectboxColumn("Final tier", options=["high", "medium", "low"],
                                                           required=True, width="small"),
            "risk_tier": st.column_config.TextColumn("Suggested tier", width="small"),
            "who": st.column_config.TextColumn("Who decides the outcome", width="small"),
            "title": st.column_config.TextColumn("Market", width="large"),
            "precision": st.column_config.TextColumn("Day-specific?", width="small"),
            "flagged": st.column_config.NumberColumn("Flagged bets", width="small"),
        })
    k1, k2, k3 = st.columns(3)
    k1.metric("Markets", len(m_edit))
    k2.metric("High risk", int((m_edit["final_tier"] == "high").sum()))
    k3.metric("Awaiting analyst approval", int((~m_edit["approved"]).sum()))
    st.caption("Demo: the suggested tier comes from keyword rules. In production a language model "
               "would suggest it from the market question, and a person always approves it.")

# ------------------------------------------------------------------ flagged bets
with tab_alerts:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Escalated bets", len(esc))
    c2.metric("Needs review", int((alerts["status"] == "Review").sum()))
    c3.metric("Money in escalated bets", f"${esc['usd'].sum():,.0f}")
    c4.metric("Wallets escalated", esc["wallet"].nunique())

    show = st.multiselect("Show", ["Escalate", "Review", "Low", "Cleared"],
                          default=["Escalate", "Review"])
    view = alerts[alerts["status"].isin(show)].copy()
    view["wallet"] = view["wallet"].map(short)
    view["first_trade"] = view["first_trade"].dt.strftime("%b %d, %H:%M UTC")
    st.dataframe(
        view[["status", "first_trade", "title", "wallet", "outcome", "usd", "avg_price",
              "live_score", "review_score", "live_reasons", "review_reasons"]],
        hide_index=True, width="stretch", height=460,
        column_config={
            "status": "Status", "first_trade": "Placed", "title": "Market",
            "wallet": "Wallet", "outcome": "Bought",
            "usd": st.column_config.NumberColumn("Amount", format="$%,.0f"),
            "avg_price": st.column_config.NumberColumn("Avg price", format="$%.2f"),
            "live_score": st.column_config.ProgressColumn("Live score", min_value=0, max_value=100, format="%d"),
            "review_score": st.column_config.ProgressColumn("Review score", min_value=0, max_value=100, format="%d"),
            "live_reasons": st.column_config.TextColumn("Why flagged at bet time", width="large"),
            "review_reasons": st.column_config.TextColumn("After resolution", width="large"),
        })
    st.caption("Escalate = high live score, bet won, and post-resolution behaviour matches the "
               "insider pattern. Suggested action: hold the payout and verify identity.")

# ------------------------------------------------------------------ payout holds
def load_identities(folder: Path) -> dict:
    f = folder / "demo_identities.json"
    try:
        return json.loads(f.read_text()) if f.exists() else {}
    except Exception:
        return {}


def identity_for(wallet: str, ids: dict) -> dict:
    """Mock ID-vendor response. Demo only: no real people or biometric data."""
    if wallet in ids:
        return ids[wallet]
    h = int(hashlib.sha256(wallet.encode()).hexdigest(), 16)
    return {"doc": "Driver's licence", "selfie": 90 + h % 9, "liveness": "Passed",
            "screen": "No watchlist match", "conflict": ""}


REVIEW_HOURS = 72
with tab_holds:
    st.subheader("Winnings on hold until the winner verifies their identity")
    st.write("When a flagged bet wins, the payout is held instead of paid out. Compliance runs an "
             "ID and selfie check on that one winner, then releases the money or reports the case. "
             f"If nothing is found within {REVIEW_HOURS} hours, the payout is released automatically.")
    held = esc.copy()
    if held.empty:
        st.success("No payouts on hold for this dataset.")
    else:
        held["payout"] = held["shares"]          # each winning share pays $1
        cases = (held.groupby(["wallet", "event"])
                     .agg(bets=("usd", "size"), markets=("title", "nunique"), staked=("usd", "sum"),
                          payout=("payout", "sum"), score=("live_score", "max"),
                          resolved=("resolved_at", "max"),
                          reasons=("live_reasons", lambda x: "; ".join(x)),
                          reasons2=("review_reasons", lambda x: "; ".join(x)))
                     .reset_index().sort_values("payout", ascending=False).reset_index(drop=True))
        cases["case"] = [f"PG-{i + 1:03d}" for i in range(len(cases))]
        ids = load_identities(DATA / name)
        state = st.session_state.setdefault(f"decisions_{name}", {})
        st.session_state.setdefault("hold_clock", time.time())

        def decide(case_id, status):
            state[case_id] = status

        status_of = lambda c: state.get(c, "Held")
        rep = cases[cases["case"].map(status_of) == "Reported"]["payout"].sum()
        rel = cases[cases["case"].map(status_of) == "Released"]["payout"].sum()
        open_cases = cases[~cases["case"].map(status_of).isin(["Reported", "Released"])]
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Payouts on hold", f"${open_cases['payout'].sum():,.0f}")
        m2.metric("Insider money stopped", f"${rep:,.0f}", help="Payouts reported to the regulator")
        m3.metric("Honest winnings delayed", f"${rel:,.0f}", help="Held, then released after review")
        m4.metric("Open cases", len(open_cases))
        st.caption("How we measure success: insider money stopped should be high, honest winnings "
                   "delayed should be low, and every case should be decided within 72 hours.")

        elapsed_h = 2 + (time.time() - st.session_state["hold_clock"]) / 3600
        for _, c in cases.iterrows():
            cid, stt = c["case"], status_of(c["case"])
            with st.container(border=True):
                left, right = st.columns([3, 1.3], vertical_alignment="top")
                with left:
                    st.markdown(f"**{cid}** · `{short(c['wallet'])}` · {c['event']}")
                    flags = []
                    for r_ in (c["reasons"] + "; " + c["reasons2"]).split("; "):
                        if r_ and r_ not in flags and r_ != "Bet won":
                            flags.append(r_)
                    st.markdown("".join(f'<span class="pg-chip">{f}</span>' for f in flags[:7]),
                                unsafe_allow_html=True)
                    st.caption(f"{c['bets']} winning bets on {c['markets']} market(s) · "
                               f"${c['staked']:,.0f} staked · live score {c['score']}")
                with right:
                    st.metric("Payout held", f"${c['payout']:,.0f}")
                    if stt in ("Reported", "Released"):
                        colour = "#b3261e" if stt == "Reported" else "#1b6e3a"
                        label = "Reported to regulator" if stt == "Reported" else "Released to winner"
                        st.markdown(f'<span class="pg-badge" style="background:{colour};color:#fff">{label}</span>',
                                    unsafe_allow_html=True)
                    else:
                        left_h = max(0.0, REVIEW_HOURS - elapsed_h)
                        st.caption(f"⏱ {int(left_h)}h {int(left_h % 1 * 60):02d}m left to review")

                if stt in ("Held",):
                    st.button("Run ID + selfie check", key=f"id_{name}_{cid}", type="primary",
                              on_click=decide, args=(cid, "Verified"))
                if stt in ("Verified", "Reported", "Released"):
                    idn = identity_for(c["wallet"], ids)
                    v1, v2, v3, v4 = st.columns(4)
                    v1.markdown(f'ID document<br><span class="pg-ok">✔ {idn["doc"]} verified</span>', unsafe_allow_html=True)
                    v2.markdown(f'Selfie vs ID photo<br><span class="pg-ok">✔ {idn["selfie"]}% match</span>', unsafe_allow_html=True)
                    v3.markdown(f'Liveness test<br><span class="pg-ok">✔ {idn["liveness"]}</span>', unsafe_allow_html=True)
                    warn = idn["screen"] != "No watchlist match"
                    v4.markdown(f'Watchlist screen<br><span class="{"pg-warn" if warn else "pg-ok"}">'
                                f'{"⚠" if warn else "✔"} {idn["screen"]}</span>', unsafe_allow_html=True)
                    if idn.get("conflict"):
                        st.error(f"Conflict of interest: {idn['conflict']}.")
                if stt == "Verified":
                    b1, b2, _ = st.columns([1, 1, 2])
                    b1.button("Release payout", key=f"rel_{name}_{cid}",
                              on_click=decide, args=(cid, "Released"))
                    b2.button("Report to regulator", key=f"rep_{name}_{cid}", type="primary",
                              on_click=decide, args=(cid, "Reported"))
        st.caption("Demo only: identity checks are simulated (no real people or biometric data), "
                   "decisions last while the page is open, and no money moves. In production the "
                   "check comes from a specialist ID-verification vendor, which also stores the data.")

# ------------------------------------------------------------------ market replay
with tab_replay:
    events = markets.sort_values("resolved_at")["event"].unique().tolist()
    # open on the event behind the biggest single held case (same order as the hold queue)
    top_event = esc.groupby(["wallet", "event"])["shares"].sum().idxmax()[1] if len(esc) else None
    default = events.index(top_event) if top_event in events else 0
    event = st.selectbox("Event", events, index=default)
    ev_markets = markets[markets["event"] == event].sort_values("scheduled_end")
    ev_titles = ev_markets["title"].tolist()
    top_m = esc[esc["event"] == event].groupby("title")["shares"].sum()  # market with the most held money
    title = st.selectbox("Market", ev_titles,
                         index=ev_titles.index(top_m.idxmax()) if len(top_m) else max(0, len(ev_titles) - 3))
    mrow = ev_markets[ev_markets["title"] == title].iloc[0]

    buys = trades[(trades["market_id"] == mrow["market_id"]) & (trades["side"] == "BUY")].copy()
    buys["hour"] = buys["timestamp"].dt.floor("h")
    ls = r["longshots"][["wallet", "market_id", "outcome", "hour"]].assign(is_ls=True)
    buys = buys.merge(ls, on=["wallet", "market_id", "outcome", "hour"], how="left")
    held_wallets = set(esc["wallet"])
    buys["type"] = buys["outcome"]
    ls_mask = buys["is_ls"].fillna(False).astype(bool)
    buys.loc[ls_mask, "type"] = "Other longshot bet"
    buys.loc[ls_mask & buys["wallet"].isin(held_wallets), "type"] = "Held wallet's bet"
    buys["wallet_short"] = buys["wallet"].map(short)

    rank = {"No": 0, "Yes": 1, "Other longshot bet": 2, "Held wallet's bet": 3}
    fig = px.scatter(buys.sort_values("type", key=lambda s: s.map(rank)),
                     x="timestamp", y="price", size="usd", color="type", size_max=22,
                     color_discrete_map={"Yes": "#6f9cc8", "No": "#c3cbd3",
                                         "Other longshot bet": "#f0b27a", "Held wallet's bet": "#8c1d18"},
                     hover_data={"wallet_short": True, "usd": ":$,.0f", "price": ":.2f",
                                 "timestamp": "|%b %d %H:%M"},
                     labels={"timestamp": "", "price": "Price paid (= implied probability)"},
                     title=f"Every buy in “{title}”")
    fig.add_vline(x=mrow["resolved_at"], line_dash="dot", line_color="#b3261e")
    fig.add_annotation(x=mrow["resolved_at"], y=1.02, yref="paper", showarrow=False,
                       text=f"Resolved {mrow['winning_outcome']}", font=dict(color="#b3261e"))
    fig.update_yaxes(range=[0, 1.05], tickformat=".0%")
    st.plotly_chart(style(fig), width="stretch")

    sp = r["spikes"][r["spikes"]["event"] == event].merge(markets[["market_id", "title"]], on="market_id")
    if len(sp):
        sp["Flag"] = sp["spike"].map({True: "Spike (> 2 SD)", False: "Normal"})
        n = sp["title"].nunique()
        fig2 = px.scatter(sp, x="hour", y="change", color="Flag", facet_row="title",
                          color_discrete_map={"Spike (> 2 SD)": "#b3261e", "Normal": "#6f9cc8"},
                          labels={"hour": "", "change": "Hourly change"},
                          title="Hourly change in YES price across every market in this event")
        fig2.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1], textangle=0,
                                                    x=0.01, xanchor="left", yanchor="bottom"))
        fig2.update_traces(marker=dict(size=7))
        fig2.update_yaxes(title_text="", matches=None)
        st.plotly_chart(style(fig2, height=170 * n + 60), width="stretch")
        st.caption("Spikes that hit several related markets in the same hour suggest someone "
                   "racing to buy on time-sensitive information.")

# ------------------------------------------------------------------ wallets
with tab_wallets:
    options = ["All events"] + markets["event"].unique().tolist()
    pick = st.selectbox("Scope", options,
                        index=options.index(event) if event in options else 0)
    if pick == "All events":
        wp = r["wallets"]
    else:
        t_ev = trades[trades["event"] == pick]
        wp = wallet_profiles(t_ev, r["longshots"][r["longshots"]["event"] == pick])
    wp = wp[wp["usd_bought"] > 0].copy()
    wp["wallet_short"] = wp["wallet"].map(short)

    fig3 = px.scatter(wp.sort_values("group", key=lambda s: s.str.startswith("Insider")),
                      x="exit_rate", y="win_rate", size="usd_bought", color="group",
                      color_discrete_map=GROUP_COLORS, size_max=30, opacity=0.85,
                      hover_data={"wallet_short": True, "usd_bought": ":$,.0f",
                                  "win_rate": ":.0%", "exit_rate": ":.0%"},
                      labels={"exit_rate": "Exit rate (shares sold before close ÷ shares bought)",
                              "win_rate": "Win rate on buys"},
                      title="Win rate vs exit rate, one dot per wallet")
    fig3.add_hline(y=C.INSIDER_MIN_WIN_RATE, line_dash="dash", line_color="#7b8794")
    fig3.add_vline(x=C.INSIDER_MAX_EXIT_RATE, line_dash="dash", line_color="#7b8794")
    fig3.update_xaxes(tickformat=".0%", range=[-0.03, 1.03])
    fig3.update_yaxes(tickformat=".0%", range=[-0.03, 1.05])
    st.plotly_chart(style(fig3, height=520), width="stretch")
    st.caption("Top left: wallets that almost always win and hold to settlement, the report's "
               "insider pattern. Top right: skilled traders who win but take profit early.")

    ins = wp[wp["group"].str.startswith("Insider")].sort_values("usd_bought", ascending=False)
    st.subheader(f"{len(ins)} wallets match the insider pattern")
    st.dataframe(ins[["wallet_short", "win_rate", "exit_rate", "usd_bought", "longshots",
                      "longshot_wins", "first_seen"]],
                 hide_index=True, width="stretch",
                 column_config={"wallet_short": "Wallet",
                                "win_rate": st.column_config.NumberColumn("Win rate", format="percent"),
                                "exit_rate": st.column_config.NumberColumn("Exit rate", format="percent"),
                                "usd_bought": st.column_config.NumberColumn("Bought", format="$%,.0f"),
                                "longshots": "Longshots", "longshot_wins": "Longshot wins",
                                "first_seen": "First seen"})

# ------------------------------------------------------------------ method
with tab_method:
    st.markdown(f"""
**Step 1: rate the market.** Who decides the outcome? Institutions (military, central bank,
executive) are high risk, one person's own choices are medium, the voting public is low.
Day-specific markets add risk because they are cheap to bet on and pay out more.

**Step 2: find longshot bets.** One wallet buying at least ${C.LONGSHOT_MIN_USD:,} of an outcome
within one hour at an average price of ${C.LONGSHOT_MAX_PRICE:.2f} or less.

**Live score (0–100), knowable when the bet is placed:** market risk tier (up to 25),
day-specific market (10), bet size (up to 15), how cheap the price is (up to 10), a price spike
around the bet (10, plus 5 if related markets spiked in the same hour), the wallet's past
longshot record (20), an account under 14 days old (5), and a wallet that has bet almost only on
this one event (10).

**Review score (0–100), after the market resolves:** placed within 12 hours of resolution (30)
or 24 hours (20), the market resolved early within 7 days of the bet (25), the wallet held the position
to settlement instead of taking profit (25), and the wallet's overall longshot win rate is 80% or
more (20). Lost bets are cleared.

**Status:** *Escalate* when the live score is {C.LIVE_HIGH}+, the bet won, and the review score
is {C.REVIEW_ESCALATE}+. The payout is held, the winner completes an ID and selfie check, and
compliance releases or reports the case within 72 hours (ACDC recommendation 2).

**Roadmap.** Transparent points first, because there are very few confirmed insider cases to learn
from. As reviewers release or report cases, those decisions become labels for anomaly detection
and, later, a machine-learning model.

**Limits.** Luck, skill and mispricing also produce winning longshots, so every flag needs human
review. One person can run many wallets. The tool should stay internal to the platform,
because public insider alerts let copy-traders profit from the insiders.
""")
