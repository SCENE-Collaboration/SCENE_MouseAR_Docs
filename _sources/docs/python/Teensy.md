# Teensy Python Driver

Source: `mouse_ar/ctrl/teensy_python.py`
Hardware reference (pin assignments, wiring, firmware): [Hardware → Teensy](../hardware/Teensy.md)

The `Teensy` class manages the USB-Serial connection to the Teensy board,
runs a background reader thread, calibrates a host↔device clock offset, and
exposes a simple command API used by the `Task` base class.

---

## Python Driver (`Teensy` class)

### Factory method

```python
teensy = Teensy.create(
    serial_port = "/dev/ttyACM0",   # or "COM3" on Windows
    baudrate    = 115200,
    inputs      = [...],            # column names (see teensy.hw.toml)
    outputs     = {...},            # command dict (see teensy.hw.toml)
    csv_expected = 7,               # must match firmware CSV column count
    dummy       = False,            # True → returns DummyTeensy
)
```

Pass `dummy=True` (or `serial_port="dummy"`) to get a `DummyTeensy` that
silently no-ops all calls — useful for development without hardware.

### Lifecycle

```
Teensy.create()
  └─ connect_serial()   open port, clear buffers, send 'stop'

teensy.start()
  ├─ calibrate_offset()  15 sync round-trips, keep 5 best
  ├─ start_read_buffer() launch background reader thread
  └─ write("start")      send 'A' → device begins streaming

teensy.write("water", [dur_ms])   → sends 'W' + int16 payload
teensy.write("TTL")               → sends 'S'
teensy.write("drain")             → sends 'D'

teensy.stop()
  ├─ write("stop")       send 'Z'
  └─ stop_event.set()    terminate reader thread
```

### Data columns

`get_input_data()` returns a NumPy array with columns in order:

```
t_recv | t_host_est | t_host | t_dev_est | t_dev_us |
PhotoDiode | BarcodeTTL | WaterValve | SyncTTL | Lux | LuxTimestamp
```

`t_host_est = offset + t_dev_us / 1e6` — the device timestamp mapped onto the
host clock using the calibrated offset.

---

## Configuration (`teensy.hw.toml`)

The full Teensy configuration is loaded from TOML and passed to `Teensy.create()`:

```toml
[teensy]
dummy        = false
serial_port  = "COM3"
baudrate     = 115200
csv_expected = 7

inputs = [
  "t_host", "t_dev_est", "t_dev_us",
  "PhotoDiode", "BarcodeTTL",
  "WaterValve", "SyncTTL",
  "Lux", "LuxTimestamp",
]

[teensy.outputs]
start = { command = "A" }
stop  = { command = "Z" }
water = { command = "W", params = ["dur_ms"] }
TTL   = { command = "S" }
sync  = { command = "X" }
drain = { command = "D" }
```

Set `dummy = true` to run without hardware.

---

## See Also

- [Teensy Hardware Reference](../hardware/Teensy.md) — pin assignments, wiring diagram, firmware
- [Task Base Class](Tasks.md) — `give_reward()`, `signal_ttl()`, `drain_water()`
- [TTL Generator](TTLGenerator.md) — software-timed TTL from the host side
- [Unity Agents](../Unity/Agents.md) — `TTLReceiverAgent` sync patch in Unity
