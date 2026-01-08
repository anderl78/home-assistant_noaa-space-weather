"""Image platform for NOAA Space Weather (animated SUVI PNG sequences).

SWPC provides directories with many PNG frames + a latest.png.
We animate by cycling through the most recent N frames and updating image_last_updated
so the frontend fetches the new image.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Final

import async_timeout
from aiohttp import ClientError, ClientSession

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import DOMAIN

# --- Configuration knobs (safe defaults) ---
FRAME_COUNT: Final[int] = 12              # how many recent frames to include in the loop
FRAME_ADVANCE_SECONDS: Final[int] = 12    # animation speed
REFRESH_LIST_MINUTES: Final[int] = 15     # how often to refresh directory listing
TIMEOUT_SECONDS: Final[int] = 20

BASE: Final[str] = "https://services.swpc.noaa.gov/images/animations/suvi"
BANDS: Final[tuple[str, ...]] = ("094", "131", "171", "195", "284", "304", "map")
PATHS: Final[tuple[str, ...]] = ("primary", "secondary")

# Extract *.png filenames from the simple HTML directory listing
PNG_HREF_RE: Final[re.Pattern[str]] = re.compile(r'href="([^"]+\.png)"', re.IGNORECASE)


@dataclass(frozen=True)
class _SuviSource:
    path: str   # "primary" or "secondary"
    band: str   # "094", ..., "map"

    @property
    def dir_url(self) -> str:
        return f"{BASE}/{self.path}/{self.band}/"

    @property
    def object_id(self) -> str:
        # Keep your legacy-style IDs
        return f"noaasw_animated_suvi_{self.path}_{self.band}_angstroms"

    @property
    def name(self) -> str:
        return f"SUVI {self.path} {self.band} (animated)"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SUVI animated image entities (primary+secondary for all bands)."""
    session = async_get_clientsession(hass)

    entities: list[NoaaSuviAnimatedPngImage] = []
    for p in PATHS:
        for b in BANDS:
            src = _SuviSource(path=p, band=b)
            entities.append(
                NoaaSuviAnimatedPngImage(
                    hass=hass,
                    entry_id=entry.entry_id,
                    session=session,
                    source=src,
                )
            )

    async_add_entities(entities)


class NoaaSuviAnimatedPngImage(ImageEntity):
    """Animated ImageEntity backed by SWPC PNG frames."""

    _attr_content_type = "image/png"
    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        session: ClientSession,
        source: _SuviSource,
    ) -> None:
        # HA 12/2025 expects hass in ImageEntity.__init__
        super().__init__(hass)

        self._entry_id = entry_id
        self._session = session
        self._source = source

        # Stable identity
        self._attr_unique_id = f"{entry_id}_{source.object_id}"
        self._attr_name = source.name

        # Force stable entity_id via object_id (Entity Registry will respect unique_id)
        self._attr_object_id = source.object_id

        # Frame state
        self._frames: list[str] = []
        self._frame_idx: int = 0

        # Cache for current frame
        self._current_url: str | None = None
        self._current_bytes: bytes | None = None

        # Cache-buster so frontend reloads the image
        self._attr_image_last_updated = dt_util.utcnow()

        self._unsub_advance = None
        self._unsub_refresh = None

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": "NOAA Space Weather",
            "manufacturer": "NOAA / SWPC",
            "entry_type": "service",
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        # Initial listing
        await self._async_refresh_frame_list()

        # async_track_time_interval expects a normal callback; schedule async work as tasks
        self._unsub_advance = async_track_time_interval(
            self.hass,
            lambda now: self.hass.async_create_task(self._async_advance_frame()),
            timedelta(seconds=FRAME_ADVANCE_SECONDS),
        )

        self._unsub_refresh = async_track_time_interval(
            self.hass,
            lambda now: self.hass.async_create_task(self._async_refresh_frame_list()),
            timedelta(minutes=REFRESH_LIST_MINUTES),
        )

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub_advance:
            self._unsub_advance()
            self._unsub_advance = None
        if self._unsub_refresh:
            self._unsub_refresh()
            self._unsub_refresh = None
        await super().async_will_remove_from_hass()

    async def _async_fetch_text(self, url: str) -> str:
        async with async_timeout.timeout(TIMEOUT_SECONDS):
            resp = await self._session.get(url)
            resp.raise_for_status()
            return await resp.text()

    async def _async_refresh_frame_list(self) -> None:
        """Refresh list of recent PNG frames from SWPC directory listing."""
        dir_url = self._source.dir_url
        try:
            html = await self._async_fetch_text(dir_url)
        except (ClientError, TimeoutError):
            return  # keep current list

        names = PNG_HREF_RE.findall(html)
        pngs = [n for n in names if n.lower().endswith(".png")]

        urls = [dir_url + n for n in pngs]

        latest_url = dir_url + "latest.png"
        non_latest = [u for u in urls if not u.endswith("/latest.png")]

        # Sort by filename (timestamps in name => lexicographic works)
        non_latest_sorted = sorted(non_latest)

        if non_latest_sorted:
            frames = non_latest_sorted[-FRAME_COUNT:]
        else:
            frames = [latest_url]

        if frames != self._frames:
            self._frames = frames
            self._frame_idx = 0
            self._current_url = None
            self._current_bytes = None

            self._attr_image_last_updated = dt_util.utcnow()
            self.async_write_ha_state()

    async def _async_advance_frame(self) -> None:
        """Advance to next frame and mark image updated."""
        if not self._frames:
            self._frames = [self._source.dir_url + "latest.png"]
            self._frame_idx = 0

        self._frame_idx = (self._frame_idx + 1) % len(self._frames)
        next_url = self._frames[self._frame_idx]

        if next_url != self._current_url:
            self._current_url = next_url
            self._current_bytes = None

        self._attr_image_last_updated = dt_util.utcnow()
        self.async_write_ha_state()

    async def async_image(self) -> bytes | None:
        """Return bytes for current frame."""
        if not self._frames:
            self._frames = [self._source.dir_url + "latest.png"]
            self._frame_idx = 0

        url = self._frames[self._frame_idx]

        if self._current_url == url and self._current_bytes is not None:
            return self._current_bytes

        try:
            async with async_timeout.timeout(TIMEOUT_SECONDS):
                resp = await self._session.get(url)
                resp.raise_for_status()
                data = await resp.read()
        except (ClientError, TimeoutError):
            return None

        self._current_url = url
        self._current_bytes = data
        return data
