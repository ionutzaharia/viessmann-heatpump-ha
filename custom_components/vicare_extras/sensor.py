"""Sensor platform for ViCare Extras: circulation schedule backup info."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import ViCareExtrasConfigEntry
from .coordinator import ViCareExtrasCoordinator
from .entity import ViCareExtrasEntity, format_schedule_preview


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ViCareExtrasConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the backup sensor."""
    async_add_entities([ViCareCirculationBackupSensor(entry.runtime_data)])


class ViCareCirculationBackupSensor(ViCareExtrasEntity, SensorEntity):
    """When the circulation schedule was last backed up, with a preview."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "circulation_schedule_backup"
    _attr_icon = "mdi:content-save-cog"

    def __init__(self, coordinator: ViCareExtrasCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "circulation-schedule-backup")

    @property
    def native_value(self) -> datetime | None:
        """Return the last backup time."""
        backup = self.coordinator.backup
        if not backup:
            return None
        return dt_util.parse_datetime(backup["backed_up_at"])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the backed-up schedule raw and as a readable preview."""
        backup = self.coordinator.backup or {}
        schedule = backup.get("schedule")
        return {
            "backup_schedule": schedule,
            "backup_preview": format_schedule_preview(schedule),
        }
