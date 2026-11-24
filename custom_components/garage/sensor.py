"""Garage sensors: last-known odometer, one 'due in' sensor per item, overdue count, next service."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN, UnitOfLength
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import DistanceConverter

from .const import DOMAIN, MAX_ODO_JUMP, SIGNAL_UPDATED

ICONS = {"over": "mdi:wrench-clock", "soon": "mdi:wrench-clock-outline", "nolog": "mdi:help-circle-outline",
         "ok": "mdi:wrench-check-outline"}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    rt = hass.data[DOMAIN][entry.entry_id]
    ents: list[SensorEntity] = [OdometerSensor(rt), OverdueSensor(rt), NextServiceSensor(rt)]
    ents += [ItemSensor(rt, it) for it in rt.schedule["items"]]
    add(ents)


class _Base(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, rt, key: str) -> None:
        self.rt = rt
        self._attr_unique_id = f"{rt.entry_id}_{key}"
        self._attr_device_info = rt.device_info()

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_UPDATED.format(self.rt.entry_id),
                                                      self._updated))

    @callback
    def _updated(self) -> None:
        self.async_write_ha_state()


class OdometerSensor(_Base, RestoreSensor):
    """The odometer that survives the dongle sleeping. Missing is never zero."""

    _attr_name = "Odometer (last known)"
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfLength.MILES
    _attr_suggested_display_precision = 0
    _attr_icon = "mdi:counter"

    def __init__(self, rt) -> None:
        super().__init__(rt, "odometer")
        self._pending: float | None = None
        self._pending_hits = 0

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_sensor_data()
        last_state = await self.async_get_last_state()
        if last and last.native_value is not None:
            try:
                self.rt.odometer = float(last.native_value)
                if last_state is not None:
                    self.rt.odometer_as_of = last_state.attributes.get("as_of")
            except (TypeError, ValueError):
                pass
        self.async_on_remove(async_track_state_change_event(self.hass, [self.rt.odometer_entity], self._source))
        src = self.hass.states.get(self.rt.odometer_entity)
        if src is not None:
            self._accept(src)
        self._attr_native_value = self.rt.odometer

    @callback
    def _source(self, event: Event) -> None:
        new = event.data.get("new_state")
        if new is not None and self._accept(new):
            self.hass.async_create_task(self.rt.async_refresh())

    def _accept(self, state) -> bool:
        if state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN, "", None):
            return False
        try:
            value = float(state.state)
        except ValueError:
            return False
        unit = state.attributes.get("unit_of_measurement")
        if unit and unit != UnitOfLength.MILES:
            try:
                value = DistanceConverter.convert(value, unit, UnitOfLength.MILES)
            except Exception:  # noqa: BLE001 - an unknown unit is not a reading
                return False
        if value <= 0:
            return False
        cur = self.rt.odometer
        if cur is not None:
            if value < cur - 1:              # odometers do not run backwards; a glitch frame
                return False
            if value - cur > MAX_ODO_JUMP:   # hold a big jump until it repeats
                if self._pending is not None and abs(value - self._pending) < 50:
                    self._pending_hits += 1
                else:
                    self._pending, self._pending_hits = value, 1
                if self._pending_hits < 3:
                    return False
            if abs(value - cur) < 0.05:
                return False
        self._pending, self._pending_hits = None, 0
        self.rt.odometer = round(value, 1)
        self.rt.odometer_as_of = dt_util.utcnow().isoformat(timespec="seconds")
        self._attr_native_value = self.rt.odometer
        if self.hass is not None and self.entity_id:
            self.async_write_ha_state()
        return True

    @property
    def native_value(self):
        return self.rt.odometer

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"as_of": self.rt.odometer_as_of, "source": self.rt.odometer_entity}


class ItemSensor(_Base):
    """Miles until an item is due. Negative = overdue. Unknown (never 0) when it was never logged."""

    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfLength.MILES
    _attr_suggested_display_precision = 0

    def __init__(self, rt, item: dict[str, Any]) -> None:
        super().__init__(rt, f"item_{item['n']}")
        self.n = int(item["n"])
        self._attr_name = f"{item['short']} due in"

    def _st(self):
        return next((s for s in self.rt.statuses if s.n == self.n), None)

    @property
    def native_value(self):
        st = self._st()
        return None if st is None else st.remaining

    @property
    def icon(self) -> str:
        st = self._st()
        return ICONS.get(st.status if st else "ok", "mdi:wrench")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        st = self._st()
        if st is None:
            return {}
        d = st.as_dict()
        d.pop("history", None)
        d["logged"] = len(st.history)
        return d


class OverdueSensor(_Base):
    _attr_name = "Services overdue"
    _attr_icon = "mdi:wrench-clock"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "items"

    def __init__(self, rt) -> None:
        super().__init__(rt, "overdue")

    @property
    def available(self) -> bool:
        return bool(self.rt.statuses)

    @property
    def native_value(self):
        return self.rt.summary.get("over")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        s = self.rt.summary
        return {
            "soon": s.get("soon"), "no_record": s.get("nolog"), "ok": s.get("ok"),
            "overdue": [x.short for x in self.rt.statuses if x.status == "over"],
            "due_soon": [x.short for x in self.rt.statuses if x.status == "soon"],
            "never_logged": [x.short for x in self.rt.statuses if x.status == "nolog"],
            "storage": self.rt.storage.get("mounted"), "error": self.rt.error,
        }


class NextServiceSensor(_Base):
    _attr_name = "Next service"
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, rt) -> None:
        super().__init__(rt, "next")

    @property
    def native_value(self):
        nxt = self.rt.summary.get("next")
        return nxt["short"] if nxt else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        nxt = self.rt.summary.get("next") or {}
        return {"item": nxt.get("name"), "n": nxt.get("n"), "miles_left": nxt.get("remaining"), "eta": nxt.get("eta")}
