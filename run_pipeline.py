"""
run_pipeline.py — Daily pipeline runner for Fleek GTM Acquisition.

Usage:
    # First run (or re-run on main pipeline only)
    python run_pipeline.py

    # Merge in new batch (Day 2 leads, etc.)
    python run_pipeline.py --new-batch data/pipeline.xlsx --new-sheet new_drop_day2

    # Skip AI message drafting (faster, uses templates)
    python run_pipeline.py --no-ai

    # Specify a custom input file
    python run_pipeline.py --input data/my_pipeline.xlsx

The tool outputs:
    output/daily_actions.xlsx  — full prioritised action list
    output/dm_queue.csv        — today's 40 Instagram DMs
    output/shop_outreach.csv   — today's shop email/call list
    output/visit_groups.json   — shops grouped by city for visit planning
    output/run_log.json        — metadata for the run
"""

import argparse
import json
import os
import sys
from datetime import datetime

import pandas as pd

# Ensure src/ is importable when run from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from cleaner import clean_pipeline, merge_new_batch
from prioritiser import prioritise, shop_visit_groups
from messenger import draft_messages_batch

TODAY_STR = datetime.today().strftime("%Y-%m-%d")

OUTPUT_COLS_RESELLER = [
    "lead_id", "lead_type", "handle_clean", "contact_name",
    "followers", "active_listings", "sales_velocity_30d",
    "spend_gbp", "stage", "last_touch_date", "num_touches",
    "last_inbound_text", "next_action", "priority_score",
    "in_todays_queue", "drafted_message", "assigned_bdr", "notes",
]

OUTPUT_COLS_SHOP = [
    "lead_id", "lead_type", "store_name", "contact_name",
    "email_clean", "phone_clean", "city", "country",
    "spend_gbp", "stage", "last_touch_date", "num_touches",
    "last_inbound_text", "next_action", "priority_score",
    "drafted_message", "assigned_bdr", "notes",
]


def load_data(input_path: str, sheet: str = "pipeline") -> pd.DataFrame:
    print(f"  Loading {input_path} [{sheet}]...")
    return pd.read_excel(input_path, sheet_name=sheet, dtype=str)


def run(args):
    os.makedirs("output", exist_ok=True)

    print("\n🔄  FLEEK GTM PIPELINE — Daily Run")
    print(f"    Date: {TODAY_STR}")
    print("=" * 50)

    # 1. Load main pipeline
    print("\n[1/5] Loading data...")
    raw = load_data(args.input, args.sheet)
    print(f"      Loaded {len(raw)} raw rows from main pipeline.")

    # 2. Merge new batch if provided
    if args.new_batch:
        print(f"      Loading new batch from {args.new_batch} [{args.new_sheet}]...")
        new_raw = load_data(args.new_batch, args.new_sheet)
        df = merge_new_batch(raw, new_raw)
        new_count = df["_is_new"].sum()
        print(f"      Merged: {new_count} new leads added, {len(new_raw) - new_count} duplicates skipped.")
        df = df.drop(columns=["_is_new"], errors="ignore")
    else:
        print("\n[2/5] Cleaning data...")
        df = clean_pipeline(raw)

    print(f"      After dedup + clean: {len(df)} unique leads.")
    reseller_count = (df["lead_type"] == "reseller").sum()
    shop_count = (df["lead_type"] == "shop").sum()
    print(f"      Lead types → Resellers: {reseller_count}  |  Shops: {shop_count}")

    # 3. Prioritise
    print("\n[3/5] Prioritising leads...")
    prioritised = prioritise(df)
    active = len(prioritised)
    dm_queue_count = prioritised[
        (prioritised["lead_type"] == "reseller") & prioritised.get("in_todays_queue", False)
    ].shape[0] if "in_todays_queue" in prioritised.columns else 0
    print(f"      Active leads (with next action): {active}")
    print(f"      Today's DM queue: {dm_queue_count} / 40")

    # 4. Draft messages
    print(f"\n[4/5] Drafting messages (AI={'enabled' if not args.no_ai else 'disabled'})...")
    prioritised["drafted_message"] = draft_messages_batch(
        prioritised,
        use_api=not args.no_ai,
        max_api_calls=80,
    )
    print("      Messages drafted.")

    # 5. Write outputs
    print("\n[5/5] Writing outputs...")

    resellers_out = prioritised[prioritised["lead_type"] == "reseller"].copy()
    shops_out = prioritised[prioritised["lead_type"] == "shop"].copy()

    # ── daily_actions.xlsx (all leads, two sheets) ──
    xlsx_path = "output/daily_actions.xlsx"
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        _write_sheet(resellers_out, writer, "Resellers", OUTPUT_COLS_RESELLER)
        _write_sheet(shops_out, writer, "Shops", OUTPUT_COLS_SHOP)
    print(f"      ✅  output/daily_actions.xlsx")

    # ── dm_queue.csv (today's 40 DMs) ──
    dm_q = resellers_out[resellers_out.get("in_todays_queue", pd.Series(False)) == True].copy() \
        if "in_todays_queue" in resellers_out.columns \
        else resellers_out.head(40).copy()
    dm_cols = ["lead_id", "handle_clean", "stage", "next_action", "priority_score", "drafted_message"]
    dm_q[[c for c in dm_cols if c in dm_q.columns]].to_csv("output/dm_queue.csv", index=False)
    print(f"      ✅  output/dm_queue.csv  ({len(dm_q)} DMs queued)")

    # ── shop_outreach.csv ──
    shop_cols = ["lead_id", "store_name", "contact_name", "email_clean", "phone_clean",
                 "city", "stage", "next_action", "priority_score", "drafted_message"]
    shops_out[[c for c in shop_cols if c in shops_out.columns]].to_csv(
        "output/shop_outreach.csv", index=False
    )
    print(f"      ✅  output/shop_outreach.csv  ({len(shops_out)} shops)")

    # ── visit_groups.json ──
    visit_shops = shops_out[shops_out.get("next_action", pd.Series("")) == "call_or_visit"].copy() \
        if "next_action" in shops_out.columns else shops_out
    # include all shops with city for grouping
    all_city_shops = shops_out[shops_out["city"].notna()].copy() if "city" in shops_out.columns else shops_out
    groups = shop_visit_groups(all_city_shops)
    with open("output/visit_groups.json", "w") as f:
        json.dump(groups, f, indent=2, default=str)
    print(f"      ✅  output/visit_groups.json  ({len(groups)} cities)")

    # ── run_log.json ──
    log = {
        "run_date": TODAY_STR,
        "input_file": args.input,
        "new_batch": args.new_batch,
        "total_leads_after_clean": len(df),
        "resellers": int(reseller_count),
        "shops": int(shop_count),
        "active_leads": int(active),
        "dm_queue_size": int(len(dm_q)),
        "ai_messages": not args.no_ai,
    }
    with open("output/run_log.json", "w") as f:
        json.dump(log, f, indent=2)
    print(f"      ✅  output/run_log.json")

    print("\n" + "=" * 50)
    print("✅  Run complete.\n")
    _print_summary(dm_q, shops_out)


def _write_sheet(df: pd.DataFrame, writer, sheet_name: str, cols: list):
    available = [c for c in cols if c in df.columns]
    extra = [c for c in df.columns if c not in available and c not in ("handle", "source", "email", "phone")]
    out = df[available + extra].copy()
    out.to_excel(writer, sheet_name=sheet_name, index=False)
    ws = writer.sheets[sheet_name]
    # Auto-width columns
    for col in ws.columns:
        max_len = max((len(str(cell.value or "")) for cell in col), default=10)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 60)


def _print_summary(dm_q: pd.DataFrame, shops: pd.DataFrame):
    print("📋  TODAY'S SNAPSHOT")
    print("-" * 50)
    print(f"  Instagram DMs to send:  {len(dm_q)}")
    if len(dm_q) > 0 and "handle_clean" in dm_q.columns:
        print("  Top 5 DM targets:")
        for _, r in dm_q.head(5).iterrows():
            handle = r.get("handle_clean", "—")
            score = r.get("priority_score", "—")
            action = r.get("next_action", "—")
            print(f"    @{handle:<30} score={score:<6} action={action}")

    print(f"\n  Shop outreach leads:    {len(shops)}")
    if len(shops) > 0:
        print("  Top 5 shop targets:")
        for _, r in shops.head(5).iterrows():
            name = r.get("store_name", "—")
            city = r.get("city", "—")
            action = r.get("next_action", "—")
            print(f"    {name:<25} ({city:<15}) action={action}")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fleek GTM Pipeline Daily Runner")
    parser.add_argument("--input", default="data/pipeline.xlsx", help="Path to main pipeline Excel file")
    parser.add_argument("--sheet", default="pipeline", help="Sheet name in main pipeline file")
    parser.add_argument("--new-batch", default=None, help="Path to new batch Excel file (optional)")
    parser.add_argument("--new-sheet", default="new_drop_day2", help="Sheet name in new batch file")
    parser.add_argument("--no-ai", action="store_true", help="Disable AI message drafting (use templates)")
    args = parser.parse_args()
    run(args)
