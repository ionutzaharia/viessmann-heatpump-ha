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

# Comfort mode: charge tank, wait for temperature, then run the override.
COMFORT_POLL_INTERVAL_SECONDS: Final = 120
COMFORT_CHARGING_TIMEOUT_MINUTES: Final = 50
COMFORT_THRESHOLD_DELTA: Final = 2.0  # trigger at DHW setpoint minus this many K
COMFORT_FALLBACK_THRESHOLD: Final = 45.0  # if the setpoint can't be read

SERVICE_COMFORT_WARM_WATER: Final = "comfort_warm_water"
SERVICE_CANCEL_COMFORT: Final = "cancel_comfort"
