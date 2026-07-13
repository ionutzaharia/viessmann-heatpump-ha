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
    """Set up the backup and override sensors."""
    async_add_entities(
        [
            ViCareCirculationBackupSensor(entry.runtime_data),
            ViCareOverrideEndsSensor(entry.runtime_data),
            ViCareComfortPhaseSensor(entry.runtime_data),
        ]
    )


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


class ViCareOverrideEndsSensor(ViCareExtrasEntity, SensorEntity):
    """When the active schedule override will end and plans get restored."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "override_ends"
    _attr_icon = "mdi:timer-sand"

    def __init__(self, coordinator: ViCareExtrasCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "override-ends")

    @property
    def native_value(self) -> datetime | None:
        """Return when the override expires, or None when inactive."""
        override = self.coordinator.override
        if not override:
            return None
        return dt_util.parse_datetime(override["expires_at"])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose previews of the plans that will be restored."""
        saved = (self.coordinator.override or {}).get("saved", {})
        return {
            "saved_circulation_preview": format_schedule_preview(
                saved.get("circulation")
            ),
            "saved_dhw_preview": format_schedule_preview(saved.get("dhw")),
        }


class ViCareComfortPhaseSensor(ViCareExtrasEntity, SensorEntity):
    """Which phase the comfort warm water sequence is in."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["idle", "charging", "active"]
    _attr_translation_key = "comfort_phase"
    _attr_icon = "mdi:shower-head"

    def __init__(self, coordinator: ViCareExtrasCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "comfort-phase")

    @property
    def native_value(self) -> str:
        """Return the comfort phase."""
        return self.coordinator.comfort_phase

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose tank temperature and the charging target."""
        data = self.coordinator.data
        comfort = self.coordinator.comfort or {}
        return {
            "tank_temperature": data.dhw_storage_temperature,
            "dhw_setpoint": data.dhw_main_setpoint,
            "charging_target": comfort.get("threshold"),
            "one_time_charge_active": data.one_time_charge_active,
        }
