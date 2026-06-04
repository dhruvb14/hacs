from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable

from homeassistant.core import HomeAssistant, callback

from .const import (
    DEFAULT_DEBOUNCE_WINDOW,
    DEFAULT_DOUBLE_CLICK_WINDOW,
    DEFAULT_IMMEDIATE_SINGLE,
    DEFAULT_NEW_PRESS_WINDOW,
)

try:
    from infrared_protocols.commands.nec import NECCommand

    _HAS_NEC = True
except ImportError:
    _HAS_NEC = False


def fingerprint(timings: list[int]) -> str:
    """Return a stable string fingerprint for a received IR signal.

    Prefers a real NEC protocol decode (robust to timing jitter); falls back
    to a raw space-width quantization for non-standard remotes.
    """
    if _HAS_NEC:
        try:
            cmd = NECCommand.from_raw_timings(timings)
            if cmd is not None:
                return f"nec:{cmd.address:04x}:{cmd.command:02x}"
        except Exception:
            pass

    # Raw fallback: skip 2-value header + trailing pulse; quantize each space.
    # Space > 1000 µs = logical 1 (matches the original ESPHome lambda threshold).
    bits: list[str] = []
    for i in range(2, len(timings) - 1, 2):
        space = abs(timings[i + 1]) if i + 1 < len(timings) else 0
        bits.append("1" if space > 1000 else "0")
    return "raw:" + "".join(bits)


def suggest_name(fp: str | None) -> str:
    """Suggest a human-readable button name from a fingerprint string."""
    if fp is None:
        return "button"
    if fp.startswith("nec:"):
        parts = fp.split(":")
        if len(parts) == 3:
            return f"nec_{parts[1]}_{parts[2]}"
    return "button"


@dataclass
class ClickResult:
    """A confirmed button press event ready to be fired."""

    event_type: str
    fingerprint: str


class ClickEngine:
    """Debounce + double-click state machine.

    Ports the original ESPHome on_raw lambda logic into Python.

    In immediate mode (default): single press fires right away; a matching
    second press within the double-click window fires an additional _2x event.

    In delayed mode: single press is held for double_click_window seconds
    before firing; a second press within that window cancels the timer and
    fires _2x instead. Adds latency equal to double_click_window.

    All timing windows are configurable to suit different remote hardware.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        debounce_window: float = DEFAULT_DEBOUNCE_WINDOW,
        new_press_window: float = DEFAULT_NEW_PRESS_WINDOW,
        double_click_window: float = DEFAULT_DOUBLE_CLICK_WINDOW,
        immediate_single: bool = DEFAULT_IMMEDIATE_SINGLE,
    ) -> None:
        self._hass = hass
        self._debounce_window = debounce_window
        self._new_press_window = new_press_window
        self._double_click_window = double_click_window
        self._immediate_single = immediate_single

        self._last_t: float = 0.0
        self._last_fp: str | None = None
        self._first_press_t: float | None = None
        self._pending_handle: asyncio.TimerHandle | None = None
        self._fire_cb: Callable[[ClickResult], None] | None = None

    def set_fire_callback(self, cb: Callable[[ClickResult], None]) -> None:
        """Register the callback invoked when a delayed single press fires."""
        self._fire_cb = cb

    def cancel(self) -> None:
        """Cancel any pending delayed single-press timer."""
        if self._pending_handle is not None:
            self._pending_handle.cancel()
            self._pending_handle = None

    @callback
    def process(self, fp: str, name: str) -> ClickResult | None:
        """Process a fingerprinted signal.

        Returns a ClickResult immediately when in immediate_single mode, or
        when a double-click is detected. Returns None in delayed mode (result
        delivered later via the fire callback) or when the signal is filtered.
        """
        now = self._hass.loop.time()
        gap = now - self._last_t

        # Debounce: ignore repeat/bounce frames within the debounce window.
        if gap < self._debounce_window:
            self._last_t = now
            return None

        self._last_t = now

        is_same_button = fp == self._last_fp
        is_within_double_click = (
            self._first_press_t is not None
            and (now - self._first_press_t) < self._double_click_window
        )
        is_new_gesture = gap >= self._new_press_window

        if is_same_button and is_within_double_click and is_new_gesture:
            # Double-click confirmed.
            self.cancel()
            self._first_press_t = None
            self._last_fp = None
            return ClickResult(event_type=f"{name}_2x", fingerprint=fp)

        # New press (different button, or gap too large, or first press).
        self._first_press_t = now
        self._last_fp = fp
        result = ClickResult(event_type=name, fingerprint=fp)

        if self._immediate_single:
            return result

        # Delayed mode: hold the single press until the double-click window expires.
        self.cancel()
        self._pending_handle = self._hass.loop.call_later(
            self._double_click_window,
            self._fire_delayed,
            result,
        )
        return None

    def _fire_delayed(self, result: ClickResult) -> None:
        self._pending_handle = None
        self._first_press_t = None
        self._last_fp = None
        if self._fire_cb is not None:
            self._fire_cb(result)
