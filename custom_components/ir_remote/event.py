from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.components.infrared import (
    InfraredReceivedSignal,
    InfraredReceiverConsumerEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_FINGERPRINT,
    CONF_NAME,
    CONF_RECEIVER,
    DEFAULT_DEBOUNCE_WINDOW,
    DEFAULT_DOUBLE_CLICK_WINDOW,
    DEFAULT_IMMEDIATE_SINGLE,
    DEFAULT_NEW_PRESS_WINDOW,
    DOMAIN,
    OPT_DEBOUNCE_WINDOW,
    OPT_DOUBLE_CLICK_WINDOW,
    OPT_IMMEDIATE_SINGLE,
    OPT_NEW_PRESS_WINDOW,
)
from .engine import ClickEngine, ClickResult, fingerprint

EVENT_TYPE_UNKNOWN = "unknown"


def build_event_types(names: list[str]) -> list[str]:
    """Build the full event_types list including _2x variants and unknown."""
    types = [EVENT_TYPE_UNKNOWN]
    for name in names:
        types.append(name)
        types.append(f"{name}_2x")
    return types


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([IrRemoteEventEntity(entry)])


class IrRemoteEventEntity(InfraredReceiverConsumerEntity, EventEntity):
    """Event entity that fires one event per learned button press."""

    _attr_has_entity_name = True
    _attr_translation_key = "buttons"

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._infrared_receiver_entity_id = entry.data[CONF_RECEIVER]
        self._attr_unique_id = f"{entry.entry_id}_buttons"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
        )

        self._codes: dict[str, str] = {
            s.data[CONF_FINGERPRINT]: s.data[CONF_NAME]
            for s in entry.subentries.values()
        }
        self._attr_event_types = build_event_types(list(self._codes.values()))
        self._engine: ClickEngine | None = None

    async def async_added_to_hass(self) -> None:
        opts = self._entry.options
        self._engine = ClickEngine(
            hass=self.hass,
            debounce_window=opts.get(OPT_DEBOUNCE_WINDOW, DEFAULT_DEBOUNCE_WINDOW),
            new_press_window=opts.get(OPT_NEW_PRESS_WINDOW, DEFAULT_NEW_PRESS_WINDOW),
            double_click_window=opts.get(
                OPT_DOUBLE_CLICK_WINDOW, DEFAULT_DOUBLE_CLICK_WINDOW
            ),
            immediate_single=opts.get(OPT_IMMEDIATE_SINGLE, DEFAULT_IMMEDIATE_SINGLE),
        )
        self._engine.set_fire_callback(self._fire_click_result)
        await super().async_added_to_hass()

    async def async_will_remove_from_hass(self) -> None:
        if self._engine is not None:
            self._engine.cancel()
        await super().async_will_remove_from_hass()

    @callback
    def _fire_click_result(self, result: ClickResult) -> None:
        """Invoked by the engine for delayed single-press events."""
        self._trigger_event(result.event_type, {"fingerprint": result.fingerprint})
        self.async_write_ha_state()

    @callback
    def _handle_signal(self, signal: InfraredReceivedSignal) -> None:
        if self._engine is None:
            return
        fp = fingerprint(signal.timings)
        name = self._codes.get(fp, EVENT_TYPE_UNKNOWN)
        result = self._engine.process(fp, name)
        if result is not None:
            self._trigger_event(result.event_type, {"fingerprint": result.fingerprint})
            self.async_write_ha_state()
