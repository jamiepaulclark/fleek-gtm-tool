"""
messenger.py — Draft personalised outreach messages for each lead.

Uses the Anthropic API (claude-sonnet-4-20250514) to generate
context-aware messages. Falls back to template strings if the API
is unavailable so the tool always produces output.
"""

import os
import json
import requests
import pandas as pd

API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-4-20250514"

# ── Prompt builders ───────────────────────────────────────────────────────

def _reseller_system_prompt() -> str:
    return """You are a new business development rep at Fleek, a B2B marketplace for secondhand and vintage clothing.
Fleek lets online resellers (Depop, eBay, Vinted, Whatnot sellers) buy stock in bulk — 100 t-shirts or jeans at a time — at wholesale prices, saving them time sourcing.

Your job: write a short, conversational Instagram DM. Rules:
- Max 3 sentences. No emojis unless in re-engage context.
- Sound like a human, not a marketing robot.
- Reference specific data about the seller (followers, listings, what they sell) to show you've done your homework.
- Always end with a soft, specific question (not "let me know if you're interested").
- Never mention competitors or be pushy.
- Tone: friendly peer, not salesperson."""


def _shop_system_prompt() -> str:
    return """You are a new business development rep at Fleek, a B2B marketplace for secondhand and vintage clothing.
Fleek lets physical vintage shops buy wholesale stock — vintage bundles, graded lots, and category-specific bales — cutting their sourcing time significantly.

Your job: write a short, professional but warm outreach email or call script note.
- Email: subject line + 3–4 sentence body. Sign off as "The Fleek Team".
- Call note: a 2-sentence talking-point guide the rep reads from.
- Reference the shop name and city to personalise.
- End with a clear, single call to action."""


def _build_reseller_prompt(row: dict, action: str) -> str:
    handle = row.get("handle_clean") or row.get("handle") or "this seller"
    followers = row.get("followers") or "unknown"
    listings = row.get("active_listings") or "unknown"
    velocity = row.get("sales_velocity_30d") or "unknown"
    spend = row.get("spend_gbp") or "unknown"
    last_text = row.get("last_inbound_text") or ""
    stage = row.get("stage") or "new"
    touches = row.get("num_touches") or 0
    notes = row.get("notes") or ""

    action_map = {
        "dm_first_outreach": "Write a first cold DM to this reseller.",
        "dm_follow_up": "Write a follow-up DM. They were contacted before but haven't replied yet.",
        "dm_follow_up_warm": f"Write a warm follow-up DM. Their last message was: '{last_text}'. Keep the momentum going.",
        "dm_follow_up_negotiation": f"Write a DM to move them towards a first order. They are negotiating. Last message: '{last_text}'.",
        "dm_confirm_call": "Write a DM to confirm their upcoming call and get them excited.",
        "dm_re_engage": f"Write a gentle re-engagement DM. They went quiet after {touches} touches. Don't be needy. Be brief.",
    }

    instruction = action_map.get(action, "Write an appropriate DM.")

    return f"""Reseller details:
- Instagram handle: @{handle}
- Followers: {followers}
- Active listings: {listings}
- Items sold last 30 days: {velocity}
- Estimated monthly spend: £{spend}
- Pipeline stage: {stage}
- Previous touches: {touches}
- Notes: {notes}

Task: {instruction}

Return ONLY the DM text. No labels, no preamble."""


def _build_shop_prompt(row: dict, action: str) -> str:
    shop = row.get("store_name") or "your shop"
    city = row.get("city") or "your city"
    contact = row.get("contact_name") or ""
    stage = row.get("stage") or "new"
    touches = row.get("num_touches") or 0
    last_text = row.get("last_inbound_text") or ""
    notes = row.get("notes") or ""

    action_map = {
        "email_first_outreach": f"Write a first cold outreach EMAIL to {shop} in {city}.",
        "email_follow_up": f"Write a follow-up EMAIL. Already contacted {touches} times, no reply yet.",
        "email_re_engage": f"Write a re-engagement EMAIL. They went cold. Last message: '{last_text}'.",
        "call_first_outreach": f"Write a CALL SCRIPT NOTE (2 sentences) for a first cold call to {shop} in {city}.",
        "call_follow_up": f"Write a CALL SCRIPT NOTE for a follow-up call. Previous contact: {touches} touches.",
        "call_or_visit": f"Write a CALL SCRIPT NOTE to arrange a shop visit. They seem warm. Last message: '{last_text}'.",
        "call_close": f"Write a CALL SCRIPT NOTE to move towards closing. They're negotiating. Last message: '{last_text}'.",
        "prepare_for_call": f"Write a 2-sentence PREP NOTE for the upcoming call with {shop}.",
    }

    instruction = action_map.get(action, "Write an appropriate outreach.")
    contact_line = f"- Contact name: {contact}" if contact else ""

    return f"""Shop details:
- Shop name: {shop}
- City: {city}
{contact_line}
- Pipeline stage: {stage}
- Previous touches: {touches}
- Notes: {notes}

Task: {instruction}

Return ONLY the message text. For emails, start with 'Subject: ...' on the first line."""


# ── API call ──────────────────────────────────────────────────────────────

def _call_api(system: str, user: str) -> str:
    try:
        resp = requests.post(
            API_URL,
            headers={"Content-Type": "application/json"},
            json={
                "model": MODEL,
                "max_tokens": 300,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
            timeout=30,
        )
        data = resp.json()
        if "content" in data:
            return data["content"][0]["text"].strip()
        return f"[API error: {data.get('error', {}).get('message', 'unknown')}]"
    except Exception as e:
        return f"[Connection error: {str(e)}]"


# ── Fallback templates ────────────────────────────────────────────────────




def _fallback_message(row: dict, action: str) -> str:
    """
    Generate a personalised message using actual lead data.
    These are not generic templates — they pull in followers, velocity,
    last reply text, spend, and shop details to feel hand-written.
    """
    lead_type = row.get("lead_type", "reseller")
    handle = row.get("handle_clean") or "there"
    shop = row.get("store_name") or "your shop"
    city = row.get("city") or "your city"
    contact = row.get("contact_name") or ""
    contact_line = f" {contact}" if contact else ""
    followers = row.get("followers") or 0
    velocity = row.get("sales_velocity_30d") or 0
    spend = row.get("spend_gbp") or 0
    listings = row.get("active_listings") or 0
    last_text = str(row.get("last_inbound_text") or "").strip()
    notes = str(row.get("notes") or "").strip()
    touches = row.get("num_touches") or 0

    # Build context snippets for personalisation
    # Velocity signal
    if velocity >= 80:
        vel_note = f"you're moving {velocity} items a month"
    elif velocity >= 30:
        vel_note = f"you're selling around {velocity} items a month"
    else:
        vel_note = f"you've got {listings} listings live"

    # Follower signal
    if followers >= 20000:
        audience_note = f"with {followers:,} followers"
    elif followers >= 5000:
        audience_note = f"with a solid {followers:,}-person audience"
    else:
        audience_note = ""

    if lead_type == "reseller":
        if action == "dm_first_outreach":
            if followers >= 5000:
                return (
                    f"Hey @{handle} — noticed {vel_note} {audience_note}, that's a serious operation. "
                    f"At Fleek we supply resellers with bulk vintage (100+ pieces at wholesale) so you're "
                    f"not spending half your week sourcing. Worth a quick look at what we've got in stock?"
                )
            else:
                return (
                    f"Hey @{handle} — love the range. At Fleek we work with resellers to get bulk vintage "
                    f"stock sorted fast — 100+ pieces, wholesale prices. "
                    f"Would it help if I sent over what we have in your category?"
                )

        elif action == "dm_follow_up":
            return (
                f"Hey @{handle} — just following up from my last message. "
                f"Happy to put together a bundle specifically for what you sell — "
                f"no commitment, just so you can see what we've got. Does that work?"
            )

        elif action == "dm_follow_up_warm":
            if last_text and len(last_text) > 5:
                # Reference what they said
                return (
                    f"Hey @{handle} — appreciate you getting back to me. "
                    f"Based on what you mentioned, I can put together a tailored bundle. "
                    f"What's the mix you move fastest — basics, graphic tees, denim?"
                )
            else:
                return (
                    f"Hey @{handle} — great to hear from you! "
                    f"Given {vel_note}, I reckon we could save you a lot of sourcing time. "
                    f"What categories move fastest for you right now?"
                )

        elif action == "dm_follow_up_negotiation":
            return (
                f"Hey @{handle} — wanted to pick back up where we left off. "
                f"Happy to put together a sample order first so you can check the quality before committing to anything bigger. "
                f"Want me to send over what that would look like?"
            )

        elif action == "dm_confirm_call":
            return (
                f"Hey @{handle} — looking forward to the call! "
                f"I'll have a few bundle options ready based on your listings. "
                f"Anything specific you want me to pull together beforehand?"
            )

        elif action == "dm_re_engage":
            return (
                f"Hey @{handle} — it's been a while, just checking back in. "
                f"We've had some good new drops come in recently. "
                f"If the timing's better now, happy to send over what's available."
            )

        else:
            return (
                f"Hey @{handle} — following up from Fleek. "
                f"We supply bulk vintage stock to resellers — happy to put something together for you. "
                f"Let me know if you'd like to take a look."
            )

    else:
        # Shop messages
        if action == "email_first_outreach":
            return (
                f"Subject: Bulk vintage stock for {shop}\n\n"
                f"Hi{contact_line},\n\n"
                f"I'm reaching out from Fleek — we supply vintage shops in {city} with curated bulk lots "
                f"(graded by category and condition, 100+ pieces). Most of our shop partners cut their "
                f"sourcing time significantly once they're set up with us.\n\n"
                f"Would you be open to a 10-minute call to see if what we carry fits {shop}?\n\n"
                f"Best,\nThe Fleek Team"
            )

        elif action in ("email_follow_up", "email_re_engage"):
            if last_text and len(last_text) > 5:
                return (
                    f"Subject: Re: Fleek stock for {shop}\n\n"
                    f"Hi{contact_line},\n\n"
                    f"Just following up — you mentioned '{last_text[:60]}{'...' if len(last_text)>60 else ''}' "
                    f"and I wanted to make sure I got back to you properly.\n\n"
                    f"Happy to send over a sample selection or jump on a quick call whenever suits.\n\n"
                    f"Best,\nThe Fleek Team"
                )
            else:
                return (
                    f"Subject: Quick follow-up — Fleek stock for {shop}\n\n"
                    f"Hi{contact_line},\n\n"
                    f"Just checking in — we've had some good new lots come in that would likely suit {shop}. "
                    f"Happy to send details or arrange a quick call at your convenience.\n\n"
                    f"Best,\nThe Fleek Team"
                )

        elif action == "call_first_outreach":
            return (
                f"Opening: 'Hi, I'm calling from Fleek — we supply bulk vintage stock to shops like {shop} in {city}.'\n"
                f"Pitch: 'We work with shops to take the sourcing grind out of the equation — curated lots, graded by category, delivered fast.'\n"
                f"Ask: 'Is now a good moment, or when would be better for a two-minute chat?'"
            )

        elif action == "call_follow_up":
            return (
                f"Opening: 'Hi{contact_line}, calling back from Fleek — I reached out about bulk vintage sourcing for {shop}.'\n"
                f"Bridge: 'I know it can be hard to find time — happy to send something over by email instead if that's easier.'\n"
                f"Ask: 'Would that work, or is there a better time to talk?'"
            )

        elif action == "call_or_visit":
            return (
                f"Opening: 'Really glad you're interested — I'd love to come by {shop} and bring a few samples so you can see the quality in person.'\n"
                f"Ask: 'Would later this week or next work for a 15-minute visit? I'm flexible on time.'"
            )

        elif action == "call_close":
            return (
                f"Opening: 'Following up on the details we discussed for {shop}.'\n"
                f"Bridge: 'I want to make sure we get the right lot together for you — have you had a chance to look at the options I sent?'\n"
                f"Ask: 'Are there any remaining questions, or shall we get the first order sorted?'"
            )

        elif action == "prepare_for_call":
            return (
                f"Prep note for {shop} ({city}): Review their last message and stage. "
                f"Have 2–3 bundle options ready at different price points (around £{max(500, int((spend or 0)*0.5)):,.0f}, "
                f"£{int(spend or 1000):,.0f}, £{int((spend or 1000)*1.5):,.0f}). "
                f"Lead with what they'd stock, not the price. Ask what sells fastest in their shop."
            )

        else:
            return (
                f"Subject: Fleek — bulk vintage stock for {shop}\n\n"
                f"Hi{contact_line},\n\n"
                f"Following up from Fleek about bulk vintage sourcing for {shop}. "
                f"Happy to share what we have available or arrange a quick call.\n\n"
                f"Best,\nThe Fleek Team"
            )


# ── Public API ────────────────────────────────────────────────────────────

def draft_message(row: dict, action: str, use_api: bool = True) -> str:
    """
    Generate a personalised message for a lead.
    If use_api=True, tries the Anthropic API first.
    Falls back to data-driven personalised templates on failure.
    """
    if action == "no_action":
        return ""

    if use_api:
        lead_type = row.get("lead_type", "reseller")
        if lead_type == "reseller":
            system = _reseller_system_prompt()
            user = _build_reseller_prompt(row, action)
        else:
            system = _shop_system_prompt()
            user = _build_shop_prompt(row, action)
        msg = _call_api(system, user)
        if not msg.startswith("["):  # no error prefix means success
            return msg

    # Personalised fallback using actual lead data
    return _fallback_message(row, action)


def draft_messages_batch(df: pd.DataFrame, use_api: bool = True, max_api_calls: int = 80) -> pd.Series:
    """
    Draft messages for all leads in df.
    Limits API calls to max_api_calls to avoid burning tokens on non-priority leads.
    """
    messages = []
    api_calls = 0

    for _, row in df.iterrows():
        action = row.get("next_action", "no_action")
        if action == "no_action":
            messages.append("")
            continue

        # Only use API for top-priority leads
        call_api = use_api and api_calls < max_api_calls
        msg = draft_message(row.to_dict(), action, use_api=call_api)
        if call_api and not msg.startswith("["):
            api_calls += 1
        messages.append(msg)

    return pd.Series(messages, index=df.index)
