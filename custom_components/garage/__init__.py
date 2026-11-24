"""Garage: vehicle maintenance tracking against a built-in schedule, with the log kept on a share."""
from __future__ import annotations

import logging
import re
import time
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
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_change
from homeassistant.util import dt as dt_util

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
    PANEL_ELEMENT,
    PANEL_ICON,
    PANEL_JS_URL,
    PANEL_TITLE,
    PANEL_URL_PATH,
    SERVICE_LOG,
    SERVICE_EXPORT,
    SERVICE_ODOMETER,
    SERVICE_PROFILE,
    SIGNAL_UPDATED,
)
from .schedule import DEFAULT_ACTION, ItemStatus, compute, load_schedule, pace_per_day, summary
from . import export as gexport
from . import stats as gstats
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
    odometer_entity: str | None
    fuel_entity: str | None
    tank_l: float | None
    odometer: float | None = None           # last known; None = never read (not zero)
    odometer_as_of: str | None = None
    statuses: list[ItemStatus] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    storage: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    pace: float | None = None              # miles per day from the log
    battery_entity: str | None = None
    stats: dict[str, Any] = field(default_factory=gstats.empty)
    stats_saved_l: float | None = None
    stats_saved_at: float = 0.0
    batt_last: float | None = None
    assumed_mpg: float | None = None
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
        self._known_odometer(settings.get("odometer"), entries)
        self.assumed_mpg = settings.get("mpg") if isinstance(settings.get("mpg"), (int, float)) else None
        self.statuses = compute(self.schedule, entries, self.odometer, dt_util.now().date(),
                                settings.get("profile", {}), settings.get("months", {}))
        self.summary = summary(self.statuses)
        today = dt_util.now().date()
        self.pace = pace_per_day(entries, self.odometer, today)
        self.points = sorted([e["date"], e["odometer"]] for e in entries
                             if e.get("odometer") is not None and e.get("date"))
        async_dispatcher_send(self.hass, SIGNAL_UPDATED.format(self.entry_id))

    def _known_odometer(self, typed: Any, entries: list[dict[str, Any]]) -> None:
        """Without a sensor the odometer is the newest thing anyone wrote down: a typed reading or
        the highest logged mileage. With one, a typed reading only ever moves it forward."""
        cands = []
        if isinstance(typed, dict) and isinstance(typed.get("miles"), (int, float)):
            cands.append((float(typed["miles"]), typed.get("at") or typed.get("date")))
        if not self.odometer_entity:
            for e in entries:
                if e.get("odometer") is not None:
                    cands.append((float(e["odometer"]), e.get("date")))
        if not cands:
            return
        miles, when = max(cands, key=lambda c: c[0])
        if self.odometer is None or miles > self.odometer or not self.odometer_entity:
            self.odometer, self.odometer_as_of = miles, when

    def economy(self) -> dict[str, Any]:
        last = self.stats.get("fuel_last") or {}
        e = gstats.economy(self.stats, self.tank_l, self.odometer, last.get("litres"))
        mpg, basis = e["mpg"], "learned"
        if mpg is None and self.assumed_mpg:
            mpg, basis = self.assumed_mpg, "assumed"
        litres = last.get("litres")
        return {"mpg": e["mpg"], "segments": e["segments"], "range": gstats.range_miles(litres, mpg),
                "range_basis": basis if mpg else None, "litres": litres, "as_of": last.get("at"),
                "percent": round(litres / self.tank_l * 100, 1) if litres is not None and self.tank_l else None}

    def device_info(self) -> dict[str, Any]:
        """Join the device that owns the odometer (e.g. the OBD dongle) so the vehicle is one device."""
        ent = er.async_get(self.hass).async_get(self.odometer_entity) if self.odometer_entity else None
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
                       s.get(CONF_ODOMETER) or None, s.get(CONF_FUEL) or None, tank)
    rt.battery_entity = s.get(CONF_BATTERY) or None
    runtimes(hass)[entry.entry_id] = rt
    try:
        rt.stats = await hass.async_add_executor_job(store.stats)
        last = rt.stats.get("fuel_last") or {}
        rt.stats_saved_l = last.get("litres")
    except GarageError as err:
        _LOGGER.warning("Garage %s: stats unreadable: %s", rt.name, err)

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
    _track_learning(hass, entry, rt)
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


# ------------------------------------------------------------------ learning from the sensors

def _num(state) -> float | None:
    if state is None or state.state in ("unknown", "unavailable", "", None):
        return None
    try:
        return float(state.state)
    except ValueError:
        return None


def _track_learning(hass: HomeAssistant, entry: ConfigEntry, rt: GarageRuntime) -> None:
    """Fill-ups from the tank sensor, the battery at rest from the voltage sensor."""

    async def save(force: bool = False) -> None:
        last = (rt.stats.get("fuel_last") or {}).get("litres")
        now = time.monotonic()
        moved = last is not None and (rt.stats_saved_l is None or abs(last - rt.stats_saved_l) >= 2.0)
        if not (force or moved or now - rt.stats_saved_at > 900):
            return
        try:
            await hass.async_add_executor_job(rt.store.save_stats, rt.stats)
            rt.stats_saved_l, rt.stats_saved_at = last, now
        except GarageError as err:
            _LOGGER.debug("Garage %s: stats not saved: %s", rt.name, err)

    @callback
    def fuel_changed(event) -> None:
        litres = _num(event.data.get("new_state"))
        if litres is None:
            if _num(event.data.get("old_state")) is not None:   # the truck went to sleep
                hass.async_create_task(save(force=True))
            return
        unit = (event.data["new_state"].attributes or {}).get("unit_of_measurement")
        if unit in ("gal", "US gal"):
            litres *= gstats.L_PER_GAL
        ev = gstats.on_fuel(rt.stats, litres, rt.odometer, dt_util.utcnow().isoformat(timespec="seconds"), rt.tank_l)
        if ev:
            _LOGGER.info("Garage %s: fill-up %.1f L -> %.1f L at %s", rt.name, ev["before"], ev["after"], ev["odometer"])
        hass.async_create_task(save(force=bool(ev)))
        async_dispatcher_send(hass, SIGNAL_UPDATED.format(rt.entry_id))

    @callback
    def battery_changed(event) -> None:
        v = _num(event.data.get("new_state"))
        if v is not None:
            rt.batt_last = v
            return
        if rt.batt_last is not None and _num(event.data.get("old_state")) is not None:
            gstats.on_battery_sleep(rt.stats, rt.batt_last, dt_util.utcnow().isoformat(timespec="seconds"))
            rt.batt_last = None
            hass.async_create_task(save(force=True))
            async_dispatcher_send(hass, SIGNAL_UPDATED.format(rt.entry_id))

    if rt.fuel_entity:
        if not rt.stats.get("fuel_last"):
            litres = _num(hass.states.get(rt.fuel_entity))
            if litres is not None:
                gstats.on_fuel(rt.stats, litres, rt.odometer, dt_util.utcnow().isoformat(timespec="seconds"), rt.tank_l)
                hass.async_create_task(save(force=True))
                # The sensors have already published by now; tell them the tank is known.
                async_dispatcher_send(hass, SIGNAL_UPDATED.format(rt.entry_id))
        entry.async_on_unload(async_track_state_change_event(hass, [rt.fuel_entity], fuel_changed))
    if rt.battery_entity:
        rt.batt_last = _num(hass.states.get(rt.battery_entity))
        entry.async_on_unload(async_track_state_change_event(hass, [rt.battery_entity], battery_changed))


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
        websocket_api.async_register_command(hass, ws_export)
        websocket_api.async_register_command(hass, ws_odometer)
        hass.http.register_view(GarageImageView())
        hass.http.register_view(GarageRecordView())
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
        "economy": rt.economy(), "battery_entity": rt.battery_entity,
        "refuels": (rt.stats.get("refuels") or [])[-12:], "rest": (rt.stats.get("rest") or [])[-40:],
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
    async def set_odometer(call: ServiceCall) -> None:
        rt = _rt(hass, call.data.get("vehicle"))
        try:
            await hass.async_add_executor_job(rt.store.set_odometer, call.data["miles"])
        except GarageError as err:
            raise HomeAssistantError(str(err)) from err
        await rt.async_refresh()

    hass.services.async_register(
        DOMAIN, SERVICE_ODOMETER, set_odometer,
        schema=vol.Schema({vol.Optional("vehicle"): cv.string, vol.Required("miles"): vol.Coerce(float)}),
    )

    async def export_record(call: ServiceCall) -> ServiceResponse:
        rt = _rt(hass, call.data.get("vehicle"))
        r = await async_export(rt, call.data.get("costs", False), True)
        if r["save_error"]:
            raise HomeAssistantError(f"Service record not saved: {r['save_error']}")
        return {"folder": r["saved"], "files": list(r["names"].values())}

    hass.services.async_register(
        DOMAIN, SERVICE_EXPORT, export_record,
        schema=vol.Schema({vol.Optional("vehicle"): cv.string, vol.Optional("costs", default=False): cv.boolean}),
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
    vehicles = [{"entry_id": r.entry_id, "name": r.name,
                 "summary": {k: r.summary.get(k, 0) for k in ("over", "soon", "nolog")}} for r in rts.values()]
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


# NOT "id": the websocket protocol owns that key (it is the message counter), so a
# command field named id is silently replaced by an integer before it reaches us.
@websocket_api.websocket_command({vol.Required("type"): "garage/update", vol.Optional("entry_id"): str,
                                  vol.Required("log_id"): str, vol.Required("entry"): dict})
@websocket_api.async_response
async def ws_update(hass, connection, msg):
    def work(rt, name):
        data = dict(msg["entry"])
        if "items" in data:
            data["items"] = _items_arg(rt, data["items"] or [])
        return rt.store.update(msg["log_id"], data, name)
    await _ws_write(hass, connection, msg, work)


@websocket_api.websocket_command({vol.Required("type"): "garage/delete", vol.Optional("entry_id"): str,
                                  vol.Required("log_id"): str})
@websocket_api.async_response
async def ws_delete(hass, connection, msg):
    await _ws_write(hass, connection, msg, lambda rt, name: rt.store.delete(msg["log_id"], name))


@websocket_api.websocket_command({vol.Required("type"): "garage/set_profile", vol.Optional("entry_id"): str,
                                  vol.Required("n"): int, vol.Required("profile"): vol.In(["normal", "severe"])})
@websocket_api.async_response
async def ws_profile(hass, connection, msg):
    await _ws_write(hass, connection, msg, lambda rt, name: rt.store.set_profile(msg["n"], msg["profile"]))


async def async_export(rt: GarageRuntime, costs: bool = False, save: bool = True) -> dict[str, Any]:
    """The service record for a sale: printable HTML and a CSV, also saved under exports/."""
    hass = rt.hass
    # Recompute first: right after a restart the statuses can still be empty, and a record
    # with an empty status table looks like a vehicle with nothing on its schedule.
    await rt.async_refresh()
    if not rt.statuses:
        raise HomeAssistantError(rt.error or "The schedule isn't loaded yet; try again in a moment.")

    def work():
        entries = rt.store.entries() if rt.store.status()["has_log"] else []
        settings = rt.store.settings() if rt.store.status()["exists"] else {}
        return entries, settings

    entries, settings = await hass.async_add_executor_job(work)
    today = dt_util.now().date()
    info = settings.get("vehicle") if isinstance(settings.get("vehicle"), dict) else {}
    title = gexport.vehicle_title(rt.name, info)
    page = gexport.build_html(rt.schedule, entries, rt.statuses, rt.name, rt.odometer, today, info, costs)
    table = gexport.build_csv(rt.schedule, entries, costs)
    names = {"html": gexport.filename(title, today, "html"), "csv": gexport.filename(title, today, "csv")}
    saved, save_error = None, None
    if save:
        try:
            saved = await hass.async_add_executor_job(
                rt.store.save_export, {names["html"]: page, names["csv"]: table})
        except (GarageError, OSError) as err:
            save_error = str(err)
    return {"html": page, "csv": table, "names": names, "saved": saved, "save_error": save_error,
            "has_costs": gexport.has_costs(entries)}


@websocket_api.websocket_command({vol.Required("type"): "garage/export", vol.Optional("entry_id"): str,
                                  vol.Optional("costs", default=False): bool,
                                  vol.Optional("save", default=True): bool})
@websocket_api.async_response
async def ws_export(hass, connection, msg):
    try:
        rt = _rt(hass, msg.get("entry_id"))
        result = await async_export(rt, msg["costs"], msg["save"])
    except (GarageError, HomeAssistantError) as err:
        connection.send_error(msg["id"], "failed", str(err))
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command({vol.Required("type"): "garage/set_odometer", vol.Optional("entry_id"): str,
                                  vol.Required("miles"): vol.Coerce(float)})
@websocket_api.async_response
async def ws_odometer(hass, connection, msg):
    await _ws_write(hass, connection, msg, lambda rt, name: rt.store.set_odometer(msg["miles"]))


class GarageRecordView(HomeAssistantView):
    """The service record as a page (or CSV). Opened from the panel through a signed path."""

    url = "/api/garage/{entry_id}/record.{ext}"
    name = "api:garage:record"
    requires_auth = True

    async def get(self, request, entry_id, ext):
        from aiohttp import web

        hass = request.app["hass"]
        rt = runtimes(hass).get(entry_id)
        if rt is None or ext not in ("html", "csv"):
            return web.Response(status=404)
        r = await async_export(rt, request.query.get("costs") == "1", save=False)
        headers = {"Cache-Control": "no-store"}
        if ext == "csv":
            headers["Content-Disposition"] = f'attachment; filename="{r["names"]["csv"]}"'
            return web.Response(text=r["csv"], content_type="text/csv", charset="utf-8", headers=headers)
        return web.Response(text=r["html"], content_type="text/html", charset="utf-8", headers=headers)


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
