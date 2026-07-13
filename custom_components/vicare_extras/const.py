"""Constants for the ViCare Extras integration."""

from typing import Final

DOMAIN: Final = "vicare_extras"

CONF_CLIENT_ID: Final = "client_id"
CONF_SCAN_INTERVAL: Final = "scan_interval"

DEFAULT_SCAN_INTERVAL_MINUTES: Final = 15
TOKEN_FILENAME: Final = ".storage/vicare_extras_token.save"

PLATFORMS: Final = ["button", "number", "sensor", "switch"]

WEEKDAYS: Final = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

CIRCULATION_FEATURE: Final = "heating.dhw.pumps.circulation.schedule"
DHW_SCHEDULE_FEATURE: Final = "heating.dhw.schedule"

SERVICE_SET_CIRCULATION_SCHEDULE: Final = "set_circulation_schedule"
SERVICE_SET_DHW_SCHEDULE: Final = "set_dhw_schedule"
SERVICE_GET_SCHEDULES: Final = "get_schedules"
SERVICE_OVERRIDE_SCHEDULES: Final = "override_schedules"
SERVICE_CANCEL_OVERRIDE: Final = "cancel_override"

# Preferred mode for the switch's "always on" schedule, if the device offers it.
PREFERRED_ON_MODE: Final = "on"
