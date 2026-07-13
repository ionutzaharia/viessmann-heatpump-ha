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
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.event import (
    async_call_later,
    async_track_point_in_utc_time,
)
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    COMFORT_CHARGING_TIMEOUT_MINUTES,
    COMFORT_FALLBACK_THRESHOLD,
    COMFORT_POLL_INTERVAL_SECONDS,
    COMFORT_THRESHOLD_DELTA,
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
    dhw_storage_temperature: float | None = None
    dhw_main_setpoint: float | None = None
    one_time_charge_active: bool | None = None


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
        self.override_store: Store = Store(hass, 1, f"{DOMAIN}_override")
        # {"saved": {"circulation": {...}, "dhw": {...}}, "expires_at": iso-utc}
        self.override: dict[str, Any] | None = None
        self.override_duration_minutes: int = 60
        self._override_timer: CALLBACK_TYPE | None = None
        self.comfort_store: Store = Store(hass, 1, f"{DOMAIN}_comfort")
        # {"charging_started_at": iso-utc, "duration_minutes": int, "threshold": float}
        self.comfort: dict[str, Any] | None = None
        self._comfort_timer: CALLBACK_TYPE | None = None

    async def async_load_backup(self) -> None:
        """Load stored backup, pending override, and pending comfort charge."""
        self.backup = await self.backup_store.async_load()
        self.override = await self.override_store.async_load()
        if self.override:
            await self._async_schedule_override_end()
        self.comfort = await self.comfort_store.async_load()
        if self.comfort:
            self._schedule_comfort_poll()

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

    def _always_on_schedule(self, mode: str) -> dict:
        return {
            day: [{"start": "00:00", "end": "24:00", "mode": mode, "position": 0}]
            for day in WEEKDAYS
        }

    async def async_start_override(self, minutes: int) -> None:
        """Boost DHW + circulation with always-on schedules for N minutes.

        The original plans are persisted before writing, so even a partial
        write failure or an HA restart still ends in a restore at expiry.
        Starting again while active only extends the timer; the originally
        saved plans are kept.
        """
        expires_at = dt_util.utcnow() + timedelta(minutes=minutes)
        extending = self.override is not None
        if not extending:
            circulation = self.data.circulation_schedule if self.data else None
            dhw = self.data.dhw_schedule if self.data else None
            if circulation is None or dhw is None:
                raise HomeAssistantError(
                    "Current schedules not available; cannot start override"
                )
            self.override = {
                "saved": {
                    "circulation": {day: circulation.get(day, []) for day in WEEKDAYS},
                    "dhw": {day: dhw.get(day, []) for day in WEEKDAYS},
                },
                "expires_at": expires_at.isoformat(),
            }
        else:
            self.override["expires_at"] = expires_at.isoformat()
        await self.override_store.async_save(self.override)
        await self._async_schedule_override_end()
        self.async_update_listeners()

        if not extending:
            await self.async_write_circulation_schedule(
                self._always_on_schedule(self.preferred_circulation_mode())
            )
            await self.async_write_dhw_schedule(self._always_on_schedule("on"))
            await self.async_request_refresh()

    async def async_end_override(self) -> None:
        """Restore the schedules saved when the override started."""
        if not self.override:
            raise HomeAssistantError("No schedule override is active")
        saved = self.override["saved"]
        await self.async_write_circulation_schedule(saved["circulation"])
        await self.async_write_dhw_schedule(saved["dhw"])
        self._cancel_override_timer()
        self.override = None
        await self.override_store.async_remove()
        self.async_update_listeners()
        await self.async_request_refresh()

    def _cancel_override_timer(self) -> None:
        if self._override_timer:
            self._override_timer()
            self._override_timer = None

    async def _async_schedule_override_end(self) -> None:
        self._cancel_override_timer()
        expires_at = dt_util.parse_datetime(self.override["expires_at"])
        if expires_at is None or expires_at <= dt_util.utcnow():
            await self._async_handle_override_end(dt_util.utcnow())
            return
        self._override_timer = async_track_point_in_utc_time(
            self.hass, self._async_handle_override_end, expires_at
        )

    async def _async_handle_override_end(self, _now) -> None:
        self._override_timer = None
        try:
            await self.async_end_override()
        except HomeAssistantError as err:
            _LOGGER.error(
                "Failed to restore schedules after override, retrying in 5 minutes: %s",
                err,
            )
            self.override["expires_at"] = (
                dt_util.utcnow() + timedelta(minutes=5)
            ).isoformat()
            await self.override_store.async_save(self.override)
            await self._async_schedule_override_end()

    async def async_shutdown(self) -> None:
        """Cancel timers on unload (stored override/comfort states survive)."""
        self._cancel_override_timer()
        self._cancel_comfort_timer()
        await super().async_shutdown()

    @property
    def comfort_phase(self) -> str:
        """Where the comfort sequence is: idle, charging, or active."""
        if self.comfort:
            return "charging"
        if self.override:
            return "active"
        return "idle"

    async def async_start_comfort(self, minutes: int | None = None) -> None:
        """Inertia-aware comfort: charge tank, wait for temperature, boost.

        Triggers a one-time charge immediately, polls the storage temperature
        until it reaches the DHW setpoint minus a small delta (or a timeout),
        then starts the schedule override for the given duration.
        """
        minutes = minutes or self.override_duration_minutes
        if self.comfort:
            # Already charging: just take the new duration for the boost phase.
            self.comfort["duration_minutes"] = minutes
            await self.comfort_store.async_save(self.comfort)
            self.async_update_listeners()
            return
        if self.override:
            await self.async_start_override(minutes)
            return

        setpoint = self.data.dhw_main_setpoint if self.data else None
        threshold = (
            setpoint - COMFORT_THRESHOLD_DELTA
            if setpoint is not None
            else COMFORT_FALLBACK_THRESHOLD
        )
        try:
            await self.hass.async_add_executor_job(self.device.activateOneTimeCharge)
        except PyViCareCommandError as err:
            raise HomeAssistantError(
                f"Viessmann API rejected one-time charge: {err}"
            ) from err
        except PyViCareRateLimitError as err:
            raise HomeAssistantError(
                f"Viessmann API rate limit reached, resets at {err.limitResetDate}"
            ) from err
        self.comfort = {
            "charging_started_at": dt_util.utcnow().isoformat(),
            "duration_minutes": minutes,
            "threshold": threshold,
        }
        await self.comfort_store.async_save(self.comfort)
        self._schedule_comfort_poll()
        self.async_update_listeners()

    async def async_cancel_comfort(self) -> None:
        """Abort the comfort sequence, whichever phase it is in."""
        if not self.comfort and not self.override:
            raise HomeAssistantError("Comfort mode is not active")
        if self.comfort:
            try:
                await self.hass.async_add_executor_job(
                    self.device.deactivateOneTimeCharge
                )
            except Exception as err:  # noqa: BLE001 - best effort, charge may be done
                _LOGGER.warning("Could not deactivate one-time charge: %s", err)
            await self._async_clear_comfort()
        if self.override:
            await self.async_end_override()

    def _cancel_comfort_timer(self) -> None:
        if self._comfort_timer:
            self._comfort_timer()
            self._comfort_timer = None

    def _schedule_comfort_poll(self) -> None:
        self._cancel_comfort_timer()
        self._comfort_timer = async_call_later(
            self.hass, COMFORT_POLL_INTERVAL_SECONDS, self._async_comfort_poll
        )

    async def _async_clear_comfort(self) -> None:
        self._cancel_comfort_timer()
        self.comfort = None
        await self.comfort_store.async_remove()
        self.async_update_listeners()

    async def _async_comfort_poll(self, _now) -> None:
        """Check tank temperature during the charging phase."""
        self._comfort_timer = None
        if not self.comfort:
            return
        try:
            temperature = await self.hass.async_add_executor_job(
                self.device.getDomesticHotWaterStorageTemperature
            )
        except Exception as err:  # noqa: BLE001 - transient errors: keep polling
            _LOGGER.warning("Comfort: could not read tank temperature: %s", err)
            self._schedule_comfort_poll()
            return

        started = dt_util.parse_datetime(self.comfort["charging_started_at"])
        elapsed_minutes = (dt_util.utcnow() - started).total_seconds() / 60
        threshold = self.comfort["threshold"]
        if temperature < threshold and elapsed_minutes < COMFORT_CHARGING_TIMEOUT_MINUTES:
            _LOGGER.debug(
                "Comfort charging: tank at %.1f°C, waiting for %.1f°C", temperature, threshold
            )
            self._schedule_comfort_poll()
            return

        if temperature < threshold:
            _LOGGER.warning(
                "Comfort: tank only reached %.1f°C after %d minutes; boosting anyway",
                temperature,
                COMFORT_CHARGING_TIMEOUT_MINUTES,
            )
        minutes = self.comfort["duration_minutes"]
        await self._async_clear_comfort()
        try:
            await self.async_start_override(minutes)
        except HomeAssistantError as err:
            _LOGGER.error("Comfort: could not start the boost phase: %s", err)

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
        try:
            data.dhw_storage_temperature = (
                self.device.getDomesticHotWaterStorageTemperature()
            )
        except PyViCareNotSupportedFeatureError:
            _LOGGER.debug("DHW storage temperature not supported")
        try:
            data.dhw_main_setpoint = (
                self.device.getDomesticHotWaterConfiguredTemperature()
            )
        except PyViCareNotSupportedFeatureError:
            _LOGGER.debug("DHW configured temperature not supported")
        try:
            data.one_time_charge_active = self.device.getOneTimeCharge()
        except PyViCareNotSupportedFeatureError:
            _LOGGER.debug("One-time charge not supported")
        return data
