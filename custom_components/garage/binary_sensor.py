"""binary_sensor.<vehicle>_service_due: on while anything is overdue or due soon."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_UPDATED


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    add([ServiceDue(hass.data[DOMAIN][entry.entry_id])])


class ServiceDue(BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_name = "Service due"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, rt) -> None:
        self.rt = rt
        self._attr_unique_id = f"{rt.entry_id}_due"
        self._attr_device_info = rt.device_info()

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_UPDATED.format(self.rt.entry_id),
                                                      self._updated))

    @callback
    def _updated(self) -> None:
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return bool(self.rt.statuses)

    @property
    def is_on(self) -> bool:
        s = self.rt.summary
        return bool(s.get("over") or s.get("soon"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        s = self.rt.summary
        return {"overdue": s.get("over"), "soon": s.get("soon"), "items": s.get("overdue_items")}
