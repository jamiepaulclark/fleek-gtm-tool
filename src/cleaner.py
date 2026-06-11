"""
cleaner.py — Normalise raw pipeline data into a clean, typed DataFrame.
Handles: date formats, spend formats, stage names, handle formats,
         lead-type detection, duplicate removal.
"""

import re
import pandas as pd
from dateutil import parser as dateparser


# ── Stage normalisation ────────────────────────────────────────────────────

STAGE_MAP = {
    # new / untouched
    "new": "new",
    "new lead": "new",
    # contacted / attempted
    "contacted": "contacted",
    "contact": "contacted",
    # replied / engaged
    "replied": "replied",
    "reply": "replied",
    # warm (positive signal)
    "warm": "warm",
    # call booked
    "call booked": "call_booked",
    "call-booked": "call_booked",
    # negotiating
    "negotiating": "negotiating",
    "in negotiation": "negotiating",
    # ghosted / no reply
    "ghosted": "ghosted",
    "no response": "ghosted",
    # lost
    "lost": "lost",
    # won
    "won": "won",
    "closed won": "won",
}

def normalise_stage(raw: str) -> str:
    if pd.isna(raw):
        return "new"
    key = str(raw).strip().lower()
    return STAGE_MAP.get(key, key)


# ── Date parsing ───────────────────────────────────────────────────────────

def parse_date(raw) -> pd.Timestamp | None:
    if pd.isna(raw):
        return None
    s = str(raw).strip()
    if not s or s.lower() in ("nan", "none", ""):
        return None
    try:
        return pd.Timestamp(dateparser.parse(s, default=pd.Timestamp("2026-01-01")))
    except Exception:
        return None


# ── Spend normalisation ────────────────────────────────────────────────────

def parse_spend(raw) -> float | None:
    if pd.isna(raw):
        return None
    s = str(raw).strip().replace("£", "").replace(",", "").replace(" ", "")
    try:
        return float(s)
    except ValueError:
        return None


# ── Handle normalisation ───────────────────────────────────────────────────

def normalise_handle(raw) -> str | None:
    if pd.isna(raw):
        return None
    s = str(raw).strip()
    # full URL → extract username
    m = re.search(r"instagram\.com/([^/?]+)", s, re.IGNORECASE)
    if m:
        s = m.group(1)
    s = s.lstrip("@").strip()
    return s.lower() if s else None


# ── Source normalisation ───────────────────────────────────────────────────

RESELLER_SOURCES = {"instagram", "ig", "instagram_dm", "whatnot", "depop", "ebay", "vinted"}
SHOP_SOURCES = {"physical store", "store", "google_maps", "in-person"}

def normalise_source(raw: str) -> str:
    if pd.isna(raw):
        return "unknown"
    return str(raw).strip().lower()


# ── Lead-type detection ────────────────────────────────────────────────────

def detect_lead_type(row: pd.Series) -> str:
    """
    Classify as 'reseller' or 'shop' based on the actual data present,
    not just the source label.
    Rule:
      - Has followers/listings/velocity → reseller
      - Has email AND (phone or city) → shop
      - Source is a reseller platform → reseller
      - Source is a shop platform → shop
    """
    has_reseller_metrics = (
        pd.notna(row.get("followers")) or
        pd.notna(row.get("active_listings")) or
        pd.notna(row.get("sales_velocity_30d"))
    )
    has_shop_contacts = (
        pd.notna(row.get("email")) and
        (pd.notna(row.get("phone")) or pd.notna(row.get("city")))
    )
    src = normalise_source(row.get("source", ""))

    if has_reseller_metrics:
        return "reseller"
    if has_shop_contacts:
        return "shop"
    if src in RESELLER_SOURCES:
        return "reseller"
    if src in SHOP_SOURCES:
        return "shop"
    # fallback: handle present → reseller
    if pd.notna(row.get("handle")):
        return "reseller"
    return "shop"


# ── Numeric coercion ───────────────────────────────────────────────────────

def to_int(val) -> int | None:
    if pd.isna(val):
        return None
    try:
        return int(float(str(val).replace(",", "")))
    except (ValueError, TypeError):
        return None


# ── Email validation ───────────────────────────────────────────────────────

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

def validate_email(raw) -> str | None:
    if pd.isna(raw):
        return None
    s = str(raw).strip()
    return s if EMAIL_RE.match(s) else None


# ── Phone normalisation ────────────────────────────────────────────────────

def normalise_phone(raw) -> str | None:
    if pd.isna(raw):
        return None
    s = str(raw).strip()
    # 0044 → +44
    s = re.sub(r"^0044", "+44", s)
    # 07xxx → +447xxx
    s = re.sub(r"^07", "+447", s)
    digits = re.sub(r"[^\d+]", "", s)
    return digits if len(digits) >= 7 else None


# ── Main clean function ────────────────────────────────────────────────────

def clean_pipeline(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # --- 1. Normalise handle (needed for dedup key) ---
    df["handle_clean"] = df["handle"].apply(normalise_handle)

    # --- 2. Dedup: prefer row with most data ---
    # Key = handle_clean (resellers) or store_name+city (shops)
    df["_dedup_key"] = df["handle_clean"].fillna("") + "|" + df["store_name"].fillna("").str.lower() + "|" + df["city"].fillna("").str.lower()
    df["_data_richness"] = df.notna().sum(axis=1)
    df = (
        df.sort_values("_data_richness", ascending=False)
          .drop_duplicates(subset="_dedup_key", keep="first")
          .reset_index(drop=True)
    )
    df = df.drop(columns=["_dedup_key", "_data_richness"])

    # --- 3. Stage ---
    df["stage"] = df["stage"].apply(normalise_stage)

    # --- 4. Dates ---
    df["first_seen_date"] = df["first_seen_date"].apply(parse_date)
    df["last_touch_date"] = df["last_touch_date"].apply(parse_date)

    # --- 5. Spend ---
    df["spend_gbp"] = df["est_monthly_spend_gbp"].apply(parse_spend)

    # --- 6. Numeric metrics ---
    for col in ["followers", "active_listings", "sales_velocity_30d", "avg_listing_price_gbp", "num_touches"]:
        df[col] = df[col].apply(to_int)

    # --- 7. Contact fields ---
    df["email_clean"] = df["email"].apply(validate_email)
    df["phone_clean"] = df["phone"].apply(normalise_phone)

    # --- 8. Lead type ---
    df["lead_type"] = df.apply(detect_lead_type, axis=1)

    # --- 9. Source normalise ---
    df["source_clean"] = df["source"].apply(normalise_source)

    return df


def merge_new_batch(existing: pd.DataFrame, new_batch: pd.DataFrame) -> pd.DataFrame:
    """
    Merge a new batch of leads into existing cleaned pipeline.
    Skips any leads already present (by handle or store+city key).
    Returns combined DataFrame with only truly new rows appended.
    """
    existing_clean = clean_pipeline(existing)
    new_clean = clean_pipeline(new_batch)

    # Build seen keys from existing
    def make_key(row):
        h = str(row.get("handle_clean") or "").strip()
        s = str(row.get("store_name") or "").strip().lower()
        c = str(row.get("city") or "").strip().lower()
        return f"{h}|{s}|{c}"

    seen = set(existing_clean.apply(make_key, axis=1))
    new_only = new_clean[~new_clean.apply(make_key, axis=1).isin(seen)].copy()
    new_only["_is_new"] = True
    existing_clean["_is_new"] = False

    combined = pd.concat([existing_clean, new_only], ignore_index=True)
    return combined
