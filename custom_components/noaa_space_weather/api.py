"""API client for NOAA Space Weather using SWPC public JSON endpoints."""

from __future__ import annotations

import logging
from typing import Any

import async_timeout
from aiohttp import ClientError, ClientSession

_LOGGER = logging.getLogger(__name__)

BASE = "https://services.swpc.noaa.gov/json"

URL_SOLAR_PROB = f"{BASE}/solar_probabilities.json"
URL_KP_1M = f"{BASE}/planetary_k_index_1m.json"

# Spot report (per-region/per-observation rows)
URL_SUNSPOT_REPORT = f"{BASE}/sunspot_report.json"

# True SSN / solar cycle indices (monthly series)
URL_SOLAR_CYCLE_INDICES = f"{BASE}/solar-cycle/observed-solar-cycle-indices.json"

DEFAULT_TIMEOUT_SECONDS = 20


def _as_list(payload: Any) -> list[dict[str, Any]]:
    """Normalize payload to list[dict]."""
    if payload is None:
        return []
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        return [payload]
    return []


class NoaaSpaceWeatherApiClient:
    """Client to fetch NOAA SWPC JSON data."""

    def __init__(self, session: ClientSession) -> None:
        self._session = session

    async def _get_json(self, url: str) -> Any:
        """GET JSON with timeout and sane error handling."""
        try:
            async with async_timeout.timeout(DEFAULT_TIMEOUT_SECONDS):
                resp = await self._session.get(url)
                resp.raise_for_status()
                return await resp.json(content_type=None)
        except (ClientError, TimeoutError) as err:
            raise ConnectionError(f"HTTP error fetching {url}: {err}") from err

    async def async_get_data(self) -> dict[str, Any]:
        """Fetch and normalize data into the structure the integration expects."""
        solar_prob = await self._get_json(URL_SOLAR_PROB)
        kp_1m = await self._get_json(URL_KP_1M)
        sunspot_report = await self._get_json(URL_SUNSPOT_REPORT)
        solar_cycle_indices = await self._get_json(URL_SOLAR_CYCLE_INDICES)

        # Normalize into keys used by sensor.py
        return {
            "probabilities_data": _as_list(solar_prob),
            "kp_index_data": _as_list(kp_1m),
            "sunspot_report_data": _as_list(sunspot_report),
            "solar_cycle_indices_data": _as_list(solar_cycle_indices),
        }
