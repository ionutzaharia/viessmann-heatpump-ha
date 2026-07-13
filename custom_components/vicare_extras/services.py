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
    SERVICE_GET_SCHEDULES,
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
        SERVICE_GET_SCHEDULES,
        handle_get_schedules,
        supports_response=SupportsResponse.ONLY,
    )
