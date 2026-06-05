# Changelog

All notable changes to **IR Remote Buttons** are documented here.

---

## [0.4.0] — 2026-06-05

Initial public release via HACS.

### Added

#### Core integration
- Config flow: pick any `infrared.*` receiver entity and name the remote.
- **Config subentries** for buttons — each learned button is a named sub-entry,
  so adding and removing buttons works through the standard HA device page
  without restarting the integration.
- **Event entity** (`event.<remote_name>_buttons`) fires one event per button
  press. Every learned button gets both a single-press variant (`power`) and a
  double-click variant (`power_2x`).
- **IR fingerprinting**: NEC protocol is decoded first
  (`nec:<address>:<command>`); non-standard remotes fall back to raw
  space-width quantization over the timing list.

#### Learn flow
- **Double-confirm capture**: the button must be pressed twice and both presses
  must produce matching fingerprints before the button is saved. Eliminates
  noise captures and near-miss misfires on remotes with similar codes.
- **Pause step** between the two presses — a "Signal locked in" screen requires
  an explicit Submit before the second listen begins, preventing repeat frames
  from the first press polluting the second capture.
- **Manual code entry**: paste a raw bit string (`010101…`) or a decoded NEC
  code (`nec:0101:0f`) to add a button without hardware. Useful for migrating
  from a known command map.
- **Timeout handling**: if no signal arrives within the configured window the
  flow surfaces a friendly "No signal detected" screen with a retry option.
- **Mismatch handling**: when the two presses don't agree the flow offers a
  "Try again" path instead of silently failing.

#### Click engine
- **Debounce window**: repeat frames fired while a button is held are ignored.
- **Double-click detection**: two presses within the double-click window fire
  a `<button>_2x` event.
- **Immediate vs. delayed single press**: configurable. In delayed mode the
  single-press event waits for the double-click window to expire before firing
  (lower false-double-click rate, adds latency). In immediate mode both events
  can fire for the same physical gesture.

#### Configuration options (all runtime-tunable via the integration's Options)
| Option | Default |
|--------|---------|
| Debounce window | 0.25 s |
| New-press gap | 0.50 s |
| Double-click window | 2.0 s |
| Learn timeout | 60 s |
| Fire single press immediately | off |

#### ESPHome firmware
- `esphome/ir-receiver-esp32.yaml` — recommended; uses the hardware RMT
  peripheral for accurate, jitter-free capture.
- `esphome/ir-receiver-esp8266.yaml` — bit-bang fallback with tuned defaults
  (`idle: 40ms`, `buffer_size: 4kb`, `tolerance: 35%`) that resolved
  intermittent capture failures on an 8-button 33-bit non-standard remote.

#### Icons
- `icon.png` (512×512): displayed by HACS in the store listing and by HA on
  the integration card.
- `icons.json`: maps the `event.buttons` entity to `mdi:remote` so HA shows
  the correct MDI icon in entity lists and dashboard cards.

#### Documentation
- Full install, configuration, and automation guide in `README.md`.
- UI walkthrough with annotated screenshots of every step in the learn flow.
- ESPHome receiver tuning guide explaining how `idle`, `buffer_size`, and
  `tolerance` affect capture quality — and the symptoms of getting them wrong.

---

## [0.3.0] — 2026-06-05

- **Manual button entry**: new "Enter code manually" path in the add-button
  flow accepts raw bit strings and `nec:ADDR:CMD` codes.
- **ESP8266 firmware tuning**: raised `idle` to 40 ms, `buffer_size` to 4 kb,
  `tolerance` to 35% to fix split-frame and mismatch failures on long
  non-standard codes.

## [0.2.2] — 2026-06-05

- **Fix capture regression**: reverted settle-based capture (introduced in
  0.2.1) which stored the last NEC repeat frame instead of the initial frame,
  causing consistent fingerprint mismatches. Restored first-signal-wins using
  the configured `debounce_window` option instead of a hardcoded 0.15 s value.

## [0.2.1] — 2026-06-05

- Added **pause / ready step** between the two confirmation presses so repeat
  frames from the first press cannot bleed into the second capture window.

## [0.2.0] — 2026-06-05

- **Double-confirm learn flow**: button must be pressed twice with matching
  fingerprints before it is saved.
- Updated timing defaults to better suit real-world IR hardware:
  debounce 0.25 s, new-press gap 0.50 s, double-click window 2.0 s,
  learn timeout 60 s, immediate single press off.

## [0.1.0] — 2026-06-05

- Initial integration: receiver picker config flow, event entity, basic
  single-press learn flow, configurable timing options.
