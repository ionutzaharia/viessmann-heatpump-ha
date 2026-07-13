"""Switch platform for ViCare Extras: DHW circulation pump."""

from __future__ import annotations

import logging
from typing import Any

from PyViCare.PyViCareUtils import PyViCareCommandError, PyViCareRateLimitError

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import ViCareExtrasConfigEntry
from .const import DOMAIN, PREFERRED_ON_MODE, WEEKDAYS
from .coordinator import ViCareExtrasCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ViCareExtrasConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the circulation pump switch."""
    coordinator = entry.runtime_data
    if coordinator.data.circulation_schedule is None:
        _LOGGER.warning(
            "Circulation pump schedule not available on this device; "
            "no switch entity created"
        )
        return
    async_add_entities([ViCareCirculationPumpSwitch(coordinator)])


class ViCareCirculationPumpSwitch(
    CoordinatorEntity[ViCareExtrasCoordinator], SwitchEntity
):
    """DHW circulation pump, controlled by uploading schedules.

    The Viessmann API offers no direct on/off command for the circulation
    pump: ON uploads an always-on weekly schedule, OFF uploads an empty one.
    State is therefore derived from whether the current schedule has entries.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "dhw_circulation_pump"
    _attr_icon = "mdi:pump"

    def __init__(self, coordinator: ViCareExtrasCoordinator) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_serial}-dhw-circulation-pump"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_serial)},
            manufacturer="Viessmann",
            model=coordinator.device_model,
            name="ViCare Extras",
        )
        self._optimistic_state: bool | None = None

    @property
    def is_on(self) -> bool | None:
        """Return True if the schedule contains any entry."""
        if self._optimistic_state is not None:
            return self._optimistic_state
        schedule = self.coordinator.data.circulation_schedule
        if schedule is None:
            return None
        return any(schedule.get(day) for day in WEEKDAYS)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the raw schedule and pump activity for observability."""
        data = self.coordinator.data
        return {
            "schedule": data.circulation_schedule,
            "available_modes": data.circulation_modes,
            "pump_currently_running": data.circulation_pump_active,
        }

    def _handle_coordinator_update(self) -> None:
        self._optimistic_state = None
        super()._handle_coordinator_update()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Upload an always-on schedule."""
        modes = self.coordinator.data.circulation_modes
        mode = PREFERRED_ON_MODE if PREFERRED_ON_MODE in modes else (
            modes[0] if modes else PREFERRED_ON_MODE
        )
        # Some devices reject end=24:00; fall back to 23:59.
        try:
            await self._async_write(self._always_on(mode, "24:00"), True)
        except HomeAssistantError:
            await self._async_write(self._always_on(mode, "23:59"), True)

    @staticmethod
    def _always_on(mode: str, end: str) -> dict:
        return {
            day: [{"start": "00:00", "end": end, "mode": mode, "position": 0}]
            for day in WEEKDAYS
        }

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Upload an empty schedule."""
        await self._async_write({}, False)

    async def _async_write(self, schedule: dict, new_state: bool) -> None:
        try:
            await self.hass.async_add_executor_job(
                self.coordinator.device.setDomesticHotWaterCirculationSchedule,
                schedule,
            )
        except PyViCareCommandError as err:
            raise HomeAssistantError(
                f"Viessmann API rejected the schedule: {err}"
            ) from err
        except PyViCareRateLimitError as err:
            raise HomeAssistantError(
                f"Viessmann API rate limit reached, resets at {err.limitResetDate}"
            ) from err
        self._optimistic_state = new_state
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()
