"""ViCare Extras: DHW circulation pump and schedule control for Viessmann heat pumps."""

from __future__ import annotations

import logging

from PyViCare.PyViCare import PyViCare
from PyViCare.PyViCareUtils import (
    PyViCareInvalidCredentialsError,
    PyViCareRateLimitError,
)
import requests

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .const import CONF_CLIENT_ID, PLATFORMS, TOKEN_FILENAME
from .coordinator import ViCareExtrasCoordinator
from .services import async_setup_services

_LOGGER = logging.getLogger(__name__)

ViCareExtrasConfigEntry = ConfigEntry[ViCareExtrasCoordinator]

# Gateway/communication modules that never carry DHW features.
_IGNORED_MODELS = ("Heatbox1", "Heatbox2_SRC", "E3_TCU41_x04", "E3_TCU10_x07")


def _login_and_pick_device(hass: HomeAssistant, entry: ConfigEntry):
    """Log in and return (device, serial, model) for the heating device."""
    vicare = PyViCare()
    vicare.initWithCredentials(
        entry.data[CONF_EMAIL],
        entry.data[CONF_PASSWORD],
        entry.data[CONF_CLIENT_ID],
        hass.config.path(TOKEN_FILENAME),
    )
    devices = vicare.devices
    if not devices:
        raise ConfigEntryNotReady("No devices found in ViCare account")

    device_config = next(
        (d for d in devices if d.getModel() not in _IGNORED_MODELS), devices[0]
    )
    model = device_config.getModel()
    device = device_config.asAutoDetectDevice()
    try:
        serial = device.getSerial()
    except Exception:  # noqa: BLE001 - serial is cosmetic; fall back to config id
        serial = device_config.getConfig().serial or device_config.device_id
    return device, str(serial), model


async def async_setup_entry(
    hass: HomeAssistant, entry: ViCareExtrasConfigEntry
) -> bool:
    """Set up ViCare Extras from a config entry."""
    try:
        device, serial, model = await hass.async_add_executor_job(
            _login_and_pick_device, hass, entry
        )
    except PyViCareInvalidCredentialsError as err:
        raise ConfigEntryAuthFailed("Invalid ViCare credentials") from err
    except PyViCareRateLimitError as err:
        raise ConfigEntryNotReady(
            f"Viessmann API rate limit reached, resets at {err.limitResetDate}"
        ) from err
    except requests.exceptions.RequestException as err:
        raise ConfigEntryNotReady(f"Cannot reach Viessmann API: {err}") from err

    _LOGGER.debug("ViCare Extras using device %s (serial %s)", model, serial)

    coordinator = ViCareExtrasCoordinator(hass, entry, device, serial, model)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    async_setup_services(hass)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: ViCareExtrasConfigEntry
) -> None:
    """Reload on options change (scan interval)."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(
    hass: HomeAssistant, entry: ViCareExtrasConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
