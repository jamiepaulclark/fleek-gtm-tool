# Fleek GTM Acquisition Tool

A repeatable, agent-ready pipeline tool for Fleek's new business team. It cleans messy inherited pipeline data, classifies leads, scores and prioritises them for daily action, drafts personalised outreach messages, and keeps working every morning when you drop in fresh leads.

---

## What it does

| Step | What happens |
|---|---|
| **Clean** | Removes duplicates, normalises stage names (25 variants → 9), parses 4 date formats, strips £ signs from spend, validates emails and phones |
| **Classify** | Detects lead type from actual data (reseller metrics, contact fields) — not just the label |
| **Score** | Ranks resellers for the 40-DM/day Instagram cap; ranks shops for email → call → visit sequencing |
| **Act** | Determines the exact next action for each lead (first outreach, follow-up, re-engage, close) |
| **Draft** | Writes the DM, email subject+body, or call script using Claude AI (falls back to templates if API unavailable) |
| **Merge** | Ingests new batches without messaging anyone twice — safe to run every morning |

---

## How the system fits together

```
Raw Excel (pipeline tab)
        │
        ▼
┌─────────────────┐
│   cleaner.py    │  Dedup · normalise stages · parse dates · validate contacts
└────────┬────────┘
         │  clean DataFrame
         ▼
┌─────────────────┐
│ prioritiser.py  │  Score 0–100 · assign next_action · cap DMs at 40
└────────┬────────┘
         │  prioritised DataFrame
         ▼
┌─────────────────┐
│  messenger.py   │  Claude API → personalised DM / email / call script
└────────┬────────┘
         │
         ▼
  output/
  ├── daily_actions.xlsx   (full pipeline, two sheets)
  ├── dm_queue.csv         (today's 40 Instagram DMs)
  ├── shop_outreach.csv    (today's shop email/call list)
  ├── visit_groups.json    (shops grouped by city)
  └── run_log.json         (run metadata)
```

**Where a person or agent steps in:**
- The tool produces the message — a human reads it and hits send (or an agent like Make/Zapier sends it via Instagram Graph API / Gmail).
- Any reply that changes a lead's stage gets updated in the pipeline Excel and re-run the next morning.
- At 30,000 leads: swap the Excel input for a Postgres/Supabase table; the scoring and messaging logic is identical.

---

## Quick start

```bash
# 1. Clone
git clone https://github.com/YOUR_USERNAME/fleek-gtm-tool.git
cd fleek-gtm-tool

# 2. Install dependencies
pip install -r requirements.txt

# 3. Put your pipeline Excel in data/
cp /path/to/your/pipeline.xlsx data/pipeline.xlsx

# 4. Run the daily pipeline (CLI)
python run_pipeline.py

# 5. Or launch the interactive dashboard
streamlit run app.py
```

---

## CLI usage

```bash
# Standard daily run
python run_pipeline.py

# Merge in Day 2 (or any new batch) — skips duplicates automatically
python run_pipeline.py --new-batch data/pipeline.xlsx --new-sheet new_drop_day2

# Skip AI message drafting (faster, uses templates instead)
python run_pipeline.py --no-ai

# Custom input file
python run_pipeline.py --input data/my_pipeline.xlsx --sheet pipeline
```

---

## Dashboard (Streamlit)

```bash
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser. Upload your pipeline Excel via the sidebar. Optionally upload a new batch (Day 2+) to see the merge in action.

Features:
- **DM Queue tab** — today's top 40 resellers with drafted messages you can edit before sending
- **Shop Outreach tab** — sequenced email/call/visit queue with drafted messages
- **All Leads tab** — filterable full pipeline with CSV export
- **Visit Planner tab** — shops grouped by city for booking visit days

---

## Prioritisation logic

### Resellers (Instagram DMs, 40/day cap)

| Factor | Weight | Rationale |
|---|---|---|
| Est. monthly spend | 40 pts | Commercial value is the primary signal |
| Stage proximity to close | 25 pts | Warm/replied > contacted > new > ghosted |
| Days since last touch | 20 pts | Sweet spot 3–14 days; stale = slight boost |
| Positive engagement signal | 10 pts | Keywords in last reply (yes, send, interested…) |
| Follower count | 5 pts | Tie-breaker; bigger audience = bigger buyer |

### Shops (email → call → visit)

Same spend/stage/recency weighting. Next action is determined by stage:
- `new` with email → `email_first_outreach`
- `contacted` with phone → `call_follow_up`
- `warm` or `replied` → `call_or_visit`
- `negotiating` → `call_close`
- `ghosted` < 3 touches → `email_re_engage`; otherwise `no_action`

---

## Scaling to 30,000 leads

The tool is designed so swapping the data layer is the only change needed:

1. **Replace Excel with a database** — swap `pd.read_excel()` for `pd.read_sql()` against Postgres/Supabase. The cleaning and scoring functions take a DataFrame and don't care where it came from.
2. **Run on a schedule** — drop `run_pipeline.py` into a cron job, GitHub Action, or Railway cron. Outputs go to S3/GCS instead of local `output/`.
3. **Automate sends** — pipe `dm_queue.csv` into a Make/Zapier workflow hitting Instagram Graph API or an automation tool like Phantombuster.
4. **Agent handoff** — give an agent (Claude, GPT-4, n8n AI agent) the `daily_actions.xlsx` as context each morning. It reads the drafted message, confirms the action, and executes.

---

## Project structure

```
fleek-gtm-tool/
├── app.py                 # Streamlit dashboard
├── run_pipeline.py        # CLI entry point
├── requirements.txt
├── README.md
├── data/
│   └── pipeline.xlsx      # Your input file (not committed — add to .gitignore)
├── output/                # Generated daily (not committed)
│   ├── daily_actions.xlsx
│   ├── dm_queue.csv
│   ├── shop_outreach.csv
│   ├── visit_groups.json
│   └── run_log.json
└── src/
    ├── __init__.py
    ├── cleaner.py          # Data cleaning and deduplication
    ├── prioritiser.py      # Scoring and next-action logic
    └── messenger.py        # Message drafting (AI + fallback templates)
```

---

## How I used AI to build this

- **Claude (this tool)** — used to explore the data, design the scoring model, write the core Python, and draft the message templates. It sped up the data-wrangling logic (date parsing, dedup key design) significantly. The main place it needed human judgment was the prioritisation weights — I set those based on what actually matters commercially, not what an AI would guess.
- **Message drafting** — the tool calls `claude-sonnet-4-20250514` at runtime to write contextual DMs and emails. It uses the actual lead data (followers, listings, last reply) so every message is specific, not templated. Falls back to hand-written templates if the API is unavailable.
- **Where AI didn't help** — deciding which stage names to collapse (there were 25 variants), and designing the dedup logic for leads that appear under slightly different handle formats. That needed a human to look at the actual data.
