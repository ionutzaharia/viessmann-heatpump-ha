"""Switch platform for ViCare Extras: DHW circulation pump."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ViCareExtrasConfigEntry
from .const import WEEKDAYS
from .coordinator import ViCareExtrasCoordinator
from .entity import ViCareExtrasEntity, format_schedule_preview

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


class ViCareCirculationPumpSwitch(ViCareExtrasEntity, SwitchEntity):
    """DHW circulation pump, controlled by uploading schedules.

    The Viessmann API offers no direct on/off command for the circulation
    pump: ON uploads an always-on weekly schedule, OFF uploads an empty one.
    State is therefore derived from whether the current schedule has entries.
    """

    _attr_translation_key = "dhw_circulation_pump"
    _attr_icon = "mdi:pump"

    def __init__(self, coordinator: ViCareExtrasCoordinator) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, "dhw-circulation-pump")
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
            "schedule_preview": format_schedule_preview(data.circulation_schedule),
            "available_modes": data.circulation_modes,
            "pump_currently_running": data.circulation_pump_active,
        }

    def _handle_coordinator_update(self) -> None:
        self._optimistic_state = None
        super()._handle_coordinator_update()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Upload an always-on schedule."""
        mode = self.coordinator.preferred_circulation_mode()
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
        await self.coordinator.async_write_circulation_schedule(schedule)
        self._optimistic_state = new_state
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()
