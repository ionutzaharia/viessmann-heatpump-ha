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
    available_fn: Callable[[ViCareExtrasCoordinator], bool] = lambda c: True


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
        available_fn=lambda c: c.backup is not None,
    ),
    ViCareExtrasButtonDescription(
        key="copy_dhw_to_circulation",
        translation_key="copy_dhw_to_circulation",
        icon="mdi:content-copy",
        press_fn=lambda c: c.async_copy_dhw_to_circulation(),
    ),
    ViCareExtrasButtonDescription(
        key="start_override",
        translation_key="start_override",
        icon="mdi:rocket-launch",
        press_fn=lambda c: c.async_start_override(c.override_duration_minutes),
    ),
    ViCareExtrasButtonDescription(
        key="cancel_override",
        translation_key="cancel_override",
        icon="mdi:timer-cancel",
        press_fn=lambda c: c.async_end_override(),
        available_fn=lambda c: c.override is not None,
    ),
    ViCareExtrasButtonDescription(
        key="comfort_warm_water",
        translation_key="comfort_warm_water",
        icon="mdi:shower-head",
        press_fn=lambda c: c.async_start_comfort(),
    ),
    ViCareExtrasButtonDescription(
        key="cancel_comfort",
        translation_key="cancel_comfort",
        icon="mdi:water-off",
        press_fn=lambda c: c.async_cancel_comfort(),
        available_fn=lambda c: c.comfort_phase != "idle",
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
        """Some actions need state (a backup, an active override) to exist."""
        return self.entity_description.available_fn(self.coordinator) and super().available

    async def async_press(self) -> None:
        """Run the action."""
        await self.entity_description.press_fn(self.coordinator)
