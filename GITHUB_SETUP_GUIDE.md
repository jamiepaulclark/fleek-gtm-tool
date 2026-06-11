# How to get this on GitHub — step by step

No prior GitHub experience needed. This takes about 10 minutes.

---

## Step 1: Create a GitHub account

1. Go to https://github.com and click **Sign up**
2. Enter your email, create a password, choose a username (e.g. `your-name`)
3. Verify your email

---

## Step 2: Download the project zip

Download the `fleek-gtm-tool.zip` file I've provided.

Unzip it. You'll get a folder called `fleek-gtm-tool` with these files inside:
```
fleek-gtm-tool/
├── app.py
├── run_pipeline.py
├── requirements.txt
├── README.md
├── .gitignore
└── src/
    ├── __init__.py
    ├── cleaner.py
    ├── prioritiser.py
    └── messenger.py
```

---

## Step 3: Install Git on your computer

**Mac**: Open Terminal (search "Terminal" in Spotlight) and run:
```
git --version
```
If it asks you to install, say yes.

**Windows**: Download from https://git-scm.com and install with all defaults.

---

## Step 4: Install Python (if you don't have it)

Go to https://www.python.org/downloads/ and download Python 3.11 or 3.12.
During install on Windows, tick **"Add Python to PATH"**.

Test it worked:
```
python --version
```

---

## Step 5: Create a new GitHub repo

1. Log into GitHub
2. Click the **+** button top right → **New repository**
3. Name it: `fleek-gtm-tool`
4. Set it to **Public**
5. Do NOT tick "Add README" — leave it empty
6. Click **Create repository**

GitHub will show you a page with setup instructions. Keep this page open.

---

## Step 6: Add your pipeline data

Inside the `fleek-gtm-tool` folder, create a folder called `data`.
Put your `pipeline.xlsx` (the Fleek case study Excel file) inside it.

---

## Step 7: Push the code to GitHub

Open Terminal (Mac) or Command Prompt / Git Bash (Windows).

Navigate to your project folder:
```bash
cd path/to/fleek-gtm-tool
```
(e.g. `cd ~/Downloads/fleek-gtm-tool` on Mac)

Then run these commands one by one:

```bash
git init
git branch -m main
git add README.md
git commit -m "docs: add README with system diagram and setup guide"

git add src/cleaner.py
git commit -m "feat(cleaner): data cleaning, dedup, date/spend normalisation, lead-type detection"

git add src/prioritiser.py
git commit -m "feat(prioritiser): scoring engine for resellers (DM cap) and shops (email>call>visit)"

git add src/messenger.py src/__init__.py
git commit -m "feat(messenger): personalised message drafting with Anthropic API + data-driven fallbacks"

git add run_pipeline.py
git commit -m "feat: CLI runner - clean, prioritise, draft, export daily outputs"

git add app.py
git commit -m "feat(dashboard): Streamlit UI with DM queue, shop outreach, visit planner tabs"

git add requirements.txt .gitignore
git commit -m "chore: requirements.txt and .gitignore"
```

Now connect to GitHub and push. Replace `YOUR_USERNAME` with your GitHub username:

```bash
git remote add origin https://github.com/YOUR_USERNAME/fleek-gtm-tool.git
git push -u origin main
```

It will ask for your GitHub username and password. For the password, use a **Personal Access Token** (not your GitHub login password):
- Go to GitHub → Settings → Developer Settings → Personal access tokens → Tokens (classic)
- Click "Generate new token (classic)"
- Tick the **repo** checkbox
- Copy the token and paste it as your password

---

## Step 8: Verify it worked

Go to `https://github.com/YOUR_USERNAME/fleek-gtm-tool`

You should see all your files and the commit history. 

**This is the link you send to Fleek.**

---

## Step 9: Run the tool locally (for your Loom video)

In Terminal, from the `fleek-gtm-tool` folder:

```bash
# Install dependencies (one time only)
pip install -r requirements.txt

# Run the daily pipeline (CLI)
python run_pipeline.py

# Then run with Day 2 batch to show deduplication
python run_pipeline.py --new-batch data/pipeline.xlsx --new-sheet new_drop_day2

# Launch the dashboard
streamlit run app.py
```

The dashboard opens at http://localhost:8501 in your browser.

---

## Loom video script (5-10 minutes)

### What to record
Use Loom (https://www.loom.com) — free, records your screen + face.

### What to say and show

**[0:00 – 0:45] The problem**
> "I inherited a pipeline of 265 leads on day one — a mix of Instagram resellers and physical vintage shops. The data was a mess: 25 different stage names, dates in 4 formats, duplicate leads. Here's what it looks like raw."
*Show the Excel file briefly*

**[0:45 – 2:00] The tool — CLI run**
> "So I built a pipeline runner. Let me show it running."
```
python run_pipeline.py --no-ai
```
> "It cleaned 265 rows down to 249 unique leads, detected 186 resellers and 63 shops from the actual data — not just the label. It scored them, capped Instagram DMs at 40, and drafted messages for each one."
*Show the output files in the folder*

**[2:00 – 3:30] The Day 2 batch**
> "The important bit — this tool can't be a one-off. Here's what happens when the Day 2 leads come in."
```
python run_pipeline.py --new-batch data/pipeline.xlsx --new-sheet new_drop_day2 --no-ai
```
> "28 new leads merged. 2 duplicates skipped. Nobody gets messaged twice. This is what it means to build something an agent can run."

**[3:30 – 5:30] The dashboard**
> "I also built a Streamlit dashboard so the team can see this without touching the command line."
```
streamlit run app.py
```
*Open http://localhost:8501*
> "DM queue — top 40 resellers scored by value, stage, recency, and engagement signals. Click any lead to see the drafted message. For shops, it sequences email → call → visit based on what contact details we have. The visit planner groups shops by city for booking visit days."

**[5:30 – 7:00] The repo**
> "Here's the GitHub repo. The commits show how I built it — cleaner first, then scoring, then messages, then the CLI, then the dashboard. The README has the system diagram."
*Show GitHub, click through commits*

**[7:00 – 8:00] Triage answer (important — they'll ask this)**
> "On day one, if I have 40 DMs to spend: I'd go straight to the warm and replied leads in negotiation — they're closest to a deal. High spend estimates filter first. Then recency — anyone stale for 3–14 days without a follow-up. That's @prelovedthreads, @plumetonicthreads, @relicthreads first. Not the ghosted ones or new cold leads — they can wait until the hot pipeline is worked."

---

## Debrief talking points

**Triage (who gets the 40 DMs and why):**
- Negotiating + high spend first → closest to revenue
- Warm/replied + stale 3-14 days → momentum that needs a nudge
- Cold new leads last → no signal yet, lower conversion odds
- Score is: 40% spend + 25% stage + 20% recency + 10% positive signal + 5% followers

**Scaling to 30,000 leads:**
- Swap Excel for Postgres/Supabase — the Python just uses DataFrames, the data source doesn't matter
- Schedule via cron / GitHub Actions / Railway — runs every morning at 7am
- Pipe dm_queue.csv into Instagram automation (e.g. Phantombuster, Make)
- Pipe shop_outreach.csv into a CRM (HubSpot, Pipedrive) via their API
- One person can manage 30k leads if the routing is automated — they only touch warm and negotiating ones

**Two channels:**
- Resellers: AI does the scoring and drafting. Human does the sending (Instagram is strict about automation). Review 40 messages each morning, personalise the top 5 if needed, hit send.
- Shops: AI drafts emails. Human makes calls. Agent could send emails via Gmail API. Visit planner makes city trips efficient.

**How I used AI:**
- Claude built the data cleaning logic, scoring weights, and message templates
- Biggest speed-up: designing the dedup key and date parsing — normally fiddly, took minutes
- Where I added judgment: the scoring weights (spend matters more than follower count for B2B), and which stage names to merge (needed to look at the actual data)
- The Anthropic API is wired in to generate fully personalised messages at runtime — the tool sends lead data as context and gets back a specific DM or email
