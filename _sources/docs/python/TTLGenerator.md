# TTL Generator Documentation

## Overview

The **TTLGenerator** creates time-coded TTL (Transistor-Transistor Logic) pulse bursts for synchronizing Unity with external recording systems. Each burst contains:
- **Preamble**: Distinctive ON-OFF pattern for burst detection
- **8-bit Counter**: Monotonically increasing burst ID (0-255, wraps around)
- **Manchester-like Encoding**: Self-clocking pulse sequence

This allows external devices (cameras, neural recording systems, photodiode circuits) to align their timestamps with Unity's internal timeline.

**Key Features:**
- Host-timed bursts (not dependent on Unity frame rate)
- Configurable period (default: 5 seconds)
- 50 ms half-cell duration (configurable)
- Simple interface: returns `[0.0]` or `[1.0]` for Unity continuous action
- Automatic state management (ON → OFF transitions)

---

## Architecture

```
┌─────────────────────────────────────────┐
│      TTLGenerator (Host Python)         │
│   ┌──────────────────────────────────┐  │
│   │   Timing Loop (every dt)         │  │
│   │   - Check if burst due           │  │
│   │   - Generate next bit            │  │
│   │   - Track position in sequence   │  │
│   └──────────┬───────────────────────┘  │
│              │                          │
│              ▼                          │
│   ┌──────────────────────────────────┐  │
│   │   read() → [0.0] or [1.0]        │  │
│   │   - Returns TTL state            │  │
│   │   - Logs to data deque           │  │
│   └──────────┬───────────────────────┘  │
└──────────────┼──────────────────────────┘
               │
               ▼
   ┌────────────────────────────┐
   │   UnityAgentTask           │
   │   _ttl_action(spec)        │
   │   - Pack [ttl] to action   │
   └────────────┬───────────────┘
                │
                ▼
   ┌────────────────────────────┐
   │   Unity ML-Agents          │
   │   Continuous Action[N]     │
   │   - Relay to digital pin   │
   └────────────┬───────────────┘
                │
                ▼
   ┌────────────────────────────┐
   │   External Device          │
   │   - Photodiode circuit     │
   └────────────────────────────┘
```

---

## TTL Burst Structure

### **Sequence Diagram**

```
TIME →
                     PREAMBLE           COUNTER BITS (8-bit, LSB first)
                 ┌──────┬──────┐  ┌──────┬──────┬─ ─ ─ ┬──────┬──────┐
                 │  ON  │ OFF  │  │ bit0 │ bit1 │ ... │ bit6 │ bit7 │
                 │ 50ms │ 50ms │  │ 50ms │ 50ms │     │ 50ms │ 50ms │
─────────────────┘      └──────┘  └──────┴──────┴─ ─ ─ ┴──────┴──────┘

Total Duration = (2 + 8*2) * 50ms = 900 ms
```

### **Example: Counter = 5 (binary: 0b00000101)**

```
LSB first: bit0=1, bit1=0, bit2=1, bit3-7=0

Preamble:
  Cell 0: ON  (50ms)
  Cell 1: OFF (50ms)

Bit 0 (=1):  Manchester "1" = ON then OFF
  Cell 2: ON  (50ms)
  Cell 3: OFF (50ms)

Bit 1 (=0):  Manchester "0" = OFF then ON
  Cell 4: OFF (50ms)
  Cell 5: ON  (50ms)

Bit 2 (=1):  Manchester "1" = ON then OFF
  Cell 6: ON  (50ms)
  Cell 7: OFF (50ms)

Bit 3-7 (=0): All Manchester "0"
  Cells 8-17: OFF, ON, OFF, ON, ... (alternating)
```

---

## TTLGenerator Class

### **Constructor**

```python
TTLGenerator(
    half_cell_sec: float = 0.05,
    period_sec: float = 5.0,
    n_bits: int = 8,
    use_perf_counter: bool = False
)
```

#### **Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `half_cell_sec` | `float` | `0.05` | Duration of each half-cell (seconds). Total cell = 2 × half_cell. |
| `period_sec` | `float` | `5.0` | Time between burst starts (seconds). |
| `n_bits` | `int` | `8` | Number of counter bits (max value = 2^n_bits - 1). |
| `use_perf_counter` | `bool` | `False` | Use `time.perf_counter()` for timing (more precise). |

**Derived Values:**
- **Full cell duration**: `2 * half_cell_sec = 100 ms` (default)
- **Preamble duration**: `2 * half_cell_sec = 100 ms` (1 ON + 1 OFF)
- **Counter duration**: `n_bits * 2 * half_cell_sec = 800 ms` (8 bits × 2 half-cells)
- **Total burst duration**: `(1 + n_bits) * 2 * half_cell_sec = 900 ms` (default)

---

### **Methods**

#### **start()**
```python
ttl.start()
```
- Resets internal state
- Sets `t_zero` to current time
- Initializes counter to 0

#### **stop()**
```python
ttl.stop()
```
- No-op (included for API consistency)

#### **read() → np.ndarray**
```python
action = ttl.read()  # Returns np.array([0.0]) or np.array([1.0])
```
- **Returns**: NumPy float32 array with single element
  - `[1.0]`: TTL high (ON)
  - `[0.0]`: TTL low (OFF)
- **Side Effect**: Advances internal state machine
- **Logs**: Each call appends `(time, ttl_value)` to internal deque

#### **get_data() → dict**
```python
data = ttl.get_data()
# Returns:
{
    "ttl_time": [t1, t2, ...],    # Timestamps (seconds)
    "ttl_value": [0.0, 1.0, ...]  # TTL states
}
```

#### **get_params() → dict**
```python
params = ttl.get_params()
# Returns:
{
    "half_cell_sec": 0.05,
    "period_sec": 5.0,
    "n_bits": 8
}
```

---

### **State Machine**

The TTLGenerator maintains:
- **`counter`**: Current burst ID (0-255)
- **`cell_idx`**: Position in current burst sequence (0 to `2*(1+n_bits)-1`)
- **`t_last_burst`**: Time when current burst started

**Logic:**
```python
def read(self) -> np.ndarray:
    t = time.time()
    dt = t - self.t_last_burst

    # Check if new burst should start
    if dt >= self.period_sec:
        self.t_last_burst = t
        self.cell_idx = 0
        self.counter = (self.counter + 1) % (2 ** self.n_bits)

    # Compute which cell we're in
    cell_in_burst = int(dt / self.half_cell_sec)
    if cell_in_burst >= 2 * (1 + self.n_bits):
        # Past end of burst → idle (OFF)
        val = 0.0
    else:
        # Preamble: cell 0=ON, cell 1=OFF
        if cell_in_burst < 2:
            val = 1.0 if cell_in_burst == 0 else 0.0
        else:
            # Counter bits (Manchester encoding)
            bit_idx = (cell_in_burst - 2) // 2  # Which bit (0-7)
            phase = (cell_in_burst - 2) % 2     # First or second half-cell
            bit_val = (self.counter >> bit_idx) & 1

            # Manchester: bit=1 → ON,OFF; bit=0 → OFF,ON
            if bit_val == 1:
                val = 1.0 if phase == 0 else 0.0
            else:
                val = 0.0 if phase == 0 else 1.0

    self.data_deque.append({"time": t, "val": val})
    return np.array([val], dtype=np.float32)
```

---

## Manchester Encoding

**Standard Manchester:**
- **Bit 1**: Transition from HIGH to LOW (mid-cell)
- **Bit 0**: Transition from LOW to HIGH (mid-cell)

**TTLGenerator Implementation:**
- **Bit 1**: Cell = `[ON, OFF]` (2 half-cells)
- **Bit 0**: Cell = `[OFF, ON]` (2 half-cells)

**Why Manchester?**
- Self-clocking: Receiver can detect cell boundaries from transitions
- Robust: Single missed edge doesn't corrupt entire message

---

## Integration with UnityAgentTask

### **Task Configuration**

```python
task = UnityAgentTask(
    teensy=teensy,
    env_path="Build/MouseAR.exe",
    use_photottl=True,
    photottl_half_cell_sec=0.05,
    photottl_period_sec=5.0,
    photottl_n_bits=8
)
task.start()
```

### **Action Construction**

In `UnityAgentTask._ttl_action(spec)`:

```python
def _ttl_action(self, spec):
    size = spec.action_spec.continuous_size
    empty = np.zeros(size, dtype=np.float32)

    if not self.ttl_generator:
        return empty

    ttl_val = self.ttl_generator.read()  # [0.0] or [1.0]
    return self._pack_and_clip(ttl_val, size)
```

**Unity Agent Receives:**
```
actions[0] = ttl_value  # 0.0 or 1.0
```

---

## Photodiode Synchronization Workflow

### **Setup**

```
Unity Display        Photodiode         Recording System
     │                   │                      │
     │ Screen Corner     │                      │
     │ (White/Black)     │                      │
     ├──────────────────►│ Analog Signal        │
     │                   ├─────────────────────►│ ADC Channel
     │                   │ (0-5V)               │ (Sampled at high rate)
```

### **Procedure**

1. **Unity**: Render TTL state to screen corner (white=1, black=0)
2. **Photodiode**: Convert light to voltage
3. **Recording ADC**: Sample photodiode at high rate
4. **Post-processing**: Detect bursts, decode counter values

---

### **Decoding Algorithm**

```python
import numpy as np

def decode_ttl_bursts(signal, sample_rate, half_cell_sec=0.05):
    """
    signal: 1D array of photodiode ADC values
    sample_rate: ADC sampling frequency (Hz)
    half_cell_sec: TTL half-cell duration (seconds)
    """
    # Threshold signal
    threshold = (signal.max() + signal.min()) / 2
    digital = (signal > threshold).astype(int)

    # Detect transitions
    edges = np.diff(digital)
    rising = np.where(edges == 1)[0]
    falling = np.where(edges == -1)[0]

    # Find preambles (long ON followed by long OFF)
    half_cell_samples = int(half_cell_sec * sample_rate)
    bursts = []

    for r in rising:
        # Check for preamble pattern
        if r + 2*half_cell_samples >= len(digital):
            continue

        on_duration = np.sum(digital[r:r+half_cell_samples])
        off_duration = half_cell_samples - np.sum(digital[r+half_cell_samples:r+2*half_cell_samples])

        if on_duration > 0.8*half_cell_samples and off_duration > 0.8*half_cell_samples:
            # Decode 8 bits
            counter = 0
            for bit_idx in range(8):
                cell_start = r + (2 + bit_idx*2) * half_cell_samples
                first_half = np.mean(digital[cell_start:cell_start+half_cell_samples])
                second_half = np.mean(digital[cell_start+half_cell_samples:cell_start+2*half_cell_samples])

                # Manchester: 1 = HIGH,LOW; 0 = LOW,HIGH
                if first_half > 0.5 and second_half < 0.5:
                    counter |= (1 << bit_idx)

            bursts.append({
                "sample": r,
                "time": r / sample_rate,
                "counter": counter
            })

    return bursts
```
---


## Data Export

### **Logged Data Structure**

```python
data = ttl.get_data()
# Keys:
#   ttl_time:   [t1, t2, ...]  # Timestamps (seconds)
#   ttl_value:  [0.0, 1.0, ...]  # TTL states
```
---
## See Also

- **[Teensy Serial Interface](Teensy.md)** - Alternative hardware-based TTL via Teensy
- **[UnityAgentTask](Tasks.md)** - TTL integration in task loop
- **[Unity Agents](../Unity/Agents.md)** - Receiving continuous actions

---

## Appendix: Timing Diagrams

### **Full Burst Timeline (Default Config)**

```
Time:  0ms   50   100  150  200  250  300  350  400  450  500  550  600  650  700  750  800  850  900
       │    │    │    │    │    │    │    │    │    │    │    │    │    │    │    │    │    │    │
       ├────┤────┤────┤────┤────┤────┤────┤────┤────┤────┤────┤────┤────┤────┤────┤────┤────┤────┤
       │ ON │OFF │ b0 │ b0'│ b1 │ b1'│ b2 │ b2'│ b3 │ b3'│ b4 │ b4'│ b5 │ b5'│ b6 │ b6'│ b7 │ b7'│idle
       │    │    │    │    │    │    │    │    │    │    │    │    │    │    │    │    │    │    │
       └────┴────┴────┴────┴────┴────┴────┴────┴────┴────┴────┴────┴────┴────┴────┴────┴────┴────┘
       PREAMBLE  BIT0      BIT1      BIT2      BIT3      BIT4      BIT5      BIT6      BIT7

       └─────────────────────────────────────────────── 900 ms ───────────────────────────────────┘

       Idle period: 5000 - 900 = 4100 ms (until next burst)
```
