"""
prioritiser.py — Score and rank leads for daily action.

Resellers  → scored for Instagram DM priority (40/day cap)
Shops      → scored for outreach sequence (email → call → visit)
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

TODAY = pd.Timestamp("today").normalize()
DM_DAILY_CAP = 40

# ── Stage ordering (higher = closer to close) ─────────────────────────────

STAGE_ORDER = {
    "won": 10,
    "negotiating": 9,
    "warm": 8,
    "call_booked": 7,
    "replied": 6,
    "contacted": 4,
    "ghosted": 3,
    "new": 2,
    "lost": 0,
}

# Stages where we should NOT reach out (closed or recently rejected)
SKIP_STAGES = {"won", "lost"}

# ── Reseller scoring ───────────────────────────────────────────────────────

def score_reseller(row: pd.Series) -> float:
    """
    Returns a priority score 0–100 for a reseller lead.
    Higher = message today.

    Factors:
    - spend_gbp:           40 pts  (commercial value)
    - stage_proximity:     25 pts  (warm/replied > new > ghosted)
    - days_since_touch:    20 pts  (stale > touched today; sweet spot 3–14 days)
    - engagement_signal:   10 pts  (last_inbound_text shows positive intent)
    - followers:            5 pts  (tie-breaker: audience size)
    """
    score = 0.0

    # 1. Spend (40 pts) — normalised vs £9,000 cap
    spend = row.get("spend_gbp") or 0
    score += min(spend / 9000, 1.0) * 40

    # 2. Stage proximity (25 pts)
    stage_val = STAGE_ORDER.get(row.get("stage", "new"), 2)
    score += (stage_val / 10) * 25

    # 3. Days since last touch (20 pts)
    last_touch = row.get("last_touch_date")
    if pd.notna(last_touch):
        days_ago = (TODAY - last_touch).days
        # Sweet spot: 3–14 days since last touch
        if 3 <= days_ago <= 14:
            score += 20
        elif days_ago > 14:
            score += 15   # stale – needs nudge
        elif days_ago < 3:
            score += 5    # very recent – don't spam
    else:
        score += 10  # no touch recorded – unknown, moderate priority

    # 4. Engagement signal (10 pts)
    text = str(row.get("last_inbound_text") or "").lower()
    positive_words = ["yes", "interested", "send", "tell me", "happy", "sure", "ok", "great", "when", "how"]
    if any(w in text for w in positive_words):
        score += 10
    elif text and len(text) > 3:
        score += 4  # any reply is better than nothing

    # 5. Followers tie-breaker (5 pts)
    followers = row.get("followers") or 0
    score += min(followers / 50000, 1.0) * 5

    return round(score, 2)


# ── Shop scoring ───────────────────────────────────────────────────────────

def score_shop(row: pd.Series) -> float:
    """
    Returns a priority score 0–100 for a physical shop lead.
    Higher = contact sooner.

    Factors:
    - spend_gbp:           40 pts
    - stage_proximity:     25 pts
    - days_since_touch:    20 pts
    - engagement_signal:   15 pts
    """
    score = 0.0

    spend = row.get("spend_gbp") or 0
    score += min(spend / 9000, 1.0) * 40

    stage_val = STAGE_ORDER.get(row.get("stage", "new"), 2)
    score += (stage_val / 10) * 25

    last_touch = row.get("last_touch_date")
    if pd.notna(last_touch):
        days_ago = (TODAY - last_touch).days
        if 3 <= days_ago <= 21:
            score += 20
        elif days_ago > 21:
            score += 18
        else:
            score += 5
    else:
        score += 10

    text = str(row.get("last_inbound_text") or "").lower()
    positive_words = ["yes", "interested", "send", "happy", "sure", "ok", "great", "when", "how", "morning"]
    if any(w in text for w in positive_words):
        score += 15
    elif text and len(text) > 3:
        score += 5

    return round(score, 2)


# ── Next action logic ─────────────────────────────────────────────────────

def next_action_reseller(row: pd.Series) -> str:
    stage = row.get("stage", "new")
    text = str(row.get("last_inbound_text") or "").lower()
    num_touches = row.get("num_touches") or 0

    if stage in SKIP_STAGES:
        return "no_action"
    if stage == "won":
        return "no_action"
    if stage == "negotiating":
        return "dm_follow_up_negotiation"
    if stage in ("warm", "replied"):
        return "dm_follow_up_warm"
    if stage == "call_booked":
        return "dm_confirm_call"
    if stage == "ghosted":
        return "dm_re_engage" if num_touches < 5 else "no_action"
    if stage == "contacted":
        return "dm_follow_up"
    # new lead
    return "dm_first_outreach"


def next_action_shop(row: pd.Series) -> str:
    stage = row.get("stage", "new")
    num_touches = row.get("num_touches") or 0
    has_email = pd.notna(row.get("email_clean"))
    has_phone = pd.notna(row.get("phone_clean"))

    if stage in SKIP_STAGES:
        return "no_action"
    if stage == "negotiating":
        return "call_close"
    if stage in ("warm", "replied"):
        return "call_or_visit"
    if stage == "call_booked":
        return "prepare_for_call"
    if stage == "ghosted":
        if num_touches < 3:
            return "email_re_engage"
        return "no_action"
    if stage == "contacted":
        return "call_follow_up" if has_phone else "email_follow_up"
    # new
    if has_email:
        return "email_first_outreach"
    return "call_first_outreach"


# ── Main prioritise function ──────────────────────────────────────────────

def prioritise(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    resellers = df[df["lead_type"] == "reseller"].copy()
    shops = df[df["lead_type"] == "shop"].copy()

    # Score
    resellers["priority_score"] = resellers.apply(score_reseller, axis=1)
    shops["priority_score"] = shops.apply(score_shop, axis=1)

    # Next action
    resellers["next_action"] = resellers.apply(next_action_reseller, axis=1)
    shops["next_action"] = shops.apply(next_action_shop, axis=1)

    # Filter out no-action, sort by score
    active_resellers = (
        resellers[resellers["next_action"] != "no_action"]
        .sort_values("priority_score", ascending=False)
        .reset_index(drop=True)
    )
    active_shops = (
        shops[shops["next_action"] != "no_action"]
        .sort_values("priority_score", ascending=False)
        .reset_index(drop=True)
    )

    # Mark today's DM queue (top 40 resellers)
    active_resellers["in_todays_queue"] = False
    active_resellers.loc[:DM_DAILY_CAP - 1, "in_todays_queue"] = True

    # Combine back
    combined = pd.concat([active_resellers, active_shops], ignore_index=True)
    return combined


def shop_visit_groups(shops_df: pd.DataFrame) -> dict:
    """Group shops by city for visit planning."""
    groups = {}
    for city, grp in shops_df.groupby("city"):
        if pd.notna(city) and city:
            groups[str(city)] = grp.sort_values("priority_score", ascending=False).to_dict("records")
    return groups
