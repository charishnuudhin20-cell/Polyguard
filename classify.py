"""Classify markets by who decides the outcome (ACDC's "outcome maker") and by precision.

group      -> institutions (military, central bank, executive, courts)  -> HIGH insider risk
individual -> one person's own choices (what a politician says or wears) -> MEDIUM
public     -> large populations (elections, approval ratings)           -> LOW

Keyword matching is a simple starting point. Upgrade idea: send each market title
to an LLM and ask it to return one of the three labels.
"""
import re

import pandas as pd

INDIVIDUAL = [r"\bsays?\b", r"\bsaid\b", r"\btweets?\b", r"\bposts?\b", r"\bmentions?\b",
              r"\bwears?\b", r"\battends?\b", r"\bspeech\b", r"\bpress (briefing|conference)\b"]
PUBLIC = [r"\belection\b", r"\bwins? the\b", r"\bprimary\b", r"\breferendum\b",
          r"\bapproval rating\b", r"\bpopular vote\b", r"\bgovernor race\b", r"\bmayoral\b",
          r"\bpolls?\b"]
GROUP = [r"\bstrikes?\b", r"\bmilitary\b", r"\battacks?\b", r"\binvad", r"\btroops\b",
         r"\bceasefire\b", r"\bwar\b", r"\bmissiles?\b", r"\bblockade\b", r"\bsanctions?\b",
         r"\btariffs?\b", r"\bfed\b", r"\bfomc\b", r"\brate (cut|hike)s?\b", r"\binterest rates?\b",
         r"\bcentral bank\b", r"\bcourt\b", r"\bruling\b", r"\bnominat", r"\bappoint",
         r"\bconfirm", r"\bexecutive order\b", r"\bpardons?\b", r"\bindict", r"\btreaty\b",
         r"\bnato\b", r"\boperation\b"]

MONTHS = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
DATE_PATTERN = re.compile(rf"\b{MONTHS}\s+\d{{1,2}}\b|\b\d{{1,2}}\s+{MONTHS}\b|\b(today|tonight|tomorrow)\b", re.I)

RISK_TIER = {"group": "high", "individual": "medium", "public": "low", "other": "unknown"}


def _matches(title: str, patterns) -> bool:
    return any(re.search(p, title, re.I) for p in patterns)


def outcome_maker(title: str) -> str:
    title = title or ""
    # Order matters: "Will X say 'war'?" is a speech market, not a military one.
    if _matches(title, INDIVIDUAL):
        return "individual"
    if _matches(title, PUBLIC):
        return "public"
    if _matches(title, GROUP):
        return "group"
    return "other"


def precision(title: str) -> str:
    """'high' if the market asks about one specific day, which the report shows is
    cheaper to bet on and more profitable for someone with inside knowledge."""
    return "high" if DATE_PATTERN.search(title or "") else "low"


def classify_markets(markets: pd.DataFrame) -> pd.DataFrame:
    m = markets.copy()
    m["outcome_maker"] = m["title"].map(outcome_maker)
    m["risk_tier"] = m["outcome_maker"].map(RISK_TIER)
    m["precision"] = m["title"].map(precision)
    return m
