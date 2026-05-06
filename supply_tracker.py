#!/usr/bin/env python3
"""
Kubota Supply Tracker — monthly data pull.

Pulls the latest IPI and Census M3 data from FRED and appends to either
local CSV files or a Google Sheet. Designed to run unattended as a cron
job or GitHub Actions workflow.

Usage:
    python supply_tracker.py
    python supply_tracker.py --months 12   # backfill more history
    python supply_tracker.py --dry-run     # don't write, just print summary
    python supply_tracker.py --verify      # verify all configured series IDs exist

Environment variables:
    FRED_API_KEY         (required) Your FRED API key.
    GOOGLE_CREDS_PATH    (optional) Path to Google service account JSON,
                         only needed if OUTPUT_MODE includes "google_sheets".
"""

import argparse
import logging
import sys
from datetime import datetime, timezone
from typing import Optional

import config
from fred_client import FredClient, FredAPIError
import output_writers as writers


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def fetch_ipi(client: FredClient, months: int) -> list[dict]:
    """Fetch IPI observations for both configured categories."""
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = []
    for key, meta in config.IPI_SERIES.items():
        series_id = meta["series_id"]
        logging.info("Fetching IPI series %s (%s)", series_id, meta["category"])
        observations = client.get_recent_observations(series_id, months=months)
        for obs in observations:
            if obs["value"] is None:
                continue
            rows.append({
                "date": obs["date"],
                "category": meta["category"],
                "series_id": series_id,
                "value": obs["value"],
                "units": meta["units"],
                "fetched_at": fetched_at,
            })
    logging.info("Fetched %d IPI observations total", len(rows))
    return rows


def fetch_m3(client: FredClient, months: int) -> list[dict]:
    """Fetch M3 observations for all configured metrics across both NAICS codes."""
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = []
    for industry_key, industry in config.M3_SERIES.items():
        for metric_name, series_id in industry["metrics"].items():
            logging.info(
                "Fetching M3 series %s (%s / %s)",
                series_id, industry["category"], metric_name,
            )
            try:
                observations = client.get_recent_observations(
                    series_id, months=months
                )
            except FredAPIError as exc:
                logging.warning(
                    "Skipping series %s — not available: %s", series_id, exc,
                )
                continue
            for obs in observations:
                if obs["value"] is None:
                    continue
                rows.append({
                    "date": obs["date"],
                    "category": industry["category"],
                    "naics": industry["naics"],
                    "metric": metric_name,
                    "series_id": series_id,
                    "value_millions": obs["value"],
                    "fetched_at": fetched_at,
                })
    logging.info("Fetched %d M3 observations total", len(rows))
    return rows


def verify_all_series(client: FredClient) -> int:
    """Test every configured series ID by fetching one observation each."""
    all_ids = []
    for meta in config.IPI_SERIES.values():
        all_ids.append(("IPI", meta["category"], meta["series_id"]))
    for industry in config.M3_SERIES.values():
        for metric, series_id in industry["metrics"].items():
            all_ids.append(("M3", f"{industry['category']} / {metric}", series_id))

    print(f"Verifying {len(all_ids)} configured FRED series...")
    print("-" * 70)
    failed = []
    for source, label, series_id in all_ids:
        try:
            obs = client.get_recent_observations(series_id, months=2)
            if obs and obs[-1]["value"] is not None:
                latest = obs[-1]
                print(f"  OK   {source:5} {series_id:12} {label}")
                print(f"           latest: {latest['date']} = {latest['value']}")
            else:
                print(f"  WARN {source:5} {series_id:12} {label} (no recent values)")
        except FredAPIError as exc:
            print(f"  FAIL {source:5} {series_id:12} {label}")
            print(f"           {exc}")
            failed.append(series_id)
    print("-" * 70)
    if failed:
        print(f"\n{len(failed)} series failed: {', '.join(failed)}")
        print("Update config.py with the correct series IDs.")
        return 1
    print(f"\nAll {len(all_ids)} series verified.")
    return 0


def run(months: int, dry_run: bool) -> int:
    """Main pipeline."""
    try:
        client = FredClient()
    except RuntimeError as exc:
        logging.error(str(exc))
        return 2

    ipi_rows = []
    m3_rows = []
    error_messages = []

    try:
        ipi_rows = fetch_ipi(client, months)
    except FredAPIError as exc:
        logging.error("IPI fetch failed: %s", exc)
        error_messages.append(f"IPI: {exc}")

    try:
        m3_rows = fetch_m3(client, months)
    except FredAPIError as exc:
        logging.error("M3 fetch failed: %s", exc)
        error_messages.append(f"M3: {exc}")

    if dry_run:
        logging.info("--dry-run set; not writing output.")
        print(f"\nWould write {len(ipi_rows)} IPI rows and {len(m3_rows)} M3 rows.")
        if ipi_rows:
            print("\nLatest IPI values:")
            latest_by_series = {}
            for r in ipi_rows:
                cur = latest_by_series.get(r["series_id"])
                if cur is None or r["date"] > cur["date"]:
                    latest_by_series[r["series_id"]] = r
            for r in latest_by_series.values():
                print(f"  {r['series_id']:12} {r['date']:10} {r['value']:>10}  {r['category']}")
        if m3_rows:
            print("\nLatest M3 values ($M):")
            latest_by_series = {}
            for r in m3_rows:
                cur = latest_by_series.get(r["series_id"])
                if cur is None or r["date"] > cur["date"]:
                    latest_by_series[r["series_id"]] = r
            for r in latest_by_series.values():
                print(f"  {r['series_id']:10} {r['date']:10} "
                      f"{r['value_millions']:>10,.0f}  {r['category']} / {r['metric']}")
        return 0

    ipi_written = 0
    m3_written = 0
    mode = config.OUTPUT_MODE.lower()

    if mode in ("csv", "both"):
        try:
            ipi_written += writers.write_ipi_csv(ipi_rows)
            m3_written += writers.write_m3_csv(m3_rows)
        except Exception as exc:
            logging.exception("CSV write failed")
            error_messages.append(f"CSV: {exc}")

    if mode in ("google_sheets", "both"):
        try:
            ipi_gs, m3_gs = writers.write_to_google_sheets(ipi_rows, m3_rows)
            # If we wrote to both backends, count CSV writes as canonical.
            if mode == "google_sheets":
                ipi_written = ipi_gs
                m3_written = m3_gs
        except Exception as exc:
            logging.exception("Google Sheets write failed")
            error_messages.append(f"Google Sheets: {exc}")

    status = "success" if not error_messages else "partial_failure"
    if mode in ("csv", "both"):
        writers.write_run_log_csv(
            status=status,
            ipi_count=ipi_written,
            m3_count=m3_written,
            errors="; ".join(error_messages),
        )

    logging.info(
        "Run complete. status=%s ipi_rows=%d m3_rows=%d",
        status, ipi_written, m3_written,
    )
    return 0 if status == "success" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--months", type=int, default=config.MONTHS_OF_HISTORY,
        help=f"Months of history to fetch (default: {config.MONTHS_OF_HISTORY}).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Fetch and print, but don't write to outputs.",
    )
    parser.add_argument(
        "--verify", action="store_true",
        help="Verify all configured FRED series IDs exist and have data.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable debug logging.",
    )
    args = parser.parse_args()
    setup_logging(args.verbose)

    if args.verify:
        try:
            client = FredClient()
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        return verify_all_series(client)

    return run(months=args.months, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
