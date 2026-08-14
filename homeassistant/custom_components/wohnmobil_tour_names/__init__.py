"""Persistent tour names for the Wohnmobil Tours custom card."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.storage import Store

DOMAIN = "wohnmobil_tour_names"
STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.names"
SENSOR_ENTITY_ID = "sensor.wohnmobil_tour_names"

SET_NAME_SCHEMA = vol.Schema(
    {
        vol.Required("tour"): vol.Coerce(int),
        vol.Required("name"): str,
    }
)
DELETE_NAME_SCHEMA = vol.Schema({vol.Required("tour"): vol.Coerce(int)})


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    loaded = await store.async_load()
    names = dict(loaded.get("names", {})) if isinstance(loaded, dict) else {}

    def update_state() -> None:
        hass.states.async_set(
            SENSOR_ENTITY_ID,
            len(names),
            {
                "friendly_name": "Wohnmobil Tournamen",
                "names": dict(sorted(names.items(), key=lambda item: int(item[0]))),
            },
        )

    async def persist() -> None:
        await store.async_save({"names": names})
        update_state()

    async def set_name(call: ServiceCall) -> None:
        tour = str(int(call.data["tour"]))
        name = str(call.data["name"]).strip()
        if not name:
            names.pop(tour, None)
        else:
            names[tour] = name
        await persist()

    async def delete_name(call: ServiceCall) -> None:
        names.pop(str(int(call.data["tour"])), None)
        await persist()

    hass.services.async_register(DOMAIN, "set_name", set_name, schema=SET_NAME_SCHEMA)
    hass.services.async_register(DOMAIN, "delete_name", delete_name, schema=DELETE_NAME_SCHEMA)
    update_state()
    return True
