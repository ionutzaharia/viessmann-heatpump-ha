"""Number platform for ViCare Extras: override duration."""

from __future__ import annotations

from homeassistant.components.number import NumberMode, RestoreNumber
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ViCareExtrasConfigEntry
from .coordinator import ViCareExtrasCoordinator
from .entity import ViCareExtrasEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ViCareExtrasConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the override duration number."""
    async_add_entities([ViCareOverrideDurationNumber(entry.runtime_data)])


class ViCareOverrideDurationNumber(ViCareExtrasEntity, RestoreNumber):
    """How long the schedule override boost should last."""

    _attr_translation_key = "override_duration"
    _attr_icon = "mdi:timer-outline"
    _attr_native_min_value = 10
    _attr_native_max_value = 1440
    _attr_native_step = 10
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: ViCareExtrasCoordinator) -> None:
        """Initialize the number."""
        super().__init__(coordinator, "override-duration")

    async def async_added_to_hass(self) -> None:
        """Restore the previously set duration."""
        await super().async_added_to_hass()
        if (data := await self.async_get_last_number_data()) and data.native_value:
            self.coordinator.override_duration_minutes = int(data.native_value)

    @property
    def native_value(self) -> float:
        """Return the configured duration."""
        return self.coordinator.override_duration_minutes

    async def async_set_native_value(self, value: float) -> None:
        """Store the duration for the start-override button."""
        self.coordinator.override_duration_minutes = int(value)
        self.async_write_ha_state()
