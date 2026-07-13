"""Base entity for ViCare Extras."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, WEEKDAYS
from .coordinator import ViCareExtrasCoordinator


def format_schedule_preview(schedule: dict[str, Any] | None) -> dict[str, str]:
    """Render a schedule as {day: "06:00-07:00 (on), 14:00-15:00 (on)"}."""
    if not schedule:
        return {}
    return {
        day: ", ".join(
            f"{e['start']}-{e['end']} ({e['mode']})" for e in schedule.get(day) or []
        )
        or "-"
        for day in WEEKDAYS
    }


class ViCareExtrasEntity(CoordinatorEntity[ViCareExtrasCoordinator]):
    """Entity attached to the heating device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ViCareExtrasCoordinator, key: str) -> None:
        """Initialize with a unique id derived from the device serial."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_serial}-{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_serial)},
            manufacturer="Viessmann",
            model=coordinator.device_model,
            name="ViCare Extras",
        )
