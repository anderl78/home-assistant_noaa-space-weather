"""Image platform for NOAA Space Weather (animated SUVI PNG sequences).

SWPC provides directories with many PNG frames + a latest.png.
We animate by cycling through the most recent N frames.

IMPORTANT: Time interval callbacks may run off the event loop. Therefore we must not call
hass.async_create_task directly from them. We schedule work onto the HA event loop
using loop.call_soon_threadsafe + asyncio.create_task.
"""

from __future__ import annotations

import asyncio
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
    _attr_content_type = "image/png"
    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        session: ClientSession,
        source: _SuviSource,
    ) -> None:
        super().__init__(hass)

        self._entry_id = entry_id
        self._session = session
        self._source = source

        self._attr_unique_id = f"{entry_id}_{source.object_id}"
        self._attr_name = source.name
        self._attr_object_id = source.object_id

        self._frames: list[str] = []
        self._frame_idx: int = 0

        self._current_url: str | None = None
        self._current_bytes: bytes | None = None

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

    def _schedule_in_loop(self, coro: asyncio.coroutines) -> None:
        """Schedule a coroutine onto the HA event loop from any thread safely."""
        loop = self.hass.loop

        def _create() -> None:
            asyncio.create_task(coro)

        loop.call_soon_threadsafe(_create)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        await self._async_refresh_frame_list()

        # NOTE: callback might run off-loop -> schedule safely
        self._unsub_advance = async_track_time_interval(
            self.hass,
            lambda now: self._schedule_in_loop(self._async_advance_frame()),
            timedelta(seconds=FRAME_ADVANCE_SECONDS),
        )

        self._unsub_refresh = async_track_time_interval(
            self.hass,
            lambda now: self._schedule_in_loop(self._async_refresh_frame_list()),
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
        dir_url = self._source.dir_url
        try:
            html = await self._async_fetch_text(dir_url)
        except (ClientError, TimeoutError):
            return

        names = PNG_HREF_RE.findall(html)
        pngs = [n for n in names if n.lower().endswith(".png")]

        urls = [dir_url + n for n in pngs]

        latest_url = dir_url + "latest.png"
        non_latest = [u for u in urls if not u.endswith("/latest.png")]
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
