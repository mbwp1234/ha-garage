"""Config flow: one entry per vehicle."""
from __future__ import annotations

import os
import re
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_BATTERY,
    CONF_FOLDER,
    CONF_FUEL,
    CONF_MOUNT,
    CONF_NAME,
    CONF_ODOMETER,
    CONF_SCHEDULE,
    CONF_TANK,
    DEFAULT_MOUNT,
    DEFAULT_SCHEDULE,
    DOMAIN,
)
from .schedule import available_schedules

FOLDER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _-]{0,40}$")


def _schema(d: dict[str, Any], schedules: dict[str, str]) -> vol.Schema:
    opts = [selector.SelectOptionDict(value=k, label=v) for k, v in schedules.items()]
    fuel = d.get(CONF_FUEL)
    batt = d.get(CONF_BATTERY)
    return vol.Schema({
        vol.Required(CONF_NAME, default=d.get(CONF_NAME, "")): str,
        vol.Required(CONF_SCHEDULE, default=d.get(CONF_SCHEDULE, DEFAULT_SCHEDULE)):
            selector.SelectSelector(selector.SelectSelectorConfig(options=opts)),
        # Optional: a vehicle without an OBD dongle yet runs on mileage typed into the panel.
        vol.Optional(CONF_ODOMETER, **({"default": d[CONF_ODOMETER]} if d.get(CONF_ODOMETER) else {})):
            selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
        vol.Optional(CONF_FUEL, **({"default": fuel} if fuel else {})):
            selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
        vol.Optional(CONF_BATTERY, **({"default": batt} if batt else {})):
            selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
        vol.Optional(CONF_TANK, default=d.get(CONF_TANK, 0)):
            selector.NumberSelector(selector.NumberSelectorConfig(min=0, max=400, step=0.1, mode="box",
                                                                  unit_of_measurement="L")),
        vol.Required(CONF_MOUNT, default=d.get(CONF_MOUNT, DEFAULT_MOUNT)): str,
        vol.Required(CONF_FOLDER, default=d.get(CONF_FOLDER, "")): str,
    })


def _validate(data: dict[str, Any]) -> dict[str, str]:
    errors: dict[str, str] = {}
    mount = str(data.get(CONF_MOUNT, "")).rstrip("/")
    if not (mount.startswith("/media/") or mount.startswith("/share/")) or ".." in mount:
        errors[CONF_MOUNT] = "bad_mount"
    elif not os.path.ismount(mount):
        errors[CONF_MOUNT] = "not_mounted"
    if not FOLDER_RE.match(str(data.get(CONF_FOLDER, ""))):
        errors[CONF_FOLDER] = "bad_folder"
    return errors


class GarageConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        schedules = await self.hass.async_add_executor_job(available_schedules)
        if user_input is not None:
            user_input[CONF_MOUNT] = user_input[CONF_MOUNT].rstrip("/")
            if not user_input.get(CONF_FOLDER):
                user_input[CONF_FOLDER] = re.sub(r"[^a-z0-9]+", "-", user_input[CONF_NAME].lower()).strip("-") or "vehicle"
            errors = await self.hass.async_add_executor_job(_validate, user_input)
            if not errors:
                await self.async_set_unique_id(f"{user_input[CONF_MOUNT]}/{user_input[CONF_FOLDER]}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)
        return self.async_show_form(step_id="user", data_schema=_schema(user_input or {}, schedules), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(entry: config_entries.ConfigEntry):
        return GarageOptionsFlow()


class GarageOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        schedules = await self.hass.async_add_executor_job(available_schedules)
        current = {**self.config_entry.data, **self.config_entry.options}
        if user_input is not None:
            user_input[CONF_MOUNT] = user_input[CONF_MOUNT].rstrip("/")
            errors = await self.hass.async_add_executor_job(_validate, user_input)
            if not errors:
                return self.async_create_entry(data=user_input)
        return self.async_show_form(step_id="init", data_schema=_schema(user_input or current, schedules), errors=errors)
