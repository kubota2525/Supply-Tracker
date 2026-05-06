"""
Configuration for the Kubota Supply Tracker automation.

All FRED series IDs below were verified against fred.stlouisfed.org.
If FRED ever renames a series, update the ID here — this is the only file
you should need to touch to fix series-level breakage.
"""

# ---------------------------------------------------------------------------
# FRED series — Industrial Production Index (Source 1)
# ---------------------------------------------------------------------------
# These indices are published monthly by the Federal Reserve Board (G.17 release).
# Base year: 2017 = 100. Seasonally adjusted.

IPI_SERIES = {
    "compact_tractors": {
        "series_id": "IPG333111S",
        "label": "Industrial Production: Farm Machinery and Equipment (NAICS 333111)",
        "category": "Compact Tractors",
        "units": "Index 2017=100",
    },
    "compact_construction": {
        "series_id": "IPG33312S",
        "label": "Industrial Production: Construction Machinery (NAICS 33312)",
        "category": "Compact Construction",
        "units": "Index 2017=100",
    },
}

# ---------------------------------------------------------------------------
# FRED series — Census M3 Survey (Source 2)
# ---------------------------------------------------------------------------
# Series naming convention:
#   Prefix: A = Seasonally Adjusted, U = Not Seasonally Adjusted
#   Middle: 33A = Farm Machinery (NAICS 333111), 33C = Construction Machinery (NAICS 333120)
#   Suffix: VS = Value of Shipments, NO = New Orders,
#           UO = Unfilled Orders, TI = Total Inventories
# All values are in millions of dollars.

M3_SERIES = {
    "farm_machinery": {
        "naics": "333111",
        "category": "Compact Tractors",
        "label": "Farm Machinery and Equipment Manufacturing",
        "metrics": {
            "shipments": "A33AVS",
            "inventories": "A33ATI",
        },
    },
    "construction_machinery": {
        "naics": "333120",
        "category": "Compact Construction",
        "label": "Construction Machinery Manufacturing",
        "metrics": {
            "shipments": "A33CVS",
            "new_orders": "A33CNO",
            "unfilled_orders": "A33CUO",
            "inventories": "A33CTI",
        },
    },
}

# ---------------------------------------------------------------------------
# Output configuration
# ---------------------------------------------------------------------------
# OUTPUT_MODE controls where data is written. Options:
#   "csv"           — Append to local CSV files (default, simplest)
#   "google_sheets" — Append to a Google Sheet (requires service account)
#   "both"          — Write to CSV and Google Sheets

OUTPUT_MODE = "csv"

# CSV output paths (used when OUTPUT_MODE includes "csv")
CSV_OUTPUT_DIR = "data"
CSV_IPI_FILENAME = "ipi_monthly.csv"
CSV_M3_FILENAME = "m3_monthly.csv"
CSV_RUN_LOG_FILENAME = "run_log.csv"

# Google Sheets configuration (used when OUTPUT_MODE includes "google_sheets")
# The service account JSON key must be at the path in GOOGLE_CREDS_PATH
# and the service account email must have edit access to the target sheet.
GOOGLE_SHEET_NAME = "Kubota Supply Tracker"
GOOGLE_SHEET_IPI_TAB = "IPI Monthly"
GOOGLE_SHEET_M3_TAB = "M3 Monthly"

# ---------------------------------------------------------------------------
# Behavior
# ---------------------------------------------------------------------------
# How many months of history to fetch on each run. The script de-duplicates
# against existing rows, so a 6-month window is plenty to backfill any
# revisions FRED publishes to recent data.
MONTHS_OF_HISTORY = 6

# FRED API base URL
FRED_BASE_URL = "https://api.stlouisfed.org/fred"

# Request timeout (seconds)
REQUEST_TIMEOUT = 30

# Maximum retry attempts for transient FRED errors
MAX_RETRIES = 3
