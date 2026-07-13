"""Data update coordinator for ViCare Extras."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
import logging
from typing import Any

from PyViCare.PyViCareUtils import (
    PyViCareCommandError,
    PyViCareInvalidCredentialsError,
    PyViCareInternalServerError,
    PyViCareNotSupportedFeatureError,
    PyViCareRateLimitError,
)
import requests

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DHW_SCHEDULE_FEATURE,
    DOMAIN,
    PREFERRED_ON_MODE,
    WEEKDAYS,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class ViCareExtrasData:
    """Snapshot of schedule-related state read from the API."""

    circulation_schedule: dict[str, Any] | None = None
    circulation_modes: list[str] = field(default_factory=list)
    circulation_pump_active: bool | None = None
    dhw_schedule: dict[str, Any] | None = None


class ViCareExtrasCoordinator(DataUpdateCoordinator[ViCareExtrasData]):
    """Polls schedules and pump state from the Viessmann API."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        device: Any,
        device_serial: str,
        device_model: str,
    ) -> None:
        """Initialize the coordinator."""
        minutes = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(minutes=minutes),
        )
        self.device = device
        self.device_serial = device_serial
        self.device_model = device_model
        self.backup_store: Store = Store(hass, 1, f"{DOMAIN}_backup")
        # {"schedule": {day: [entries]}, "backed_up_at": iso-utc}
        self.backup: dict[str, Any] | None = None

    async def async_load_backup(self) -> None:
        """Load a previously stored circulation schedule backup."""
        self.backup = await self.backup_store.async_load()

    def preferred_circulation_mode(self) -> str:
        """Return the best schedule mode the device offers."""
        modes = self.data.circulation_modes if self.data else []
        if PREFERRED_ON_MODE in modes:
            return PREFERRED_ON_MODE
        return modes[0] if modes else PREFERRED_ON_MODE

    async def async_write_circulation_schedule(self, schedule: dict) -> None:
        """Upload a circulation pump schedule, translating API errors."""
        await self._async_write(
            self.device.setDomesticHotWaterCirculationSchedule, schedule
        )

    async def async_write_dhw_schedule(self, schedule: dict) -> None:
        """Upload a DHW time program, translating API errors."""

        def _write(new_schedule: dict) -> None:
            self.device.service.setProperty(
                DHW_SCHEDULE_FEATURE, "setSchedule", {"newSchedule": new_schedule}
            )

        await self._async_write(_write, schedule)

    async def _async_write(self, write_fn, schedule: dict) -> None:
        try:
            await self.hass.async_add_executor_job(write_fn, schedule)
        except PyViCareCommandError as err:
            raise HomeAssistantError(
                f"Viessmann API rejected the schedule: {err}"
            ) from err
        except PyViCareRateLimitError as err:
            raise HomeAssistantError(
                f"Viessmann API rate limit reached, resets at {err.limitResetDate}"
            ) from err

    async def async_backup_circulation_schedule(self) -> None:
        """Store the current circulation schedule in HA storage."""
        current = self.data.circulation_schedule if self.data else None
        if current is None:
            raise HomeAssistantError("No circulation schedule available to back up")
        schedule = {day: current.get(day, []) for day in WEEKDAYS}
        self.backup = {
            "schedule": schedule,
            "backed_up_at": dt_util.utcnow().isoformat(),
        }
        await self.backup_store.async_save(self.backup)
        self.async_update_listeners()

    async def async_restore_circulation_schedule(self) -> None:
        """Upload the backed-up circulation schedule to the device."""
        if not self.backup:
            raise HomeAssistantError(
                "No circulation schedule backup stored; press the backup button first"
            )
        await self.async_write_circulation_schedule(self.backup["schedule"])
        await self.async_request_refresh()

    async def async_copy_dhw_to_circulation(self) -> None:
        """Copy the DHW time program onto the circulation pump schedule."""
        dhw = self.data.dhw_schedule if self.data else None
        if dhw is None:
            raise HomeAssistantError("No DHW schedule available to copy")
        modes = self.data.circulation_modes
        fallback = self.preferred_circulation_mode()
        schedule = {
            day: [
                {
                    "start": entry["start"],
                    "end": entry["end"],
                    "mode": entry["mode"] if entry["mode"] in modes else fallback,
                    "position": pos,
                }
                for pos, entry in enumerate(dhw.get(day) or [])
            ]
            for day in WEEKDAYS
        }
        await self.async_write_circulation_schedule(schedule)
        await self.async_request_refresh()

    async def _async_update_data(self) -> ViCareExtrasData:
        """Fetch schedule data from the API."""
        try:
            return await self.hass.async_add_executor_job(self._fetch)
        except PyViCareInvalidCredentialsError as err:
            raise ConfigEntryAuthFailed("Invalid ViCare credentials") from err
        except PyViCareRateLimitError as err:
            raise UpdateFailed(
                f"Viessmann API rate limit reached, resets at {err.limitResetDate}"
            ) from err
        except (
            PyViCareInternalServerError,
            requests.exceptions.RequestException,
        ) as err:
            raise UpdateFailed(f"Error communicating with Viessmann API: {err}") from err

    def _fetch(self) -> ViCareExtrasData:
        data = ViCareExtrasData()
        try:
            data.circulation_schedule = self.device.getDomesticHotWaterCirculationSchedule()
        except PyViCareNotSupportedFeatureError:
            _LOGGER.debug("Circulation schedule not supported")
        try:
            data.circulation_modes = list(
                self.device.getDomesticHotWaterCirculationScheduleModes()
            )
        except PyViCareNotSupportedFeatureError:
            _LOGGER.debug("Circulation schedule modes not supported")
        try:
            data.circulation_pump_active = (
                self.device.getDomesticHotWaterCirculationPumpActive()
            )
        except PyViCareNotSupportedFeatureError:
            _LOGGER.debug("Circulation pump active flag not supported")
        try:
            data.dhw_schedule = self.device.getDomesticHotWaterSchedule()
        except PyViCareNotSupportedFeatureError:
            _LOGGER.debug("DHW schedule not supported")
        return data
