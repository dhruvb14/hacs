# dhruvb14 custom HACS integrations

Custom Home Assistant integrations distributed via [HACS](https://hacs.xyz).

## Integrations

| Integration | Description | HA Version |
|---|---|---|
| [IR Remote Buttons](#ir-remote-buttons-ir_remote) | Learn any IR remote and use its buttons as automation triggers | 2026.6.0+ |

---

## IR Remote Buttons (`ir_remote`)

Point any IR remote at an ESPHome (or other) infrared receiver. Learn buttons
one at a time through the UI. Each button press fires an **event entity** that
automations can trigger on — including double-click variants.

### Requirements

- Home Assistant **2026.6.0** or later (requires the new `infrared` entity platform)
- An infrared receiver adopted into HA as an `infrared.*` entity
  (ESPHome with `ir_rf_proxy`, Broadlink, or the `kitchen_sink` demo)
- HACS installed

### Installation via HACS

1. In HACS, go to **Integrations → ⋮ → Custom repositories**.
2. Add `https://github.com/dhruvb14/hacs` as category **Integration**.
3. Search for **IR Remote Buttons** and click **Download**.
4. Restart Home Assistant.
5. Go to **Settings → Devices & Services → Add Integration** and search for
   **IR Remote Buttons**.

### Configuration

1. **Add integration** — select your infrared receiver entity and give the
   remote a name (e.g. "Living room TV remote").
2. **Add buttons** — on the integration's device page, click **Add button**.
   Point your remote at the receiver and press the button when prompted; name
   it (e.g. `power`, `vol_up`).
3. Repeat for each button you want to use in automations.

Each time you add a button the integration reloads so the event entity's
`event_types` list is updated.

### Using in automations

The integration creates one **event** entity per configured receiver. Use it
as an automation trigger:

```yaml
trigger:
  - platform: state
    entity_id: event.living_room_tv_remote_buttons
    attribute: event_type
    to: "power"           # single press
    # to: "power_2x"      # double-click
```

Or via the UI: **Trigger → Entity → Event entity → event_type equals `power`**.

### Options (timing tuning)

Open the integration's options to adjust timing windows to suit your hardware:

| Option | Default | Description |
|---|---|---|
| Debounce window | 0.15 s | Signals faster than this are treated as repeats |
| New-press gap | 0.25 s | Minimum gap before the same button counts as a new press |
| Double-click window | 1.3 s | Maximum gap between two presses to count as double-click |
| Learn timeout | 20 s | How long the "Add button" flow waits for a signal |
| Fire single press immediately | ✓ | When off, single press waits for the double-click window (lower false-double-click rate, adds latency) |

---

## ESPHome Firmware

See [`esphome/`](esphome/) for ready-to-flash configurations:

- [`ir-receiver-esp32.yaml`](esphome/ir-receiver-esp32.yaml) — **recommended**;
  uses the hardware RMT peripheral for accurate, jitter-free capture.
- [`ir-receiver-esp8266.yaml`](esphome/ir-receiver-esp8266.yaml) — bit-bang
  fallback; works but is more sensitive to RF noise and CPU load.

Both configs use `!secret` for all credentials. Copy
[`esphome/secrets.yaml.example`](esphome/secrets.yaml.example) to
`esphome/secrets.yaml` and fill in your values before flashing.

---

## Testing

### Without hardware (recommended for development)

Enable the `kitchen_sink` integration in your HA dev instance
(`configuration.yaml`):

```yaml
kitchen_sink:
```

This registers a `DemoInfraredReceiver` as `infrared.demo_ir_receiver`. Point
the config flow at it, then drive signals in the HA developer console:

```python
# Developer Tools → Template (or a script) — fire a fake signal
hass.components.infrared._handle_received_signal(
    "infrared.demo_ir_receiver",
    InfraredReceivedSignal(timings=[9000, -4500, 560, -1690, 560, -560, 560])
)
```

### Unit tests (no HA required)

The `ClickEngine` and `fingerprint()` function can be tested without any HA
machinery:

```bash
pip install pytest
pytest tests/components/ir_remote/test_engine.py -v
```

Tests cover:

- `fingerprint()` — NEC decode path, raw space-width quantization, edge cases
- `ClickEngine` (immediate mode) — first press, debounce, second-press-after-window,
  double-click detection, boundary conditions
- `ClickEngine` (delayed mode) — returns `None` on first press, fires `_2x` immediately

### Integration tests (requires HA test framework)

Follow the standard HA custom component test setup — mock the `infrared`
component using the patterns from `tests/components/infrared/common.py` and
`tests/components/lg_infrared/` in the HA core repo.
