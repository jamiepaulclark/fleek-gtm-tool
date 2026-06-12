# System Design — How it fits together

## Architecture diagram

```
┌─────────────────────────────────────────────────────────────┐
│                        INPUT LAYER                           │
│                                                             │
│   pipeline.xlsx          new_drop_day2 sheet                │
│   (265 raw leads)   +    (30 fresh leads, any time)         │
└────────────────┬────────────────────┬───────────────────────┘
                 │                    │
                 ▼                    ▼
┌─────────────────────────────────────────────────────────────┐
│                    src/cleaner.py                            │
│                                                             │
│  • Deduplicates by handle + store_name + city key           │
│  • Normalises 25 stage variants → 9 canonical stages        │
│  • Parses 4 date formats → single timestamp                 │
│  • Validates emails (regex) and phones (+44 format)         │
│  • Detects lead type from DATA not label:                   │
│    - has followers/listings → reseller                      │
│    - has email + phone/city → shop                          │
│  • Merge new batch: skip dupes, flag new rows               │
└────────────────────────────┬────────────────────────────────┘
                             │  clean DataFrame
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                   src/prioritiser.py                         │
│                                                             │
│  RESELLERS (Instagram, 40 DM/day cap)                       │
│  Score 0–100:                                               │
│    40% spend · 25% stage · 20% recency · 10% signal · 5%   │
│  → Top 40 flagged as in_todays_queue                        │
│  → next_action: dm_first_outreach / dm_follow_up /          │
│                 dm_follow_up_warm / dm_re_engage / etc.     │
│                                                             │
│  SHOPS (email → call → visit)                               │
│  Score 0–100: same factors                                  │
│  → next_action driven by stage + contact fields available   │
│  → visit_groups.json: shops grouped by city                 │
└────────────────────────────┬────────────────────────────────┘
                             │  prioritised DataFrame
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                   src/messenger.py                           │
│                                                             │
│  For each lead: calls Anthropic API with lead context       │
│  → Personalised DM, email, or call script                   │
│  → Falls back to data-driven templates if API unavailable   │
│  → Max 80 API calls/run (top priority leads only)           │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                       OUTPUT LAYER                           │
│                                                             │
│   daily_actions.xlsx    dm_queue.csv    shop_outreach.csv   │
│   visit_groups.json     run_log.json                        │
│                                                             │
│   Live dashboard: jamiepaulclark.github.io/fleek-gtm-tool   │
└─────────────────────────────────────────────────────────────┘
```

## Where humans vs agents step in

| Step | Automated | Human / Agent |
|------|-----------|---------------|
| Clean + dedup pipeline | ✅ Fully automatic | — |
| Detect lead type | ✅ Fully automatic | — |
| Score and prioritise | ✅ Fully automatic | — |
| Draft messages | ✅ AI drafts via Claude API | Human reviews top 5, edits if needed |
| Send Instagram DMs | ⚠️ Queue is ready | Human sends (Instagram bans automation) |
| Send emails | ✅ Could pipe to Gmail API / Make | Human approves first run |
| Make calls | 📋 Script ready | Human makes the call |
| Book shop visits | 📍 City groups ready | Human books calendar |
| Update stage after reply | ⚠️ Manual today | Future: parse inbox → update CRM |

## How to scale to 30,000 leads

1. **Swap Excel for Postgres** — replace `pd.read_excel()` with `pd.read_sql()`. Scoring/messaging logic unchanged.
2. **Schedule daily run** — cron / GitHub Actions / Railway at 7am every morning.
3. **Automate sends** — pipe `dm_queue.csv` → Make/Zapier → Instagram Graph API or Phantombuster.
4. **Agent handoff** — give an AI agent the `daily_actions.xlsx` each morning. It reads drafted messages, confirms actions, executes. One person manages the exceptions.
5. **Enrich automatically** — scrape new reseller handles from Depop/Vinted search, feed directly into pipeline. No manual prospecting.

## Key design decisions

- **Dedup key**: `handle_clean | store_name_lower | city_lower` — catches same lead entered multiple ways
- **Lead type from data not label**: 20 leads in this pipeline had wrong source labels — fixing this matters commercially
- **40 DM cap is hard**: score is deterministic so the same leads don't get double-messaged if run twice on same day
- **Fallback messages**: tool always produces output even without API key — unblocks the team immediately
