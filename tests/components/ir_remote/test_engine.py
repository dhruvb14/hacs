"""Unit tests for the ir_remote engine — no HA machinery required."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.ir_remote.engine import (
    ClickEngine,
    ClickResult,
    fingerprint,
    suggest_name,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeClock:
    """Monotonic clock substitute for ClickEngine tests."""

    def __init__(self) -> None:
        self._t = 0.0

    def time(self) -> float:
        return self._t

    def advance(self, seconds: float) -> None:
        self._t += seconds


def make_hass(clock: FakeClock) -> MagicMock:
    hass = MagicMock()
    hass.loop.time.side_effect = clock.time
    # call_later is used in delayed mode; capture the callback.
    hass.loop.call_later.side_effect = lambda delay, fn, *args: fn  # not called here
    return hass


# NEC-like timing pattern (simplified: header pair + 32 bit-pairs)
NEC_HEADER = [9000, -4500]
NEC_ONE = [560, -1690]
NEC_ZERO = [560, -560]


def make_nec_timings(address: int, command: int) -> list[int]:
    """Build a minimal NEC-shaped timing list (not real NEC, just plausible)."""
    bits: list[int] = list(NEC_HEADER)
    for byte_val in [address, address ^ 0xFF, command, command ^ 0xFF]:
        for shift in range(8):
            bits += NEC_ONE if (byte_val >> shift) & 1 else NEC_ZERO
    bits.append(560)  # trailing pulse
    return bits


# ---------------------------------------------------------------------------
# fingerprint()
# ---------------------------------------------------------------------------


class TestFingerprint:
    def test_raw_all_zeros(self) -> None:
        # All spaces ≤ 1000 µs → all-zero bit string.
        timings = [9000, -4500, 560, -500, 560, -500, 560]
        fp = fingerprint(timings)
        assert fp.startswith("raw:")
        assert "1" not in fp.replace("raw:", "")

    def test_raw_all_ones(self) -> None:
        # All spaces > 1000 µs → all-one bit string.
        timings = [9000, -4500, 560, -1690, 560, -1690, 560]
        fp = fingerprint(timings)
        assert fp.startswith("raw:")
        assert "0" not in fp.replace("raw:", "")

    def test_raw_mixed(self) -> None:
        timings = [9000, -4500, 560, -1690, 560, -500, 560, -1690, 560]
        fp = fingerprint(timings)
        assert fp == "raw:101"

    def test_deterministic(self) -> None:
        timings = [9000, -4500, 560, -1690, 560, -500, 560]
        assert fingerprint(timings) == fingerprint(timings)

    def test_empty_timings(self) -> None:
        # Should not raise; short list produces empty raw string.
        fp = fingerprint([])
        assert fp == "raw:"

    def test_single_timing(self) -> None:
        fp = fingerprint([9000])
        assert fp.startswith("raw:")


# ---------------------------------------------------------------------------
# suggest_name()
# ---------------------------------------------------------------------------


class TestSuggestName:
    def test_nec_fingerprint(self) -> None:
        assert suggest_name("nec:0101:08") == "nec_0101_08"

    def test_raw_fingerprint(self) -> None:
        assert suggest_name("raw:10110") == "button"

    def test_none(self) -> None:
        assert suggest_name(None) == "button"

    def test_malformed_nec(self) -> None:
        # Not enough parts → falls back to "button"
        assert suggest_name("nec:only_one") == "button"


# ---------------------------------------------------------------------------
# ClickEngine — immediate mode (default)
# ---------------------------------------------------------------------------


class TestClickEngineImmediate:
    def _engine(self, clock: FakeClock) -> ClickEngine:
        hass = make_hass(clock)
        return ClickEngine(
            hass=hass,
            debounce_window=0.15,
            new_press_window=0.25,
            double_click_window=1.3,
            immediate_single=True,
        )

    def test_first_press_fires(self) -> None:
        clock = FakeClock()
        engine = self._engine(clock)
        result = engine.process("fp1", "power")
        assert result == ClickResult(event_type="power", fingerprint="fp1")

    def test_debounce_ignores_fast_repeat(self) -> None:
        clock = FakeClock()
        engine = self._engine(clock)
        engine.process("fp1", "power")
        clock.advance(0.05)  # < debounce_window (0.15)
        result = engine.process("fp1", "power")
        assert result is None

    def test_second_press_fires_single_after_debounce(self) -> None:
        clock = FakeClock()
        engine = self._engine(clock)
        engine.process("fp1", "power")
        clock.advance(2.0)  # beyond double_click_window
        result = engine.process("fp1", "power")
        assert result == ClickResult(event_type="power", fingerprint="fp1")

    def test_double_click_detected(self) -> None:
        clock = FakeClock()
        engine = self._engine(clock)
        engine.process("fp1", "power")
        clock.advance(0.5)  # within double_click_window, beyond new_press_window
        result = engine.process("fp1", "power")
        assert result == ClickResult(event_type="power_2x", fingerprint="fp1")

    def test_double_click_resets_state(self) -> None:
        clock = FakeClock()
        engine = self._engine(clock)
        engine.process("fp1", "power")
        clock.advance(0.5)
        engine.process("fp1", "power")  # _2x
        clock.advance(2.0)
        # Next press should be a fresh single, not another _2x.
        result = engine.process("fp1", "power")
        assert result == ClickResult(event_type="power", fingerprint="fp1")

    def test_different_button_is_new_press(self) -> None:
        clock = FakeClock()
        engine = self._engine(clock)
        engine.process("fp1", "power")
        clock.advance(0.5)
        result = engine.process("fp2", "mute")
        assert result == ClickResult(event_type="mute", fingerprint="fp2")

    def test_unknown_fingerprint_emits_unknown(self) -> None:
        clock = FakeClock()
        engine = self._engine(clock)
        result = engine.process("fp_unknown", "unknown")
        assert result == ClickResult(event_type="unknown", fingerprint="fp_unknown")

    def test_debounce_boundary_just_outside(self) -> None:
        clock = FakeClock()
        engine = self._engine(clock)
        engine.process("fp1", "power")
        clock.advance(0.16)  # just beyond debounce_window
        result = engine.process("fp1", "power")
        assert result is not None  # should fire

    def test_double_click_window_boundary_just_outside(self) -> None:
        clock = FakeClock()
        engine = self._engine(clock)
        engine.process("fp1", "power")
        clock.advance(1.31)  # just beyond double_click_window
        result = engine.process("fp1", "power")
        assert result == ClickResult(event_type="power", fingerprint="fp1")


# ---------------------------------------------------------------------------
# ClickEngine — delayed mode
# ---------------------------------------------------------------------------


class TestClickEngineDelayed:
    def _engine(self, clock: FakeClock) -> tuple[ClickEngine, list[ClickResult]]:
        hass = MagicMock()
        hass.loop.time.side_effect = clock.time

        fired: list[ClickResult] = []
        pending_calls: list[tuple] = []

        def fake_call_later(delay, fn, *args):
            pending_calls.append((delay, fn, args))
            handle = MagicMock()
            handle.cancel.side_effect = lambda: pending_calls.clear()
            return handle

        hass.loop.call_later.side_effect = fake_call_later

        engine = ClickEngine(
            hass=hass,
            debounce_window=0.15,
            new_press_window=0.25,
            double_click_window=1.3,
            immediate_single=False,
        )
        engine.set_fire_callback(fired.append)

        # Expose pending_calls so tests can drain them.
        engine._pending_calls = pending_calls  # type: ignore[attr-defined]
        return engine, fired

    def test_single_press_returns_none(self) -> None:
        clock = FakeClock()
        engine, fired = self._engine(clock)
        result = engine.process("fp1", "power")
        assert result is None
        assert fired == []

    def test_double_click_returns_2x_immediately(self) -> None:
        clock = FakeClock()
        engine, fired = self._engine(clock)
        engine.process("fp1", "power")
        clock.advance(0.5)
        result = engine.process("fp1", "power")
        assert result == ClickResult(event_type="power_2x", fingerprint="fp1")
        assert fired == []  # callback not involved for double-click

    def test_debounce_in_delayed_mode(self) -> None:
        clock = FakeClock()
        engine, fired = self._engine(clock)
        engine.process("fp1", "power")
        clock.advance(0.05)
        result = engine.process("fp1", "power")
        assert result is None
        assert fired == []
