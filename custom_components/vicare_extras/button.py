"""Button platform for ViCare Extras: backup / restore / copy actions."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ViCareExtrasConfigEntry
from .coordinator import ViCareExtrasCoordinator
from .entity import ViCareExtrasEntity


@dataclass(frozen=True, kw_only=True)
class ViCareExtrasButtonDescription(ButtonEntityDescription):
    """Button description with its coordinator action."""

    press_fn: Callable[[ViCareExtrasCoordinator], Awaitable[None]]
    requires_backup: bool = False


BUTTONS: tuple[ViCareExtrasButtonDescription, ...] = (
    ViCareExtrasButtonDescription(
        key="backup_circulation_schedule",
        translation_key="backup_circulation_schedule",
        icon="mdi:content-save",
        press_fn=lambda c: c.async_backup_circulation_schedule(),
    ),
    ViCareExtrasButtonDescription(
        key="restore_circulation_schedule",
        translation_key="restore_circulation_schedule",
        icon="mdi:backup-restore",
        press_fn=lambda c: c.async_restore_circulation_schedule(),
        requires_backup=True,
    ),
    ViCareExtrasButtonDescription(
        key="copy_dhw_to_circulation",
        translation_key="copy_dhw_to_circulation",
        icon="mdi:content-copy",
        press_fn=lambda c: c.async_copy_dhw_to_circulation(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ViCareExtrasConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the action buttons."""
    coordinator = entry.runtime_data
    async_add_entities(
        ViCareExtrasButton(coordinator, description) for description in BUTTONS
    )


class ViCareExtrasButton(ViCareExtrasEntity, ButtonEntity):
    """A one-shot schedule action."""

    entity_description: ViCareExtrasButtonDescription

    def __init__(
        self,
        coordinator: ViCareExtrasCoordinator,
        description: ViCareExtrasButtonDescription,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        """Restore is only available once a backup exists."""
        if self.entity_description.requires_backup and not self.coordinator.backup:
            return False
        return super().available

    async def async_press(self) -> None:
        """Run the action."""
        await self.entity_description.press_fn(self.coordinator)
