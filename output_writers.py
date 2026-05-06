"""
Output writers for IPI and M3 data.

Two backends are supported:
  - CSV: appends to local CSV files (default; no setup required beyond
    write access to the data/ directory).
  - Google Sheets: appends to a named Google Sheet (requires a service
    account key; see SETUP_GUIDE.md).

Both backends are idempotent — running the script multiple times in the
same month will not create duplicate rows. Data is keyed on (date, series).
"""

import csv
import logging
import os
from pathlib import Path
from typing import Optional

import config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CSV writer
# ---------------------------------------------------------------------------

IPI_HEADERS = ["date", "category", "series_id", "value", "units", "fetched_at"]
M3_HEADERS = [
    "date", "category", "naics", "metric", "series_id", "value_millions",
    "fetched_at",
]
RUN_LOG_HEADERS = [
    "run_at", "status", "ipi_rows_added", "m3_rows_added", "errors",
]


def _ensure_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _read_existing_keys(path: Path, key_columns: list[str]) -> set[tuple]:
    """Read existing rows and return a set of unique key tuples."""
    if not path.exists():
        return set()
    keys = set()
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                keys.add(tuple(row[col] for col in key_columns))
            except KeyError:
                # Older file with different columns; treat as no existing keys
                return set()
    return keys


def _append_csv(path: Path, headers: list[str], rows: list[dict]) -> int:
    """Append rows to a CSV file, writing the header if the file is new."""
    _ensure_dir(path)
    write_header = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        if write_header:
            writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def write_ipi_csv(rows: list[dict]) -> int:
    """Append IPI rows to the IPI CSV, deduplicating by (date, series_id)."""
    path = Path(config.CSV_OUTPUT_DIR) / config.CSV_IPI_FILENAME
    existing = _read_existing_keys(path, ["date", "series_id"])
    new_rows = [
        r for r in rows
        if (r["date"], r["series_id"]) not in existing
    ]
    if not new_rows:
        logger.info("No new IPI rows to write (all dates already present).")
        return 0
    written = _append_csv(path, IPI_HEADERS, new_rows)
    logger.info("Wrote %d IPI rows to %s", written, path)
    return written


def write_m3_csv(rows: list[dict]) -> int:
    """Append M3 rows to the M3 CSV, deduplicating by (date, series_id)."""
    path = Path(config.CSV_OUTPUT_DIR) / config.CSV_M3_FILENAME
    existing = _read_existing_keys(path, ["date", "series_id"])
    new_rows = [
        r for r in rows
        if (r["date"], r["series_id"]) not in existing
    ]
    if not new_rows:
        logger.info("No new M3 rows to write (all dates already present).")
        return 0
    written = _append_csv(path, M3_HEADERS, new_rows)
    logger.info("Wrote %d M3 rows to %s", written, path)
    return written


def write_run_log_csv(
    status: str, ipi_count: int, m3_count: int, errors: str = ""
) -> None:
    """Append a single row to the run log CSV."""
    from datetime import datetime
    path = Path(config.CSV_OUTPUT_DIR) / config.CSV_RUN_LOG_FILENAME
    row = {
        "run_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "status": status,
        "ipi_rows_added": ipi_count,
        "m3_rows_added": m3_count,
        "errors": errors,
    }
    _append_csv(path, RUN_LOG_HEADERS, [row])


# ---------------------------------------------------------------------------
# Google Sheets writer (optional)
# ---------------------------------------------------------------------------
# This backend is opt-in. It requires the gspread + google-auth packages and
# a service account key file. See SETUP_GUIDE.md for the one-time setup steps.

def write_to_google_sheets(
    ipi_rows: list[dict], m3_rows: list[dict]
) -> tuple[int, int]:
    """
    Append IPI and M3 rows to a Google Sheet.

    The sheet is identified by config.GOOGLE_SHEET_NAME and must already
    exist. The service account email (in the credentials JSON) must have
    edit access to the sheet.

    Returns:
        Tuple of (ipi_rows_written, m3_rows_written).
    """
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError as exc:
        raise RuntimeError(
            "Google Sheets output requires gspread and google-auth. "
            "Install with: pip install gspread google-auth"
        ) from exc

    creds_path = os.environ.get("GOOGLE_CREDS_PATH")
    if not creds_path or not Path(creds_path).exists():
        raise RuntimeError(
            "GOOGLE_CREDS_PATH not set or file not found. "
            "Set it to the path of your service account JSON key."
        )

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
    client = gspread.authorize(creds)
    sheet = client.open(config.GOOGLE_SHEET_NAME)

    ipi_count = _append_to_sheet_tab(
        sheet, config.GOOGLE_SHEET_IPI_TAB, IPI_HEADERS, ipi_rows
    )
    m3_count = _append_to_sheet_tab(
        sheet, config.GOOGLE_SHEET_M3_TAB, M3_HEADERS, m3_rows
    )
    return ipi_count, m3_count


def _append_to_sheet_tab(
    sheet, tab_name: str, headers: list[str], rows: list[dict]
) -> int:
    """Append rows to a named tab, deduplicating against existing values."""
    try:
        worksheet = sheet.worksheet(tab_name)
    except Exception:
        worksheet = sheet.add_worksheet(title=tab_name, rows=1000, cols=20)
        worksheet.append_row(headers)

    existing = worksheet.get_all_records()
    existing_keys = {(str(r.get("date", "")), str(r.get("series_id", "")))
                     for r in existing}
    new_rows = [
        r for r in rows
        if (str(r["date"]), str(r["series_id"])) not in existing_keys
    ]
    if not new_rows:
        logger.info("No new rows to write to tab %s", tab_name)
        return 0

    values = [[row.get(h, "") for h in headers] for row in new_rows]
    worksheet.append_rows(values, value_input_option="USER_ENTERED")
    logger.info("Wrote %d rows to Google Sheets tab %s", len(new_rows), tab_name)
    return len(new_rows)
