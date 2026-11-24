"""Garage: vehicle maintenance tracking against a built-in schedule, with the log kept on a share."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.components.frontend import async_register_built_in_panel, async_remove_panel
from homeassistant.components.http import HomeAssistantView, StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

from .const import (
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
    PANEL_ELEMENT,
    PANEL_ICON,
    PANEL_JS_URL,
    PANEL_TITLE,
    PANEL_URL_PATH,
    SERVICE_LOG,
    SERVICE_PROFILE,
    SIGNAL_UPDATED,
)
from .schedule import DEFAULT_ACTION, ItemStatus, compute, load_schedule, pace_per_day, summary
from .store import GarageError, GarageStore, StoreConfig

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]
FRONTEND_DIR = Path(__file__).parent / "frontend"
PANEL_FILE = FRONTEND_DIR / "garage-panel.js"
IMAGE_NAMES = ("truck.png", "truck.jpg", "truck.webp", "vehicle.png", "vehicle.jpg")

_GLOBALS_REGISTERED = False


@dataclass
class GarageRuntime:
    hass: HomeAssistant
    entry_id: str
    name: str
    schedule: dict[str, Any]
    store: GarageStore
    odometer_entity: str
    fuel_entity: str | None
    tank_l: float | None
    odometer: float | None = None           # last known; None = never read (not zero)
    odometer_as_of: str | None = None
    statuses: list[ItemStatus] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    storage: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    pace: float | None = None              # miles per day from the log
    points: list[list[Any]] = field(default_factory=list)

    async def async_refresh(self) -> None:
        def work():
            st = self.store.status()
            entries = self.store.entries() if st["has_log"] else []
            settings = self.store.settings() if st["exists"] else {"profile": {}, "months": {}}
            return st, entries, settings

        try:
            st, entries, settings = await self.hass.async_add_executor_job(work)
            self.error = None
        except GarageError as err:
            self.error = str(err)
            _LOGGER.warning("Garage %s: %s", self.name, err)
            async_dispatcher_send(self.hass, SIGNAL_UPDATED.format(self.entry_id))
            return
        self.storage = st
        self.statuses = compute(self.schedule, entries, self.odometer, dt_util.now().date(),
                                settings.get("profile", {}), settings.get("months", {}))
        self.summary = summary(self.statuses)
        today = dt_util.now().date()
        self.pace = pace_per_day(entries, self.odometer, today)
        self.points = sorted([e["date"], e["odometer"]] for e in entries
                             if e.get("odometer") is not None and e.get("date"))
        async_dispatcher_send(self.hass, SIGNAL_UPDATED.format(self.entry_id))

    def device_info(self) -> dict[str, Any]:
        """Join the device that owns the odometer (e.g. the OBD dongle) so the vehicle is one device."""
        ent = er.async_get(self.hass).async_get(self.odometer_entity)
        if ent and ent.device_id:
            dev = dr.async_get(self.hass).async_get(ent.device_id)
            if dev and dev.identifiers:
                return {"identifiers": set(dev.identifiers)}
        return {"identifiers": {(DOMAIN, self.entry_id)}, "name": self.name, "manufacturer": "Garage"}


def runtimes(hass: HomeAssistant) -> dict[str, GarageRuntime]:
    return hass.data.setdefault(DOMAIN, {})


def _settings(entry: ConfigEntry) -> dict[str, Any]:
    return {**entry.data, **entry.options}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    s = _settings(entry)
    schedule = await hass.async_add_executor_job(load_schedule, s.get(CONF_SCHEDULE) or DEFAULT_SCHEDULE)
    store = GarageStore(StoreConfig(mount_path=s.get(CONF_MOUNT) or DEFAULT_MOUNT, folder=s[CONF_FOLDER]),
                        {int(it["n"]) for it in schedule["items"]}, today=lambda: dt_util.now().date())
    tank = float(s.get(CONF_TANK) or 0) or None
    rt = GarageRuntime(hass, entry.entry_id, s.get(CONF_NAME) or entry.title, schedule, store,
                       s[CONF_ODOMETER], s.get(CONF_FUEL) or None, tank)
    runtimes(hass)[entry.entry_id] = rt

    status = await hass.async_add_executor_job(store.status)
    if not status["mounted"]:
        _LOGGER.warning("Garage storage is not mounted at %s; logging is disabled until it is", status["path"])

    await _async_register_globals(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await rt.async_refresh()

    @callback
    def _midnight(_now) -> None:
        hass.async_create_task(rt.async_refresh())

    entry.async_on_unload(async_track_time_change(hass, _midnight, hour=0, minute=5, second=0))
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        runtimes(hass).pop(entry.entry_id, None)
        if not runtimes(hass):
            async_remove_panel(hass, PANEL_URL_PATH)
            global _PANEL_REGISTERED
            _PANEL_REGISTERED = False
    return ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


# ------------------------------------------------------------------ panel, API, services

_PANEL_REGISTERED = False


def _panel_file_info() -> tuple[int, str] | None:
    if not PANEL_FILE.exists():
        return None
    text = PANEL_FILE.read_text(encoding="utf-8")
    m = re.search(r"var VERSION = '([0-9A-Za-z.]+)';", text)
    return int(PANEL_FILE.stat().st_mtime), (m.group(1) if m else "0")


async def _async_register_globals(hass: HomeAssistant) -> None:
    global _GLOBALS_REGISTERED, _PANEL_REGISTERED
    if not _GLOBALS_REGISTERED:
        websocket_api.async_register_command(hass, ws_get)
        websocket_api.async_register_command(hass, ws_add)
        websocket_api.async_register_command(hass, ws_update)
        websocket_api.async_register_command(hass, ws_delete)
        websocket_api.async_register_command(hass, ws_profile)
        hass.http.register_view(GarageImageView())
        # Registered even before a panel file exists: routes can't be added later without a restart.
        await hass.http.async_register_static_paths([StaticPathConfig(PANEL_JS_URL, str(PANEL_FILE), False)])
        _register_services(hass)
        _GLOBALS_REGISTERED = True
    if not _PANEL_REGISTERED:
        info = await hass.async_add_executor_job(_panel_file_info)
        if info:
            stamp, version = info
            # Per-version element name: a browser can't redefine a custom element, and HA caches
            # the manifest until restart, so the version is read from the panel file itself.
            async_register_built_in_panel(
                hass, component_name="custom", sidebar_title=PANEL_TITLE, sidebar_icon=PANEL_ICON,
                frontend_url_path=PANEL_URL_PATH,
                config={"_panel_custom": {"name": f"{PANEL_ELEMENT}-{version.replace('.', '-')}",
                                          "js_url": f"{PANEL_JS_URL}?v={stamp}"}},
                require_admin=False, update=True,
            )
            _PANEL_REGISTERED = True


def _rt(hass: HomeAssistant, entry_id: str | None) -> GarageRuntime:
    rts = runtimes(hass)
    if entry_id:
        if entry_id in rts:
            return rts[entry_id]
        for rt in rts.values():                    # accept the vehicle name too
            if rt.name.lower() == str(entry_id).lower():
                return rt
        raise HomeAssistantError(f"No vehicle {entry_id!r}.")
    if len(rts) == 1:
        return next(iter(rts.values()))
    raise HomeAssistantError("Say which vehicle (entry_id).")


def snapshot(rt: GarageRuntime) -> dict[str, Any]:
    fuel = None
    if rt.fuel_entity:
        st = rt.hass.states.get(rt.fuel_entity)
        if st is not None:
            try:
                litres = float(st.state)
                fuel = {"litres": litres, "percent": round(litres / rt.tank_l * 100, 1) if rt.tank_l else None,
                        "as_of": st.last_updated.isoformat()}
            except ValueError:
                fuel = None
    return {
        "entry_id": rt.entry_id, "name": rt.name, "error": rt.error, "storage": rt.storage,
        "odometer": rt.odometer, "odometer_as_of": rt.odometer_as_of, "odometer_entity": rt.odometer_entity,
        "fuel_entity": rt.fuel_entity, "tank_l": rt.tank_l, "fuel": fuel,
        "schedule": rt.schedule, "summary": rt.summary,
        "pace": None if rt.pace is None else round(rt.pace, 1), "points": rt.points,
        "items": [s.as_dict() for s in rt.statuses],
    }


def _items_arg(rt: GarageRuntime, raw: list[Any]) -> list[dict[str, Any]]:
    """Accept [1, 2], ["oil", "Rotate"] or [{"n": 1, "action": ...}]."""
    lookup: dict[str, dict[str, Any]] = {}
    for it in rt.schedule["items"]:
        for key in (str(it["n"]), it["id"], it["short"].lower(), it["name"].lower()):
            lookup[key] = it
    out = []
    for r in raw:
        if isinstance(r, dict):
            it = lookup.get(str(r.get("n", "")).lower())
            if it is None:
                raise HomeAssistantError(f"Unknown item {r.get('n')!r}.")
            row = {"n": it["n"], "action": r.get("action") or DEFAULT_ACTION[it["kind"]]}
            if r.get("measure") not in (None, ""):
                row["measure"] = r["measure"]
            out.append(row)
        else:
            it = lookup.get(str(r).strip().lower())
            if it is None:
                raise HomeAssistantError(f"Unknown item {r!r}.")
            out.append({"n": it["n"], "action": DEFAULT_ACTION[it["kind"]]})
    return out


async def _user_name(hass: HomeAssistant, user_id: str | None) -> str:
    if not user_id:
        return ""
    user = await hass.auth.async_get_user(user_id)
    return user.name if user and user.name else ""


def _register_services(hass: HomeAssistant) -> None:
    async def log_service(call: ServiceCall) -> ServiceResponse:
        rt = _rt(hass, call.data.get("vehicle"))
        data = {
            "items": _items_arg(rt, call.data["items"]),
            "odometer": call.data.get("odometer", rt.odometer),
            "date": call.data.get("date"),
            "notes": call.data.get("notes"),
            "cost": call.data.get("cost"),
            "by": call.data.get("by", ""),
        }
        name = await _user_name(hass, call.context.user_id)
        try:
            entry = await hass.async_add_executor_job(rt.store.add, data, "service", name)
        except GarageError as err:
            raise HomeAssistantError(str(err)) from err
        await rt.async_refresh()
        return {"entry": entry}

    async def set_profile(call: ServiceCall) -> None:
        rt = _rt(hass, call.data.get("vehicle"))
        n = _items_arg(rt, [call.data["item"]])[0]["n"]
        try:
            await hass.async_add_executor_job(rt.store.set_profile, n, call.data["profile"])
        except GarageError as err:
            raise HomeAssistantError(str(err)) from err
        await rt.async_refresh()

    hass.services.async_register(
        DOMAIN, SERVICE_LOG, log_service,
        schema=vol.Schema({
            vol.Optional("vehicle"): cv.string,
            vol.Required("items"): vol.All(cv.ensure_list, [vol.Any(cv.string, int, dict)]),
            vol.Optional("odometer"): vol.Coerce(float),
            vol.Optional("date"): cv.date,
            vol.Optional("notes"): cv.string,
            vol.Optional("cost"): vol.Coerce(float),
            vol.Optional("by"): vol.In(["self", "dealer", "shop", ""]),
        }),
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_PROFILE, set_profile,
        schema=vol.Schema({
            vol.Optional("vehicle"): cv.string,
            vol.Required("item"): vol.Any(cv.string, int),
            vol.Required("profile"): vol.In(["normal", "severe"]),
        }),
    )


@websocket_api.websocket_command({vol.Required("type"): "garage/get", vol.Optional("entry_id"): str})
@websocket_api.async_response
async def ws_get(hass, connection, msg):
    rts = runtimes(hass)
    vehicles = [{"entry_id": r.entry_id, "name": r.name} for r in rts.values()]
    if not rts:
        connection.send_result(msg["id"], {"vehicles": [], "vehicle": None})
        return
    try:
        rt = _rt(hass, msg.get("entry_id") or next(iter(rts)))
    except HomeAssistantError as err:
        connection.send_error(msg["id"], "not_found", str(err))
        return
    log = await hass.async_add_executor_job(rt.store.entries) if rt.storage.get("has_log") else []
    settings = await hass.async_add_executor_job(rt.store.settings) if rt.storage.get("exists") else {}
    connection.send_result(msg["id"], {"vehicles": vehicles, "vehicle": snapshot(rt),
                                       "log": log, "settings": settings})


async def _ws_write(hass, connection, msg, work):
    try:
        rt = _rt(hass, msg.get("entry_id"))
        name = await _user_name(hass, connection.user.id if connection.user else None)
        result = await hass.async_add_executor_job(work, rt, name)
    except (GarageError, HomeAssistantError) as err:
        connection.send_error(msg["id"], "failed", str(err))
        return
    await rt.async_refresh()
    connection.send_result(msg["id"], {"result": result, "vehicle": snapshot(rt)})


@websocket_api.websocket_command({vol.Required("type"): "garage/add", vol.Optional("entry_id"): str,
                                  vol.Required("entry"): dict})
@websocket_api.async_response
async def ws_add(hass, connection, msg):
    def work(rt, name):
        data = dict(msg["entry"])
        data["items"] = _items_arg(rt, data.get("items") or [])
        return rt.store.add(data, "app", name)
    await _ws_write(hass, connection, msg, work)


@websocket_api.websocket_command({vol.Required("type"): "garage/update", vol.Optional("entry_id"): str,
                                  vol.Required("id"): str, vol.Required("entry"): dict})
@websocket_api.async_response
async def ws_update(hass, connection, msg):
    def work(rt, name):
        data = dict(msg["entry"])
        if "items" in data:
            data["items"] = _items_arg(rt, data["items"] or [])
        return rt.store.update(msg["id"], data, name)
    await _ws_write(hass, connection, msg, work)


@websocket_api.websocket_command({vol.Required("type"): "garage/delete", vol.Optional("entry_id"): str,
                                  vol.Required("id"): str})
@websocket_api.async_response
async def ws_delete(hass, connection, msg):
    await _ws_write(hass, connection, msg, lambda rt, name: rt.store.delete(msg["id"], name))


@websocket_api.websocket_command({vol.Required("type"): "garage/set_profile", vol.Optional("entry_id"): str,
                                  vol.Required("n"): int, vol.Required("profile"): vol.In(["normal", "severe"])})
@websocket_api.async_response
async def ws_profile(hass, connection, msg):
    await _ws_write(hass, connection, msg, lambda rt, name: rt.store.set_profile(msg["n"], msg["profile"]))


class GarageImageView(HomeAssistantView):
    """The vehicle's picture, read from its folder on the share (it is not shipped with the code)."""

    url = "/api/garage/{entry_id}/image"
    name = "api:garage:image"
    requires_auth = True

    async def get(self, request, entry_id):
        from aiohttp import web

        hass = request.app["hass"]
        rt = runtimes(hass).get(entry_id)
        if rt is None:
            return web.Response(status=404)

        def find():
            for nm in IMAGE_NAMES:
                p = rt.store.root / nm
                if p.is_file():
                    return p
            return None

        path = await hass.async_add_executor_job(find)
        if path is None:
            return web.Response(status=404)
        return web.FileResponse(path, headers={"Cache-Control": "private, max-age=3600"})
