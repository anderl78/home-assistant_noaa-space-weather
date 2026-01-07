"""Shared entity helpers for NOAA Space Weather."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from . import NoaaSpaceWeatherDataUpdateCoordinator


class NoaaSpaceWeatherBaseEntity(CoordinatorEntity[NoaaSpaceWeatherDataUpdateCoordinator]):
    """Base entity for NOAA Space Weather."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: NoaaSpaceWeatherDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._entry = entry

    @property
    def device_info(self):
        """Return device info for the integration."""
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": "NOAA Space Weather",
            "manufacturer": "NOAA / SWPC",
            "entry_type": "service",
        }
