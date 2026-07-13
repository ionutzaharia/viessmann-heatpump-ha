"""Data update coordinator for ViCare Extras."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
import logging
from typing import Any

from PyViCare.PyViCareUtils import (
    PyViCareInvalidCredentialsError,
    PyViCareInternalServerError,
    PyViCareNotSupportedFeatureError,
    PyViCareRateLimitError,
)
import requests

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
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
