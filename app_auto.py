"""
app_auto.py — Auto-loading version of the dashboard.
Loads pipeline.xlsx directly from the data/ folder — no upload needed.
"""

import os, sys, json
from datetime import datetime

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from cleaner import clean_pipeline, merge_new_batch
from prioritiser import prioritise, shop_visit_groups
from messenger import draft_message

st.set_page_config(page_title="Fleek — GTM Pipeline", page_icon="🧥", layout="wide")

st.markdown("""
<style>
* { box-sizing: border-box; }
.metric-card { background: #1a1a1a; border: 1px solid #333; border-radius: 8px; padding: 16px; text-align: center; }
.metric-big { font-size: 2rem; font-weight: 700; color: #4ade80; }
.metric-label { font-size: 0.7rem; color: #888; text-transform: uppercase; letter-spacing: 0.08em; margin-top: 4px; }
.stage-chip { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.7rem; font-weight: 600; text-transform: uppercase; }
.msg-box { background: #111; border-left: 3px solid #4ade80; border-radius: 0 6px 6px 0; padding: 12px 16px; font-size: 0.85rem; line-height: 1.6; color: #ccc; white-space: pre-wrap; margin-top: 8px; }
</style>
""", unsafe_allow_html=True)

STAGE_COLORS = {
    "negotiating": "#22c55e", "warm": "#86efac", "call_booked": "#60a5fa",
    "replied": "#a78bfa", "contacted": "#fbbf24", "ghosted": "#f87171",
    "new": "#6b7280", "lost": "#374151", "won": "#10b981",
}

def stage_chip(stage):
    color = STAGE_COLORS.get(stage, "#555")
    return f'<span class="stage-chip" style="background:{color}20;color:{color}">{stage}</span>'

# ── Auto-load data ─────────────────────────────────────────────────────────

DATA_PATH = os.path.join(os.path.expanduser("~"), "Downloads", "fleek-gtm-tool", "data", "pipeline.xlsx")

@st.cache_data(show_spinner=False)
def load_data(include_day2=False):
    raw = pd.read_excel(DATA_PATH, sheet_name="pipeline", dtype=str)
    if include_day2:
        new_raw = pd.read_excel(DATA_PATH, sheet_name="new_drop_day2", dtype=str)
        df = merge_new_batch(raw, new_raw)
        df["_is_new"] = df.get("_is_new", False)
    else:
        df = clean_pipeline(raw)
        df["_is_new"] = False
    return df

@st.cache_data(show_spinner=False)
def run_prioritiser(df_json):
    df = pd.read_json(df_json, orient="records")
    return prioritise(df)

# ── Sidebar ────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🧥 Fleek GTM")
    st.markdown("**Acquisition Pipeline**")
    st.divider()
    include_day2 = st.toggle("Include Day 2 batch", value=False,
        help="Merges new_drop_day2 sheet — skips duplicates automatically")
    st.divider()
    st.markdown("#### Filters")
    stage_filter = st.multiselect("Stage",
        ["new","contacted","replied","warm","call_booked","negotiating","ghosted","lost","won"],
        default=["new","contacted","replied","warm","call_booked","negotiating","ghosted"])

# ── Load ───────────────────────────────────────────────────────────────────

with st.spinner("Loading pipeline..."):
    df_clean = load_data(include_day2)
    prioritised = run_prioritiser(df_clean.to_json(orient="records", date_format="iso"))

mask = prioritised["stage"].isin(stage_filter)
filtered = prioritised[mask].copy()

resellers = prioritised["lead_type"] == "reseller"
shops = prioritised["lead_type"] == "shop"
new_leads = int(df_clean["_is_new"].sum()) if "_is_new" in df_clean.columns else 0
dm_queue = prioritised[resellers & (prioritised.get("in_todays_queue", pd.Series(False)) == True)]

# ── Header ─────────────────────────────────────────────────────────────────

st.markdown(f"# 🧥 Fleek GTM — Daily Pipeline")
st.markdown(f"**{datetime.today().strftime('%A %d %B %Y')}** · {len(df_clean)} leads loaded")

if include_day2 and new_leads > 0:
    st.success(f"✨ {new_leads} new leads merged from Day 2 batch — {28 - new_leads} duplicates skipped automatically.")

# ── KPIs ───────────────────────────────────────────────────────────────────

c1,c2,c3,c4,c5 = st.columns(5)
for col, (val, label) in zip([c1,c2,c3,c4,c5], [
    (str(len(df_clean)), "Total leads"),
    (str(int(resellers.sum())), "Resellers"),
    (str(int(shops.sum())), "Shops"),
    (f"{len(dm_queue)}/40", "DMs queued today"),
    (str(int((prioritised['stage']=='negotiating').sum())), "Negotiating"),
]):
    with col:
        st.markdown(f'<div class="metric-card"><div class="metric-big">{val}</div><div class="metric-label">{label}</div></div>', unsafe_allow_html=True)

st.markdown("")

# ── Tabs ───────────────────────────────────────────────────────────────────

tab_dm, tab_shop, tab_all, tab_visits = st.tabs(["📱 DM Queue (40/day)", "📧 Shop Outreach", "📋 All Leads", "🗺️ Visit Planner"])

with tab_dm:
    st.markdown("### Today's Instagram DM Queue")
    st.markdown("Scored by: **spend (40%)** → **stage proximity (25%)** → **days stale (20%)** → **positive signal (10%)** → **followers (5%)**")
    dm_df = prioritised[resellers].sort_values("priority_score", ascending=False)
    todays = dm_df[dm_df.get("in_todays_queue", pd.Series(False)) == True]
    for i, (_, row) in enumerate(todays.iterrows(), 1):
        handle = row.get("handle_clean") or "—"
        stage = row.get("stage","new")
        score = row.get("priority_score", 0)
        action = row.get("next_action","—")
        spend = row.get("spend_gbp") or 0
        vel = row.get("sales_velocity_30d") or 0
        msg = draft_message(row.to_dict(), action, use_api=False)
        dot = "🟢" if score >= 70 else "🟡" if score >= 50 else "⚪"
        with st.expander(f"{dot} #{i}  @{handle}   score={score:.0f}   {action}"):
            c1, c2 = st.columns([1,2])
            with c1:
                st.markdown(f"**Stage:** {stage_chip(stage)}", unsafe_allow_html=True)
                st.markdown(f"**Score:** {score}")
                st.markdown(f"**Est. spend:** £{spend:,.0f}/mo")
                st.markdown(f"**Sold/30d:** {vel}")
            with c2:
                st.markdown("**Drafted DM:**")
                st.markdown(f'<div class="msg-box">{msg}</div>', unsafe_allow_html=True)

with tab_shop:
    st.markdown("### Shop Outreach — email → call → visit")
    shop_df = prioritised[shops & (prioritised["next_action"] != "no_action")].sort_values("priority_score", ascending=False)
    for i, (_, row) in enumerate(shop_df.iterrows(), 1):
        name = row.get("store_name") or "—"
        city = row.get("city") or "—"
        stage = row.get("stage","new")
        action = row.get("next_action","—")
        score = row.get("priority_score", 0)
        spend = row.get("spend_gbp") or 0
        msg = draft_message(row.to_dict(), action, use_api=False)
        icon = "📧" if "email" in action else "📞" if "call" in action else "🚶"
        dot = "🟢" if score >= 70 else "🟡" if score >= 50 else "⚪"
        with st.expander(f"{dot} #{i}  {name} ({city})  {icon} {action}"):
            c1, c2 = st.columns([1,2])
            with c1:
                st.markdown(f"**Stage:** {stage_chip(stage)}", unsafe_allow_html=True)
                st.markdown(f"**Est. spend:** £{spend:,.0f}/mo")
                email = row.get("email_clean") or "—"
                phone = row.get("phone_clean") or "—"
                st.markdown(f"**Email:** {email}")
                st.markdown(f"**Phone:** {phone}")
            with c2:
                st.markdown("**Drafted message / script:**")
                st.markdown(f'<div class="msg-box">{msg}</div>', unsafe_allow_html=True)

with tab_all:
    st.markdown("### Full Pipeline")
    cols = ["lead_id","lead_type","handle_clean","store_name","city","stage","spend_gbp","priority_score","next_action","last_touch_date","num_touches"]
    show = filtered[[c for c in cols if c in filtered.columns]].fillna("—")
    st.dataframe(show, use_container_width=True, height=500)
    st.caption(f"{len(show)} leads shown")
    st.download_button("⬇️ Download as CSV", filtered.to_csv(index=False),
        file_name=f"fleek_pipeline_{datetime.today().strftime('%Y%m%d')}.csv", mime="text/csv")

with tab_visits:
    st.markdown("### Shop Visit Planner — grouped by city")
    shop_data = prioritised[shops & prioritised["city"].notna()].copy()
    groups = shop_visit_groups(shop_data)
    if not groups:
        st.info("No shops with city data.")
    else:
        for city, leads in groups.items():
            with st.expander(f"📍 {city} — {len(leads)} shops"):
                for lead in leads:
                    name = lead.get("store_name") or "—"
                    stage = lead.get("stage","new")
                    spend = lead.get("spend_gbp") or 0
                    phone = lead.get("phone_clean") or "—"
                    email = lead.get("email_clean") or "—"
                    action = lead.get("next_action","—")
                    st.markdown(f"**{name}** · {stage_chip(stage)} · £{spend:,.0f}/mo  \n📞 `{phone}` · 📧 `{email}` · _{action}_", unsafe_allow_html=True)
                    st.divider()
