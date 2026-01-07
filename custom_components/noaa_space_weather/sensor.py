"""Sensor platform for NOAA Space Weather."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorDeviceClass,
    SensorStateClass,
)

from .const import DOMAIN
from .entity import NoaaSpaceWeatherBaseEntity
from . import NoaaSpaceWeatherDataUpdateCoordinator


def _safe_float(value: Any) -> float | None:
    """Convert to float safely."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    """Convert to int safely."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _get_first(d: dict[str, Any], key: str) -> dict[str, Any]:
    """Get first element of a list stored in d[key], or {}."""
    val = d.get(key)
    if isinstance(val, list) and val:
        first = val[0]
        if isinstance(first, dict):
            return first
    return {}


def _get_value(path_getter: Callable[[dict[str, Any]], Any], data: dict[str, Any]) -> Any:
    """Apply getter defensively."""
    try:
        return path_getter(data)
    except Exception:
        return None


@dataclass(frozen=True, kw_only=True)
class NoaaSpaceWeatherSensorEntityDescription(SensorEntityDescription):
    """Describes NOAA Space Weather sensor entity."""

    value_fn: Callable[[dict[str, Any]], Any]


SENSORS: tuple[NoaaSpaceWeatherSensorEntityDescription, ...] = (
    # --- Solar activity / flare probabilities (typically in probabilities_data[0]) ---
    NoaaSpaceWeatherSensorEntityDescription(
        key="c_class_1_day",
        name="C-class flare probability (1 day)",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _safe_float(_get_first(data, "probabilities_data").get("c_class_1_day")),
    ),
    NoaaSpaceWeatherSensorEntityDescription(
        key="m_class_1_day",
        name="M-class flare probability (1 day)",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _safe_float(_get_first(data, "probabilities_data").get("m_class_1_day")),
    ),
    NoaaSpaceWeatherSensorEntityDescription(
        key="x_class_1_day",
        name="X-class flare probability (1 day)",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _safe_float(_get_first(data, "probabilities_data").get("x_class_1_day")),
    ),
    NoaaSpaceWeatherSensorEntityDescription(
        key="c_class_2_day",
        name="C-class flare probability (2 days)",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _safe_float(_get_first(data, "probabilities_data").get("c_class_2_day")),
    ),
    NoaaSpaceWeatherSensorEntityDescription(
        key="m_class_2_day",
        name="M-class flare probability (2 days)",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _safe_float(_get_first(data, "probabilities_data").get("m_class_2_day")),
    ),
    NoaaSpaceWeatherSensorEntityDescription(
        key="x_class_2_day",
        name="X-class flare probability (2 days)",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _safe_float(_get_first(data, "probabilities_data").get("x_class_2_day")),
    ),
    # --- Planetary K-index (often kp_index_data[0]) ---
    NoaaSpaceWeatherSensorEntityDescription(
        key="planetary_k_index",
        name="Planetary K-index",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _safe_float(_get_first(data, "kp_index_data").get("planetary_k_index")),
    ),
    # --- Sunspot number (often solar_cycle_data[0]) ---
    NoaaSpaceWeatherSensorEntityDescription(
        key="sunspot_number",
        name="Sunspot number",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _safe_int(_get_first(data, "solar_cycle_data").get("sunspot_number")),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up NOAA Space Weather sensors from a config entry."""
    coordinator: NoaaSpaceWeatherDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[NoaaSpaceWeatherSensor] = [
        NoaaSpaceWeatherSensor(coordinator, entry, description)
        for description in SENSORS
    ]
    async_add_entities(entities)


class NoaaSpaceWeatherSensor(NoaaSpaceWeatherBaseEntity, SensorEntity):
    """NOAA Space Weather sensor."""

    entity_description: NoaaSpaceWeatherSensorEntityDescription

    def __init__(
        self,
        coordinator: NoaaSpaceWeatherDataUpdateCoordinator,
        entry: ConfigEntry,
        description: NoaaSpaceWeatherSensorEntityDescription,
    ) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry)
        self.entity_description = description

        # Stable unique ID per config entry + sensor key
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"

        # Nice entity_id naming; HA will handle final formatting
        self._attr_translation_key = description.key

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        data = self.coordinator.data or {}
        return _get_value(self.entity_description.value_fn, data)
