"""Constants for Garage."""
from __future__ import annotations

DOMAIN = "garage"

CONF_NAME = "name"
CONF_SCHEDULE = "schedule"
CONF_ODOMETER = "odometer_entity"
CONF_FUEL = "fuel_entity"
CONF_TANK = "tank_size"
CONF_BATTERY = "battery_entity"
CONF_MOUNT = "mount_path"
CONF_FOLDER = "folder"

DEFAULT_MOUNT = "/media/garage"
DEFAULT_SCHEDULE = "toyota_tacoma_3g"

PANEL_URL_PATH = "garage"
PANEL_ELEMENT = "garage-panel"
PANEL_JS_URL = "/garage_panel"
PANEL_TITLE = "Garage"
PANEL_ICON = "mdi:car-wrench"

SIGNAL_UPDATED = "garage_updated_{}"

SERVICE_LOG = "log_service"
SERVICE_PROFILE = "set_profile"

# An odometer that jumps further than this between two readings is held back until it
# repeats: a single garbage frame from the bus must not mark every service as done.
MAX_ODO_JUMP = 5000
