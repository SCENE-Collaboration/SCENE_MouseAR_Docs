# Teensy Hardware Reference

Firmware: `mouse_ar/ctrl/teensy_code/single_teensy_photodiode/single_teensy_photodiode.ino`

The Teensy microcontroller is the hardware bridge between the host PC and the
physical reward/sensor peripherals.  It handles real-time solenoid control,
sensor acquisition, and clock synchronisation independently of the host OS
scheduler.

**Hardware responsibilities**

| Subsystem | Direction | Description |
|-----------|-----------|-------------|
| Water solenoid 1 | OUT | Timed valve pulses for primary water reward delivery |
| Water solenoid 2 | OUT | Timed valve pulses for secondary water reward delivery |
| Vibration motor | OUT | Timed haptic feedback pulse (e.g. puck-contact cue) |
| Speaker / tone | OUT | Timed 3 kHz tone pulse (e.g. reward auditory cue) |
| TTL sync pulse | OUT | 10 ms pulse for episode-sync with external devices |
| Drain | OUT | Toggle valve open indefinitely (line flushing) |
| Photodiode | IN | 10-bit ADC reading from screen photodiode |
| Barcode TTL | IN | Digital barcode channel from screen |
| BH1750 lux | IN | I²C ambient-light sensor (50 Hz) |
| Clock sync | BOTH | NTP-style offset calibration over USB-Serial |

---

## Pin Assignments

| Pin | Direction | Signal | Notes |
|-----|-----------|--------|-------|
| 14 (A0) | IN | `PhotoDiode` | 10-bit ADC, 4× averaging, 500 Hz |
| 12 | IN | `BarcodeTTL` | `INPUT_PULLUP` — active-low barcode signal |
| 6 | OUT | `Water_pin` | Primary water solenoid — TIP120G via 220 Ω |
| 0 | OUT | `Water_pin2` | Secondary water solenoid |
| 9 | OUT | `Vibration_pin` | Vibration motor (e.g. Velleman WPM458) |
| 1 | OUT | `speaker` | Speaker — 3 kHz tone via `tone()` / `noTone()` |
| 11 | OUT | `TTL_pin` | Episode-sync TTL, 10 ms pulse |
| 13 | OUT | `LED_pin` | Built-in LED, mirrors primary water valve state |
| 18 (SDA) | I²C | BH1750 data | Wire library default |
| 19 (SCL) | I²C | BH1750 clock | Wire library default |

---

## Wiring Diagram

### Full board connections

```
                     ┌───────────────────────────────────────┐
                     │          Teensy 4.x                   │
                     │                                       │
      Photodiode ────┤ A0 / pin 14   (10-bit ADC)           │
    Barcode TTL ─────┤ pin 12        (INPUT_PULLUP)         │
                     │                                       │
            LED ─────┤ pin 13        (built-in)             │
        TTL out ─────┤ pin 11   ──► external TTL device     │
                     │                                       │
  Water ckt (1) ─────┤ pin 6    ──► 220 Ω ──► TIP120G base │
  Water ckt (2) ─────┤ pin 0    ──► secondary solenoid      │
Vibration motor ─────┤ pin 9    ──► Velleman WPM458 / relay │
        Speaker ─────┤ pin 1    ──► speaker / amplifier     │
                     │                                       │
    BH1750 SDA ──────┤ pin 18  (SDA)                        │
    BH1750 SCL ──────┤ pin 19  (SCL)                        │
                     │                                       │
            GND ─────┤ GND                                  │
            USB ─────┤ USB  ◄──────────────────► Host PC   │
                     └───────────────────────────────────────┘
```

### Water valve driver (TIP120G)

The solenoid valve is driven from a 12 V supply.  The Teensy output cannot
switch 12 V directly — a **TIP120G NPN Darlington transistor** switches the
solenoid's ground path.  The 12 V supply is always powered; the valve opens
when the transistor pulls the solenoid's negative terminal to GND.

```
 12 V ─────────────────────────────────┐
                                       │
                                 [Solenoid]
                                       │
                         TIP120G       │
                      ┌──────────┐     │
Teensy pin 6 ─[220Ω] ─┤ Base     │     │
                      │ Collector├─────┘
                      │ Emitter  ├──── GND
                      └──────────┘

  • 12 V supply:   always on
  • pin 6 HIGH  →  transistor ON  →  solenoid energised  (valve opens)
  • pin 6 LOW   →  transistor OFF →  solenoid de-energised (valve closed)
  • 220 Ω resistor limits base current to safe levels for 3.3 V output
  • Add a 1N4007 flyback diode across the solenoid (cathode to 12 V)
    to suppress the inductive spike when the valve closes
```

> **Flyback diode (required):** omitting it exposes the TIP120G collector to
> voltage spikes that can exceed its V_CE rating and destroy the transistor.

---

## Firmware Description

### Timing parameters

| Parameter | Value |
|-----------|-------|
| Baud rate | 115 200 |
| Main sample rate | 500 Hz |
| BH1750 request rate | 50 Hz |
| BH1750 measurement time | ~20 ms (low-resolution mode) |
| TTL pulse duration | 10 ms (fixed) |

### CSV output format

While `task_on`, the firmware emits one line per sample at 500 Hz over serial:

```
<micros>,<analog>,<digital>,<W_on>,<L_on>,<V_on>,<T_on>,<TTL_on>,<lux>,<lux_timestamp>
```

| Field | Type | Description |
|-------|------|-------------|
| `micros` | uint64 | Device time in µs (64-bit, overflow-safe) |
| `analog` | int | 10-bit ADC (0–1023) — photodiode |
| `digital` | int | Pin 12 state (0/1) — barcode TTL |
| `W_on` | 0/1 | Primary water valve active |
| `L_on` | 0/1 | Secondary water valve active |
| `V_on` | 0/1 | Vibration motor active |
| `T_on` | 0/1 | Tone (speaker) active |
| `TTL_on` | 0/1 | TTL output active |
| `lux` | uint | BH1750 lux (actual value when new reading available, else `4242`) |
| `lux_timestamp` | uint64 | Device µs of the lux reading (0 when not new) |

The `lux` field uses sentinel `4242` between readings so that an actual lux
reading of 0 can be distinguished from "no new reading".

### Command set

Commands are single ASCII bytes.  Some carry a **signed 16-bit little-endian**
integer payload (2 bytes) sent immediately after the command byte.

| Command | Byte | Payload | Valid when | Effect |
|---------|------|---------|------------|--------|
| Start   | `A`  | —       | idle       | Enable streaming, reset all output timers |
| Stop    | `Z`  | —       | running    | Disable streaming, turn off all outputs |
| Water 1 | `W`  | `int16 ms` | both   | Open primary solenoid for N ms (≤0 = close immediately) |
| Water 2 | `L`  | `int16 ms` | both   | Open secondary solenoid for N ms (≤0 = close immediately) |
| Vibration | `V` | `int16 ms` | both  | Run vibration motor for N ms (≤0 = stop immediately) |
| Tone    | `T`  | `int16 ms` | both   | Play 3 kHz tone for N ms (≤0 = stop immediately) |
| TTL pulse | `S` | —      | running    | Raise TTL pin for 10 ms |
| Clock sync | `X` | —    | both       | Reply `SYNC <t_dev_us>\n` |
| Drain   | `D`  | —       | idle       | Toggle both water valves open/closed (line flushing) |
| Reboot  | `Y`  | —       | idle       | `_reboot_Teensyduino_()` |

### Clock sync protocol

The host calibrates a time offset using an NTP-style exchange:

```
Host                              Device
 │                                   │
 │──── 'X' (1 byte) ────────────────►│
 │  t0 = time.time()                 │  t_dev = micros() (immediate)
 │◄─── "SYNC <t_dev_us>\n" ──────────│
 │  t3 = time.time()                 │
 │                                   │
 │  rtt    = t3 - t0
 │  offset = t3 - (t_dev_us/1e6 + rtt/2)
 │
 │  t_host_est = offset + t_dev_us/1e6   applied to every CSV row
```

`calibrate_offset()` (Python) performs 15 round-trips, keeps the 5
lowest-RTT samples, and stores their median as `self.offset`.

---

## See Also

- [Teensy Python Driver](../python/Teensy.md) — `Teensy` class, configuration, data access
- [Task Base Class](../python/Tasks.md) — `give_reward()`, `give_reward2()`, `give_vibration()`, `give_tone()`, `signal_ttl()`, `drain_water()`
