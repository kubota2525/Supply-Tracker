"""
FRED API client.

Wraps the Federal Reserve Economic Data API with retry logic, error handling,
and a clean Python interface. Documentation: https://fred.stlouisfed.org/docs/api/fred/

The API key is loaded from the FRED_API_KEY environment variable. Get a free
key at https://fred.stlouisfed.org/docs/api/api_key.html.
"""

import os
import time
import logging
from datetime import datetime, timedelta
from typing import Optional

import requests

import config

logger = logging.getLogger(__name__)


class FredAPIError(Exception):
    """Raised when the FRED API returns an error response."""


class FredClient:
    """Minimal FRED API client for fetching observation data."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("FRED_API_KEY")
        if not self.api_key:
            raise RuntimeError(
                "FRED_API_KEY not set. Get a free key at "
                "https://fred.stlouisfed.org/docs/api/api_key.html "
                "and export it as FRED_API_KEY (or add to .env file)."
            )

    def get_observations(
        self,
        series_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> list[dict]:
        """
        Fetch observations for a FRED series.

        Args:
            series_id: FRED series ID (e.g., "IPG333111S").
            start_date: ISO format YYYY-MM-DD (optional).
            end_date: ISO format YYYY-MM-DD (optional).

        Returns:
            List of dicts with keys "date" (str) and "value" (float or None).
            Missing values (FRED uses ".") are returned as None.

        Raises:
            FredAPIError: On non-recoverable API errors.
        """
        url = f"{config.FRED_BASE_URL}/series/observations"
        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "sort_order": "asc",
        }
        if start_date:
            params["observation_start"] = start_date
        if end_date:
            params["observation_end"] = end_date

        for attempt in range(1, config.MAX_RETRIES + 1):
            try:
                response = requests.get(
                    url, params=params, timeout=config.REQUEST_TIMEOUT
                )
                if response.status_code == 200:
                    data = response.json()
                    return self._parse_observations(data, series_id)
                if response.status_code == 400:
                    raise FredAPIError(
                        f"Bad request for series '{series_id}'. "
                        f"Verify the series ID exists at "
                        f"https://fred.stlouisfed.org/series/{series_id}. "
                        f"Response: {response.text[:200]}"
                    )
                if response.status_code == 429:
                    wait = 2 ** attempt
                    logger.warning(
                        "FRED rate limit hit, sleeping %ds (attempt %d/%d)",
                        wait, attempt, config.MAX_RETRIES,
                    )
                    time.sleep(wait)
                    continue
                logger.warning(
                    "FRED returned %d for %s (attempt %d/%d): %s",
                    response.status_code, series_id, attempt,
                    config.MAX_RETRIES, response.text[:200],
                )
            except requests.RequestException as exc:
                logger.warning(
                    "FRED request failed for %s (attempt %d/%d): %s",
                    series_id, attempt, config.MAX_RETRIES, exc,
                )
            time.sleep(2 ** attempt)

        raise FredAPIError(
            f"Failed to fetch series '{series_id}' after "
            f"{config.MAX_RETRIES} attempts."
        )

    def get_recent_observations(
        self, series_id: str, months: int = 6
    ) -> list[dict]:
        """Fetch the last `months` months of observations."""
        end = datetime.utcnow().date()
        start = end - timedelta(days=months * 32)  # generous window
        return self.get_observations(
            series_id,
            start_date=start.isoformat(),
            end_date=end.isoformat(),
        )

    @staticmethod
    def _parse_observations(data: dict, series_id: str) -> list[dict]:
        """Convert FRED observation dicts to clean Python types."""
        observations = data.get("observations", [])
        result = []
        for obs in observations:
            raw_value = obs.get("value", ".")
            value = None if raw_value in (".", "") else float(raw_value)
            result.append({"date": obs["date"], "value": value})
        if not result:
            logger.warning("No observations returned for %s", series_id)
        return result
