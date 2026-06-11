"""
app.py — Fleek GTM Acquisition Dashboard (Streamlit)

Run with: streamlit run app.py
"""

import json
import os
import sys
from datetime import datetime

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from cleaner import clean_pipeline, merge_new_batch
from prioritiser import prioritise, shop_visit_groups
from messenger import draft_message

# ── Page config ───────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Fleek — GTM Pipeline",
    page_icon="🧥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────

st.markdown("""
<style>
    /* Inter-like clean sans-serif */
    html, body, [class*="css"] { font-family: 'Inter', 'Helvetica Neue', sans-serif; }
    
    /* Metric cards */
    .metric-card {
        background: #0f0f0f;
        border: 1px solid #222;
        border-radius: 8px;
        padding: 16px 20px;
        text-align: center;
    }
    .metric-big { font-size: 2.4rem; font-weight: 700; color: #e8ff47; }
    .metric-label { font-size: 0.75rem; color: #888; text-transform: uppercase; letter-spacing: 0.08em; }
    
    /* DM queue badge */
    .queue-badge {
        background: #e8ff47;
        color: #0f0f0f;
        font-size: 0.7rem;
        font-weight: 700;
        padding: 2px 8px;
        border-radius: 20px;
        text-transform: uppercase;
    }
    
    /* Priority dots */
    .dot-high { color: #e8ff47; font-size: 1.2em; }
    .dot-med  { color: #888;    font-size: 1.2em; }
    .dot-low  { color: #444;    font-size: 1.2em; }

    /* Stage chip */
    .stage-chip {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.72rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }
    
    /* Sidebar */
    section[data-testid="stSidebar"] { background: #0a0a0a; }
    
    /* Message box */
    .msg-box {
        background: #111;
        border-left: 3px solid #e8ff47;
        border-radius: 0 6px 6px 0;
        padding: 12px 16px;
        font-size: 0.88rem;
        line-height: 1.55;
        color: #ccc;
        white-space: pre-wrap;
    }
</style>
""", unsafe_allow_html=True)

STAGE_COLORS = {
    "negotiating": "#22c55e",
    "warm": "#86efac",
    "call_booked": "#60a5fa",
    "replied": "#a78bfa",
    "contacted": "#fbbf24",
    "ghosted": "#f87171",
    "new": "#6b7280",
    "lost": "#374151",
    "won": "#10b981",
}


def stage_chip(stage: str) -> str:
    color = STAGE_COLORS.get(stage, "#555")
    return f'<span class="stage-chip" style="background:{color}20;color:{color}">{stage}</span>'


# ── Data loading (cached) ─────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def load_and_clean(file_bytes, new_bytes=None):
    raw = pd.read_excel(file_bytes, sheet_name="pipeline", dtype=str)
    if new_bytes is not None:
        new_raw = pd.read_excel(new_bytes, sheet_name="new_drop_day2", dtype=str)
        df = merge_new_batch(raw, new_raw)
        is_new_col = df.pop("_is_new") if "_is_new" in df.columns else pd.Series([False] * len(df))
        df["_is_new"] = is_new_col
    else:
        df = clean_pipeline(raw)
        df["_is_new"] = False
    return df


@st.cache_data(show_spinner=False)
def run_prioritiser(df_json):
    df = pd.read_json(df_json, orient="records")
    return prioritise(df)


# ── Sidebar ───────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🧥 Fleek GTM")
    st.markdown("**Acquisition Pipeline**")
    st.divider()

    main_file = st.file_uploader("Main pipeline (.xlsx)", type=["xlsx"], key="main")
    new_file = st.file_uploader("New batch — Day 2+ (.xlsx)", type=["xlsx"], key="new")

    if main_file is None:
        st.info("Upload your pipeline Excel to get started.")
        st.stop()

    use_ai = st.toggle("AI message drafting", value=False,
                       help="Calls Anthropic API to write personalised messages. Turn off for speed.")

    st.divider()
    st.markdown("#### Filters")
    lead_type_filter = st.multiselect(
        "Lead type", ["reseller", "shop"], default=["reseller", "shop"]
    )
    stage_filter = st.multiselect(
        "Stage", ["new", "contacted", "replied", "warm", "call_booked", "negotiating", "ghosted", "lost", "won"],
        default=["new", "contacted", "replied", "warm", "call_booked", "negotiating", "ghosted"]
    )

# ── Load data ─────────────────────────────────────────────────────────────

with st.spinner("Cleaning pipeline..."):
    try:
        df_clean = load_and_clean(
            main_file,
            new_file if new_file else None
        )
    except Exception as e:
        st.error(f"Error loading data: {e}")
        st.stop()

prioritised = run_prioritiser(df_clean.to_json(orient="records", date_format="iso"))

# Apply filters
mask = (
    prioritised["lead_type"].isin(lead_type_filter) &
    prioritised["stage"].isin(stage_filter)
)
filtered = prioritised[mask].copy()

# ── Header ────────────────────────────────────────────────────────────────

st.markdown(f"# Fleek GTM — Daily Pipeline")
st.markdown(f"**{datetime.today().strftime('%A %d %B %Y')}**  ·  {len(df_clean)} leads loaded")

# ── KPI row ───────────────────────────────────────────────────────────────

new_leads = int(df_clean["_is_new"].sum()) if "_is_new" in df_clean.columns else 0
resellers = (prioritised["lead_type"] == "reseller")
shops = (prioritised["lead_type"] == "shop")
dm_queue = prioritised[resellers & prioritised.get("in_todays_queue", pd.Series(False))]
active_shops = prioritised[shops & (prioritised["next_action"] != "no_action")]
negotiating = (prioritised["stage"] == "negotiating").sum()

c1, c2, c3, c4, c5 = st.columns(5)
kpis = [
    (str(len(df_clean)), "Total leads"),
    (str(int(resellers.sum())), "Resellers"),
    (str(int(shops.sum())), "Shops"),
    (f"{len(dm_queue)}/40", "DMs queued today"),
    (str(negotiating), "In negotiation"),
]
for col, (val, label) in zip([c1, c2, c3, c4, c5], kpis):
    with col:
        st.markdown(f"""
        <div class="metric-card">
          <div class="metric-big">{val}</div>
          <div class="metric-label">{label}</div>
        </div>""", unsafe_allow_html=True)

if new_leads > 0:
    st.success(f"✨ {new_leads} new leads merged from Day 2 batch — duplicates skipped automatically.")

st.markdown("")

# ── Tabs ──────────────────────────────────────────────────────────────────

tab_dm, tab_shop, tab_all, tab_visits = st.tabs([
    "📱 DM Queue (40/day)", "📧 Shop Outreach", "📋 All Leads", "🗺️ Visit Planner"
])

# ─── DM Queue tab ────────────────────────────────────────────────────────

with tab_dm:
    st.markdown("### Today's Instagram DM Queue")
    st.markdown("Top 40 resellers scored by **commercial value → stage proximity → days stale → positive signals**.")

    dm_df = prioritised[resellers].sort_values("priority_score", ascending=False)
    dm_queue_df = dm_df[dm_df.get("in_todays_queue", pd.Series(False)) == True].copy()

    if len(dm_queue_df) == 0:
        st.info("No DMs queued. Check your filters.")
    else:
        for i, (_, row) in enumerate(dm_queue_df.iterrows(), 1):
            handle = row.get("handle_clean") or "—"
            stage = row.get("stage", "new")
            score = row.get("priority_score", 0)
            action = row.get("next_action", "—")
            followers = row.get("followers") or 0
            velocity = row.get("sales_velocity_30d") or 0
            spend = row.get("spend_gbp") or 0
            last_text = row.get("last_inbound_text") or ""

            dot = "🟡" if score >= 70 else "🟠" if score >= 50 else "⚪"

            with st.expander(f"{dot} #{i}  @{handle}   score={score:.0f}   {action}"):
                col1, col2 = st.columns([2, 3])
                with col1:
                    st.markdown(f"**Stage:** {stage_chip(stage)}", unsafe_allow_html=True)
                    st.markdown(f"**Followers:** {followers:,}")
                    st.markdown(f"**Items sold / 30d:** {velocity}")
                    st.markdown(f"**Est. spend:** £{spend:,.0f}/mo")
                    if last_text:
                        st.markdown(f"**Last reply:** _{last_text}_")
                with col2:
                    st.markdown("**Drafted message:**")
                    # Use cached or generate on demand
                    msg_key = f"msg_{handle}_{action}"
                    if msg_key not in st.session_state:
                        if use_ai:
                            with st.spinner("Drafting with AI..."):
                                st.session_state[msg_key] = draft_message(row.to_dict(), action, use_api=True)
                        else:
                            st.session_state[msg_key] = draft_message(row.to_dict(), action, use_api=False)
                    msg = st.session_state[msg_key]
                    st.markdown(f'<div class="msg-box">{msg}</div>', unsafe_allow_html=True)
                    st.text_area("Edit before sending:", value=msg, key=f"edit_{handle}_{i}", height=100)

# ─── Shop Outreach tab ───────────────────────────────────────────────────

with tab_shop:
    st.markdown("### Shop Outreach Queue")
    st.markdown("Sequenced by **email → call → visit** based on stage and contacts available.")

    shop_df = prioritised[shops & (prioritised["next_action"] != "no_action")].sort_values(
        "priority_score", ascending=False
    )

    if len(shop_df) == 0:
        st.info("No shops to action. Check your filters.")
    else:
        for i, (_, row) in enumerate(shop_df.iterrows(), 1):
            name = row.get("store_name") or "—"
            city = row.get("city") or "—"
            stage = row.get("stage", "new")
            action = row.get("next_action", "—")
            score = row.get("priority_score", 0)
            email = row.get("email_clean") or ""
            phone = row.get("phone_clean") or ""
            spend = row.get("spend_gbp") or 0

            # Action icon
            icon = "📧" if "email" in action else "📞" if "call" in action else "🚶"
            dot = "🟡" if score >= 70 else "🟠" if score >= 50 else "⚪"

            with st.expander(f"{dot} #{i}  {name}  ({city})  {icon} {action}"):
                col1, col2 = st.columns([2, 3])
                with col1:
                    st.markdown(f"**Stage:** {stage_chip(stage)}", unsafe_allow_html=True)
                    if email:
                        st.markdown(f"**Email:** `{email}`")
                    if phone:
                        st.markdown(f"**Phone:** `{phone}`")
                    st.markdown(f"**Est. spend:** £{spend:,.0f}/mo")
                    last_text = row.get("last_inbound_text") or ""
                    if last_text:
                        st.markdown(f"**Last reply:** _{last_text}_")
                with col2:
                    st.markdown("**Drafted message / script:**")
                    msg_key = f"msg_{name}_{action}"
                    if msg_key not in st.session_state:
                        if use_ai:
                            with st.spinner("Drafting with AI..."):
                                st.session_state[msg_key] = draft_message(row.to_dict(), action, use_api=True)
                        else:
                            st.session_state[msg_key] = draft_message(row.to_dict(), action, use_api=False)
                    msg = st.session_state[msg_key]
                    st.markdown(f'<div class="msg-box">{msg}</div>', unsafe_allow_html=True)

# ─── All Leads tab ────────────────────────────────────────────────────────

with tab_all:
    st.markdown("### Full Pipeline")

    display_cols = [
        "lead_id", "lead_type", "handle_clean", "store_name", "contact_name",
        "city", "stage", "spend_gbp", "priority_score", "next_action",
        "last_touch_date", "num_touches", "assigned_bdr"
    ]
    available = [c for c in display_cols if c in filtered.columns]
    show_df = filtered[available].copy()

    # Format
    if "spend_gbp" in show_df.columns:
        show_df["spend_gbp"] = show_df["spend_gbp"].apply(
            lambda x: f"£{x:,.0f}" if pd.notna(x) and x else "—"
        )
    if "last_touch_date" in show_df.columns:
        show_df["last_touch_date"] = pd.to_datetime(show_df["last_touch_date"], errors="coerce").dt.strftime("%d %b %Y")

    st.dataframe(
        show_df.fillna("—"),
        use_container_width=True,
        height=500,
    )
    st.caption(f"Showing {len(show_df)} leads after filters.")

    # Download
    csv = filtered.to_csv(index=False)
    st.download_button(
        "⬇️ Download filtered leads as CSV",
        csv,
        file_name=f"fleek_pipeline_{datetime.today().strftime('%Y%m%d')}.csv",
        mime="text/csv",
    )

# ─── Visit Planner tab ───────────────────────────────────────────────────

with tab_visits:
    st.markdown("### Shop Visit Planner")
    st.markdown("Shops grouped by city so you can book the most visits in one day.")

    shop_data = prioritised[shops & prioritised["city"].notna()].copy()
    groups = shop_visit_groups(shop_data)

    if not groups:
        st.info("No shops with city data.")
    else:
        city_tabs = st.tabs(list(groups.keys()))
        for city_tab, (city, leads) in zip(city_tabs, groups.items()):
            with city_tab:
                st.markdown(f"**{len(leads)} shops in {city}**")
                for lead in leads:
                    name = lead.get("store_name") or "—"
                    stage = lead.get("stage", "new")
                    spend = lead.get("spend_gbp") or 0
                    phone = lead.get("phone_clean") or "—"
                    email = lead.get("email_clean") or "—"
                    action = lead.get("next_action", "—")
                    st.markdown(f"""
**{name}**  ·  {stage_chip(stage)}  ·  £{spend:,.0f}/mo  
📞 `{phone}`  ·  📧 `{email}`  ·  Next: _{action}_
""", unsafe_allow_html=True)
                    st.divider()
