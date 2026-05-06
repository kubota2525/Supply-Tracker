# Kubota Supply Tracker — Tier 2 Automation

Automated monthly pull of supply data from FRED (Federal Reserve Economic Data),
covering both the Industrial Production Index and the Census M3 Survey for
farm machinery and construction machinery.

The script runs unattended on a monthly schedule, appends new data to either
local CSV files or a Google Sheet, and is idempotent — re-running it never
creates duplicate rows.

---

## What this automates

**Source 1 — Federal Reserve IPI (Industrial Production Index)**
- `IPG333111S` — Farm Machinery and Equipment, NAICS 333111 (compact tractors)
- `IPG33312S` — Construction Machinery, NAICS 33312 (compact construction)

**Source 2 — Census M3 Survey** (mirrored on FRED for clean API access)
- For NAICS 333111 (Farm Machinery): shipments, new orders, unfilled orders, inventories
- For NAICS 333120 (Construction Machinery): shipments, new orders, unfilled orders, inventories

**What's NOT automated:** earnings call processing. That step still requires a
human to paste the transcript into Claude with the standardized prompt, because
earnings releases happen on unpredictable schedules and the human-in-the-loop
review is genuinely valuable.

---

## What you need

- Python 3.9+
- A free FRED API key (takes 30 seconds to register)
- A place to run the script monthly. Three options, in order of recommendation:
  1. **GitHub Actions** — free, runs in the cloud, includes built-in scheduler
  2. **Local cron job** — runs on any always-on Linux/macOS machine
  3. **Manual** — run on your laptop once a month if you prefer

---

## Quick start (5 minutes)

### Step 1: Get a FRED API key

Visit https://fred.stlouisfed.org/docs/api/api_key.html and request a free key.
You'll get an email with a key like `abcdef1234567890abcdef1234567890`.

### Step 2: Install and configure

```bash
git clone <your-repo>          # or copy this folder to your machine
cd supply_tracker_automation
pip install -r requirements.txt

cp .env.example .env
# Edit .env and paste your FRED API key
```

### Step 3: Verify all series IDs are still valid

FRED occasionally renames series. Run this once to confirm everything works:

```bash
export FRED_API_KEY=your_key_here    # or: source .env
python supply_tracker.py --verify
```

You should see `OK` next to all 10 series. If any fail, see "Troubleshooting".

### Step 4: Do a dry run

```bash
python supply_tracker.py --dry-run
```

This fetches the data and prints the latest values without writing anything.
Confirm the numbers look reasonable.

### Step 5: Run for real

```bash
python supply_tracker.py
```

This creates `data/ipi_monthly.csv`, `data/m3_monthly.csv`, and `data/run_log.csv`.
Open them in Excel or your tracker spreadsheet to confirm.

---

## Scheduling: GitHub Actions (recommended)

GitHub Actions is the simplest path because it runs in the cloud — you don't
need a machine that's always on, and the schedule is built in.

### Setup

1. Push this folder to a private GitHub repo.
2. In the repo, go to **Settings → Secrets and variables → Actions → New repository secret**.
3. Name: `FRED_API_KEY`. Value: your FRED API key.
4. The workflow file at `.github/workflows/monthly_pull.yml` is already
   configured to run on the 18th of every month at 14:00 UTC.

### How it works

On the 18th of each month, GitHub Actions automatically:
1. Checks out the repo
2. Installs Python and dependencies
3. Runs `supply_tracker.py`
4. Commits the updated CSV files back to the repo

You can also trigger a run manually from the **Actions** tab using "Run workflow."

### Verifying it runs

After the first scheduled run, check the **Actions** tab. Each run shows
green check or red X, and you can click in to see the logs. You can also
configure GitHub to email you on failure: **Settings → Notifications →
Actions → "Only notify for failed workflows"**.

---

## Scheduling: cron (alternative)

If you have a Linux/macOS machine that's always on (a dealership server, an
old desktop, a Raspberry Pi):

```bash
crontab -e
```

Add this line (adjust the path to where you installed the script):

```cron
# Run on the 18th of each month at 10:00 AM
0 10 18 * * cd /path/to/supply_tracker_automation && /usr/bin/python3 supply_tracker.py >> /var/log/supply_tracker.log 2>&1
```

The script's exit code is non-zero on failure, which most cron mail handlers
will surface to you automatically.

---

## Output formats

### CSV (default)

Three files are appended to the `data/` directory:

**`data/ipi_monthly.csv`**

| Column | Example |
|---|---|
| date | 2026-02-01 |
| category | Compact Tractors |
| series_id | IPG333111S |
| value | 96.1 |
| units | Index 2017=100 |
| fetched_at | 2026-03-18T14:00:15+00:00 |

**`data/m3_monthly.csv`**

| Column | Example |
|---|---|
| date | 2026-01-01 |
| category | Compact Tractors |
| naics | 333111 |
| metric | shipments |
| series_id | A33AVS |
| value_millions | 1234.5 |
| fetched_at | 2026-03-18T14:00:15+00:00 |

**`data/run_log.csv`** records every run for auditing.

### Google Sheets (optional)

To write directly to a Google Sheet instead of (or in addition to) CSV:

1. Edit `config.py` and set `OUTPUT_MODE = "google_sheets"` or `"both"`.
2. Uncomment the `gspread` and `google-auth` lines in `requirements.txt` and reinstall.
3. Create a Google Cloud service account:
   - https://console.cloud.google.com → Create project → IAM & Admin → Service Accounts
   - Create service account → Create key → JSON → download
4. Save the JSON key file somewhere safe and set `GOOGLE_CREDS_PATH=/path/to/key.json`.
5. Create a Google Sheet named exactly `Kubota Supply Tracker` (or whatever
   you set in `config.py`).
6. Share that sheet with the service account email (visible in the JSON key)
   with Editor permissions.

The script will create `IPI Monthly` and `M3 Monthly` tabs automatically on
the first run.

---

## Connecting this to your tracking spreadsheet

The CSV outputs are designed to be imported into the existing
`one_hour_supply_tracker.xlsx` workbook. Two recommended approaches:

**Option A: Power Query (Excel)**
1. Open the tracker workbook → Data tab → Get Data → From File → From CSV.
2. Point at `data/ipi_monthly.csv` and click "Load."
3. Repeat for `data/m3_monthly.csv`.
4. Right-click the imported tables → Refresh to pull latest data.

**Option B: Google Sheets (if using the Google Sheets backend)**
The data lands directly in named tabs. Use `IMPORTRANGE()` or just point
your formulas at the tabs the script writes to.

---

## Monthly review workflow (now ~20 minutes)

With Tier 2 in place, the analyst's monthly job collapses to:

| Step | Time |
|---|---|
| Open tracker workbook, refresh data imports | 2 min |
| Glance at IPI YoY trend and M3 backlog months ratio | 5 min |
| If earnings released this month: paste 4 transcripts into Claude (5 min each) | 0–20 min |
| Write 2-3 sentence brief in Quarterly Summary tab | 5 min |
| **Total** | **12–32 min** |

---

## Troubleshooting

**`FRED_API_KEY not set`**
You haven't exported the env variable. Either run `export FRED_API_KEY=...`
or use a tool like `direnv` to auto-load `.env`.

**`Bad request for series 'X'. Verify the series ID exists`**
FRED renamed or discontinued a series. Visit
`https://fred.stlouisfed.org/series/<SERIES_ID>` to confirm. If the series
moved, search FRED for the new ID and update `config.py`.

**`429 rate limit hit`**
The script automatically retries with exponential backoff. If you see this
repeatedly, you're hitting FRED's 120 requests/minute limit — unlikely with
this script's 10 series, but possible if you're running multiple instances.

**No new rows written, but I expected new data**
This is correct behavior on re-runs in the same month. New data appears
when FRED publishes the next month's value (typically mid-month for IPI,
~6 weeks after the reference month for M3). Run with `--verbose` to see
exactly what dates were fetched.

**Google Sheets: `Spreadsheet not found`**
The service account doesn't have access to the sheet. In the sheet, click
Share → paste the service account email (from the JSON key, looks like
`name@project-id.iam.gserviceaccount.com`) → Editor.

---

## File structure

```
supply_tracker_automation/
├── README.md                    ← this file
├── config.py                    ← all FRED series IDs (edit if FRED renames any)
├── fred_client.py               ← FRED API wrapper with retry logic
├── output_writers.py            ← CSV and Google Sheets backends
├── supply_tracker.py            ← main entry point
├── requirements.txt             ← Python dependencies
├── .env.example                 ← template for your secrets
├── .gitignore                   ← keeps secrets out of git
├── .github/workflows/
│   └── monthly_pull.yml         ← GitHub Actions schedule
└── data/                        ← created on first run; CSV outputs go here
    ├── ipi_monthly.csv
    ├── m3_monthly.csv
    └── run_log.csv
```

---

## Initial backfill

To populate historical data on first run, fetch more than the default 6 months:

```bash
python supply_tracker.py --months 36
```

This pulls the last 3 years of data, giving you proper YoY comparison
context from day one.
