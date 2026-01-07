"""Custom integration to integrate NOAA Space Weather with Home Assistant."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import NoaaSpaceWeatherApiClient
from .const import DOMAIN, PLATFORMS, SCAN_INTERVAL_MINUTES, STARTUP_MESSAGE

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=SCAN_INTERVAL_MINUTES)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the integration (YAML not supported, but return True)."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up NOAA Space Weather from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    _LOGGER.info(STARTUP_MESSAGE)

    client = NoaaSpaceWeatherApiClient()
    coordinator = NoaaSpaceWeatherDataUpdateCoordinator(hass, client=client)

    # Home Assistant standard: do a first refresh here and raise ConfigEntryNotReady on failures
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        # This will cause HA to retry later instead of "half-loading" the integration.
        raise ConfigEntryNotReady from err

    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Forward platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register update listener exactly once
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


class NoaaSpaceWeatherDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to manage fetching NOAA Space Weather data."""

    def __init__(self, hass: HomeAssistant, client: NoaaSpaceWeatherApiClient) -> None:
        """Initialize."""
        self.api = client
        super().__init__(
            hass=hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API."""
        try:
            return await self.api.async_get_data()
        except Exception as err:
            # Mark update failed; entities will keep old state + show unavailable if needed
            raise UpdateFailed(str(err)) from err


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload a config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
