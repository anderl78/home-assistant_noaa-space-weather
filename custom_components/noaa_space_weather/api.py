"""API client for NOAA Space Weather.

This integration uses swpclib to retrieve NOAA SWPC data.
"""

from __future__ import annotations

import logging
from typing import Any

import async_timeout
from swpclib import Runner

_LOGGER = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 20


class NoaaSpaceWeatherApiClient:
    """Client to communicate with NOAA Space Weather data source."""

    def __init__(self) -> None:
        """Initialize the client."""
        self._swpc = Runner()

    async def async_get_data(self) -> dict[str, Any]:
        """Fetch data from NOAA SWPC via swpclib.

        Raises exceptions on failure so the coordinator can mark the update as failed
        and Home Assistant can retry appropriately.
        """
        # swpclib returns an awaitable for get_standard()
        try:
            async with async_timeout.timeout(DEFAULT_TIMEOUT_SECONDS):
                data = await self._swpc.get_standard()
        except Exception as err:
            _LOGGER.warning("Failed to fetch NOAA Space Weather data: %s", err)
            raise

        if not isinstance(data, dict):
            # Be strict: coordinator expects a dict-like payload.
            raise ValueError("Unexpected payload type from swpclib (expected dict)")

        return data
