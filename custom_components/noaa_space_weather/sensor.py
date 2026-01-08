"""Sensor platform for NOAA Space Weather."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import NoaaSpaceWeatherDataUpdateCoordinator
from .const import DOMAIN
from .entity import NoaaSpaceWeatherBaseEntity


ICON_FLARE = "mdi:sun-wireless-outline"
ICON_SUNNY = "mdi:weather-sunny"


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    if isinstance(value, dict):
        return [value]
    return []


def _latest_valid_monthly_value(
    items: list[dict[str, Any]],
    value_key: str,
    time_key: str = "time-tag",
    invalid_value: float = -1.0,
) -> float | None:
    """Find the latest entry where value_key is not invalid_value (-1.0)."""
    if not items:
        return None

    for rec in sorted(items, key=lambda x: str(x.get(time_key, "")), reverse=True):
        f = _safe_float(rec.get(value_key))
        if f is None:
            continue
        if f == float(invalid_value):
            continue
        return f

    return None


def _get_latest_by_time_tag(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the item with the greatest time_tag (string compare works for ISO timestamps)."""
    if not items:
        return {}
    return max(items, key=lambda x: str(x.get("time_tag", "")))


def _sum_numspot_latest_observation(items: list[dict[str, Any]]) -> int | None:
    """Sum Numspot for all records that share the latest time_tag."""
    if not items:
        return None
    latest_tag = str(max(items, key=lambda x: str(x.get("time_tag", ""))).get("time_tag", ""))
    if not latest_tag:
        return None

    total = 0
    found_any = False
    for rec in items:
        if str(rec.get("time_tag", "")) != latest_tag:
            continue
        n = _safe_int(rec.get("Numspot"))
        if n is None:
            continue
        total += n
        found_any = True

    return total if found_any else None


def _get_first(d: dict[str, Any], key: str) -> dict[str, Any]:
    val = d.get(key)
    if isinstance(val, list) and val:
        first = val[0]
        if isinstance(first, dict):
            return first
    return {}


def _get_value(path_getter: Callable[[dict[str, Any]], Any], data: dict[str, Any]) -> Any:
    try:
        return path_getter(data)
    except Exception:
        return None


@dataclass(frozen=True, kw_only=True)
class NoaaSpaceWeatherSensorEntityDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any]


SENSORS: tuple[NoaaSpaceWeatherSensorEntityDescription, ...] = (
    # --- Solar flare probabilities ---
    NoaaSpaceWeatherSensorEntityDescription(
        key="c_class_1_day",
        name="C-class flare probability (1 day)",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        icon=ICON_FLARE,
        value_fn=lambda data: _safe_float(_get_first(data, "probabilities_data").get("c_class_1_day")),
    ),
    NoaaSpaceWeatherSensorEntityDescription(
        key="m_class_1_day",
        name="M-class flare probability (1 day)",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        icon=ICON_FLARE,
        value_fn=lambda data: _safe_float(_get_first(data, "probabilities_data").get("m_class_1_day")),
    ),
    NoaaSpaceWeatherSensorEntityDescription(
        key="x_class_1_day",
        name="X-class flare probability (1 day)",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        icon=ICON_FLARE,
        value_fn=lambda data: _safe_float(_get_first(data, "probabilities_data").get("x_class_1_day")),
    ),
    NoaaSpaceWeatherSensorEntityDescription(
        key="c_class_2_day",
        name="C-class flare probability (2 days)",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        icon=ICON_FLARE,
        value_fn=lambda data: _safe_float(_get_first(data, "probabilities_data").get("c_class_2_day")),
    ),
    NoaaSpaceWeatherSensorEntityDescription(
        key="m_class_2_day",
        name="M-class flare probability (2 days)",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        icon=ICON_FLARE,
        value_fn=lambda data: _safe_float(_get_first(data, "probabilities_data").get("m_class_2_day")),
    ),
    NoaaSpaceWeatherSensorEntityDescription(
        key="x_class_2_day",
        name="X-class flare probability (2 days)",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        icon=ICON_FLARE,
        value_fn=lambda data: _safe_float(_get_first(data, "probabilities_data").get("x_class_2_day")),
    ),

    # --- Planetary K-index ---
    NoaaSpaceWeatherSensorEntityDescription(
        key="planetary_k_index",
        name="Planetary K-index",
        state_class=SensorStateClass.MEASUREMENT,
        icon=ICON_SUNNY,
        value_fn=lambda data: _safe_float(
            _get_latest_by_time_tag(_as_list_of_dicts(data.get("kp_index_data"))).get("kp_index")
        ),
    ),

    # --- True SSN (monthly) ---
    NoaaSpaceWeatherSensorEntityDescription(
        key="sunspot_number",
        name="Sunspot number (SSN, monthly)",
        state_class=SensorStateClass.MEASUREMENT,
        icon=ICON_SUNNY,
        value_fn=lambda data: _latest_valid_monthly_value(
            _as_list_of_dicts(data.get("solar_cycle_indices_data")),
            "ssn",
        ),
    ),
    NoaaSpaceWeatherSensorEntityDescription(
        key="sunspot_smoothed",
        name="Sunspot number (smoothed, monthly)",
        state_class=SensorStateClass.MEASUREMENT,
        icon=ICON_SUNNY,
        value_fn=lambda data: _latest_valid_monthly_value(
            _as_list_of_dicts(data.get("solar_cycle_indices_data")),
            "smoothed_ssn",
        ),
    ),

    # --- Extra: spot-count from sunspot_report.json ---
    NoaaSpaceWeatherSensorEntityDescription(
        key="sunspot_spot_count",
        name="Sunspot spots (latest observation)",
        state_class=SensorStateClass.MEASUREMENT,
        icon=ICON_SUNNY,
        value_fn=lambda data: _sum_numspot_latest_observation(
            _as_list_of_dicts(data.get("sunspot_report_data"))
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: NoaaSpaceWeatherDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [NoaaSpaceWeatherSensor(coordinator, entry, description) for description in SENSORS]
    )


class NoaaSpaceWeatherSensor(NoaaSpaceWeatherBaseEntity, SensorEntity):
    entity_description: NoaaSpaceWeatherSensorEntityDescription

    def __init__(
        self,
        coordinator: NoaaSpaceWeatherDataUpdateCoordinator,
        entry: ConfigEntry,
        description: NoaaSpaceWeatherSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator, entry)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_translation_key = description.key

    @property
    def native_value(self) -> Any:
        data = self.coordinator.data or {}
        return _get_value(self.entity_description.value_fn, data)
