"""Constants for the NOAA Space Weather integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "noaa_space_weather"

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.IMAGE]

STARTUP_MESSAGE = "NOAA Space Weather custom integration loaded"

# Update interval for coordinator
SCAN_INTERVAL_MINUTES = 10
