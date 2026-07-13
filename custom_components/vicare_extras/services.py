"""Services for ViCare Extras."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    SERVICE_CANCEL_COMFORT,
    SERVICE_CANCEL_OVERRIDE,
    SERVICE_COMFORT_WARM_WATER,
    SERVICE_GET_SCHEDULES,
    SERVICE_OVERRIDE_SCHEDULES,
    SERVICE_SET_CIRCULATION_SCHEDULE,
    SERVICE_SET_DHW_SCHEDULE,
    WEEKDAYS,
)
from .coordinator import ViCareExtrasCoordinator

_LOGGER = logging.getLogger(__name__)

TIME_RE = r"^([01]\d|2[0-3]):[0-5]\d$|^24:00$"

ENTRY_SCHEMA = vol.Schema(
    {
        vol.Required("start"): cv.matches_regex(TIME_RE),
        vol.Required("end"): cv.matches_regex(TIME_RE),
        vol.Required("mode"): cv.string,
        vol.Optional("position", default=0): cv.positive_int,
    }
)

SCHEDULE_SCHEMA = vol.Schema(
    {vol.Optional(day): [ENTRY_SCHEMA] for day in WEEKDAYS}
)


def _get_coordinator(hass: HomeAssistant) -> ViCareExtrasCoordinator:
    """Return the coordinator of the (single) loaded config entry."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is ConfigEntryState.LOADED:
            return entry.runtime_data
    raise HomeAssistantError("ViCare Extras is not set up")


def _build_full_week(call_data: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Normalize service data into a full 7-day schedule; missing days are empty."""
    schedule: dict[str, list[dict[str, Any]]] = {}
    for day in WEEKDAYS:
        entries = sorted(call_data.get(day, []), key=lambda e: e["start"])
        for pos, entry in enumerate(entries):
            entry["position"] = pos
        schedule[day] = entries
    return schedule


def async_setup_services(hass: HomeAssistant) -> None:
    """Register services (idempotent)."""
    if hass.services.has_service(DOMAIN, SERVICE_SET_CIRCULATION_SCHEDULE):
        return

    async def handle_set_circulation_schedule(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass)
        await coordinator.async_write_circulation_schedule(_build_full_week(call.data))
        await coordinator.async_request_refresh()

    async def handle_set_dhw_schedule(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass)
        await coordinator.async_write_dhw_schedule(_build_full_week(call.data))
        await coordinator.async_request_refresh()

    async def handle_override_schedules(call: ServiceCall) -> None:
        await _get_coordinator(hass).async_start_override(call.data["minutes"])

    async def handle_cancel_override(call: ServiceCall) -> None:
        await _get_coordinator(hass).async_end_override()

    async def handle_comfort_warm_water(call: ServiceCall) -> None:
        await _get_coordinator(hass).async_start_comfort(call.data.get("minutes"))

    async def handle_cancel_comfort(call: ServiceCall) -> None:
        await _get_coordinator(hass).async_cancel_comfort()

    async def handle_get_schedules(call: ServiceCall) -> ServiceResponse:
        coordinator = _get_coordinator(hass)
        await coordinator.async_refresh()
        data = coordinator.data
        return {
            "circulation_schedule": data.circulation_schedule or {},
            "circulation_modes": data.circulation_modes,
            "dhw_schedule": data.dhw_schedule or {},
        }

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_CIRCULATION_SCHEDULE,
        handle_set_circulation_schedule,
        schema=SCHEDULE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_DHW_SCHEDULE,
        handle_set_dhw_schedule,
        schema=SCHEDULE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_OVERRIDE_SCHEDULES,
        handle_override_schedules,
        schema=vol.Schema(
            {
                vol.Required("minutes"): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=1440)
                )
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CANCEL_OVERRIDE,
        handle_cancel_override,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_COMFORT_WARM_WATER,
        handle_comfort_warm_water,
        schema=vol.Schema(
            {
                vol.Optional("minutes"): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=1440)
                )
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CANCEL_COMFORT,
        handle_cancel_comfort,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_SCHEDULES,
        handle_get_schedules,
        supports_response=SupportsResponse.ONLY,
    )
