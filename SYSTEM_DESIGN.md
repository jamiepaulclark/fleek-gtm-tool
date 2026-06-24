# System Design — How the Fleek GTM Tool Fits Together

## Architecture diagram

```
┌─────────────────────────────────────────────────────┐
│                    INPUT LAYER                      │
│                                                     │
│  pipeline.xlsx          new_drop_day2 sheet         │
│  (265 raw leads)   +    (30 fresh leads, any time)  │
└──────────────┬──────────────────┬───────────────────┘
               │                  │
               ▼                  ▼
┌─────────────────────────────────────────────────────┐
│                 src/cleaner.py                      │
│                                                     │
│  • Deduplicates by handle + store_name + city key   │
│  • Normalises 25 stage variants → 9 canonical       │
│  • Parses 4 date formats → single timestamp         │
│  • Validates emails (regex) and phones (+44 format) │
│  • Detects lead type from DATA not label:           │
│    - has follower count / listings → reseller       │
│    - has email + phone + city → shop                │
│    - has both → reseller + email (dual channel)     │
└──────────────────────────┬──────────────────────────┘
                           │  clean DataFrame
                           ▼
┌─────────────────────────────────────────────────────┐
│                src/prioritiser.py                   │
│                                                     │
│  RESELLERS (40 DM/day cap):                         │
│    Score 0-100:                                     │
│    40% estimated monthly spend (commercial value)   │
│    25% stage proximity (negotiating > warm > new)   │
│    20% days since last touch (sweet spot 3-14 days) │
│    10% positive signal in last reply                │
│     5% follower count (tiebreaker)                  │
│    → Top 40 go into dm_queue                        │
│                                                     │
│  SHOPS (email → call → visit sequence):             │
│    Same spend/stage/recency weighting               │
│    Next action determined by stage:                 │
│    new → email_first_outreach                       │
│    contacted → call_follow_up                       │
│    warm/replied → call_or_visit                     │
│    negotiating → call_close                         │
│    ghosted → email_re_engage or no_action           │
└──────────────────────────┬──────────────────────────┘
                           │  prioritised DataFrame
                           ▼
┌─────────────────────────────────────────────────────┐
│                 src/messenger.py                    │
│                                                     │
│  For each lead:                                     │
│  1. Reads their last reply text                     │
│  2. Identifies what they said (objection, question, │
│     request, call booking, timing pushback etc.)    │
│  3. Calls Claude API → contextual response          │
│  4. Falls back to smart templates if API down       │
│                                                     │
│  Result: personalised DM, email, or call script     │
│  that responds to what they actually said           │
└──────────────────────────┬──────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────┐
│                    OUTPUTS                          │
│                                                     │
│  output/daily_actions.xlsx   full pipeline          │
│  output/dm_queue.csv         today's 40 DMs         │
│  output/shop_outreach.csv    today's shop list      │
│  output/visit_groups.json    shops by city          │
│  docs/index.html             live dashboard         │
└──────────────────────────┬──────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────┐
│              WHERE HUMANS/AGENTS STEP IN            │
│                                                     │
│  AUTOMATED (no human needed):                       │
│  • Full pipeline run (cron job at 7am)              │
│  • Shop emails (Gmail API)                          │
│  • New lead ingestion (scraper → pipeline)          │
│                                                     │
│  HUMAN IN THE LOOP:                                 │
│  • Instagram DM sends (Instagram bans automation)   │
│    → 20 mins/day, rep reviews queue and hits send   │
│  • Phone calls (script provided, human dials)       │
│  • Stage updates after replies                      │
│  • Visit scheduling (tool groups by city, human     │
│    books the calendar)                              │
└─────────────────────────────────────────────────────┘
```

## Scaling from 265 to 30,000 leads

| Component | Now (265 leads) | At scale (30,000+) |
|---|---|---|
| Data store | Excel file | Postgres / Supabase table |
| Lead ingestion | Manual Excel update | Nightly scraper (Depop, Vinted, Google Maps) |
| Pipeline run | `python run_pipeline.py` in Terminal | Cron job / GitHub Action at 7am |
| DM sends | Human copies and sends | Human reviews queue (still 20 mins/day) |
| Email sends | Human sends manually | Gmail API — fully automated |
| Outputs | Local CSV/Excel | S3 bucket / Google Sheets |
| Dashboard | GitHub Pages static HTML | Same, or upgrade to Streamlit Cloud |

**The scoring, messaging, and dedup logic does not change at all.**
Only the data layer changes. This was a design decision made at the start.

## Two channels — what AI does vs what a person does

### Instagram resellers
| Task | Who does it |
|---|---|
| Score and rank who to DM today | Tool (automated) |
| Read last reply and write contextual DM | Claude API (automated) |
| Review DM for quality | Human (2 mins per batch) |
| Press send on Instagram | Human (Instagram bans automation) |
| Update stage when they reply | Human |

### Physical shops
| Task | Who does it |
|---|---|
| Score and sequence shops | Tool (automated) |
| Write email / call script | Claude API (automated) |
| Send email | Gmail API (automated) |
| Make phone call | Human (script written by tool) |
| Book visit day | Human (city grouping done by tool) |
| Update stage after contact | Human |
