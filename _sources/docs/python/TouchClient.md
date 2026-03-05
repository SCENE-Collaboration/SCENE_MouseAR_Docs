# Touch Client Documentation

## Overview

The **TouchClient** provides a simplified interface to the touchscreen module's `HostTouchClient`. It connects to a `TouchController` server running on a Raspberry Pi, forces `vectorized` view mode, and exposes a normalized `read()` API optimized for behavioral tasks.

**Key Features:**
- Automatic connection to touchscreen server with clock synchronization
- Fixed `vectorized` view mode (position + velocity vector)
- Normalized output in `[-1, 1]` for direct use as Unity actions
- Background receive thread with minimal latency
- Optional dummy modes for testing without hardware

---

## Architecture

```
┌─────────────────────────────────────────┐
│   Raspberry Pi (Touchscreen Server)     │
│   - TouchController (vectorized mode)   │
│   - 60 Hz rate transmission             │
│   - TCP Server on 0.0.0.0:6001          │
└──────────────┬──────────────────────────┘
               │ Network (multiprocessing)
               │
               ▼
┌─────────────────────────────────────────┐
│  HostTouchClient (touchscreen module)   │
│  - Background RX thread                 │
│  - Clock sync (NTP-style)               │
│  - Timing annotation                    │
└──────────────┬──────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────┐
│        TouchClient (Wrapper)             │
│  ┌────────────────────────────────────┐  │
│  │   Background RX Loop               │  │
│  │   - Drain packets from HostClient  │  │
│  │   - Keep only latest vectorized    │  │
│  │   - Store in deque(maxlen=1)       │  │
│  └────────────┬───────────────────────┘  │
│               │                          │
│               ▼                          │
│  ┌────────────────────────────────────┐  │
│  │   read() → Normalize to [-1, 1]    │  │
│  │   - px, py: Position               │  │
│  │   - vx, vy: Velocity               │  │
│  │   - heading: Direction [-1, 1]     │  │
│  │   - speed01: Magnitude [0, 1]      │  │
│  └────────────┬───────────────────────┘  │
└───────────────┼──────────────────────────┘
                │
                ▼
      ┌─────────────────────┐
      │  UnityAgentTask     │
      └─────────────────────┘
```

---

## TouchClient Class

### **Constructor**

```python
TouchClient(
    host: str = "127.0.0.1",
    port: int = 6001,
    authkey: bytes = b"touchbus",
    tx_mode: str = "rate",
    tx_hz: float = 60.0,
    max_queue_packets: int = 256,
    latest_maxlen: int = 1,
    invert_y: bool = True,
    speed_gain: float = 1.0,
    use_perf_counter: bool = False,
    # View params (sent to server on start)
    min_cutoff: float = 1.0,
    beta: float = 0.02,
    jitter_px: float = 2.0,
    merge_dist_norm: float = 0.08,
    vector_window_ms: int = 200
)
```

#### **Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `host` | `str` | `"127.0.0.1"` | Raspberry Pi IP address |
| `port` | `int` | `6001` | TouchController server port |
| `authkey` | `bytes` | `b"touchbus"` | Authentication key |
| `tx_mode` | `str` | `"rate"` | Transmission mode (`"event"`, `"rate"`, `"both"`) |
| `tx_hz` | `float` | `60.0` | Rate in Hz when `tx_mode` includes `"rate"` |
| `max_queue_packets` | `int` | `256` | HostTouchClient internal buffer size |
| `latest_maxlen` | `int` | `1` | TouchClient deque size (keep only latest) |
| `invert_y` | `bool` | `True` | Invert Y-axis (Unity convention) |
| `speed_gain` | `float` | `1.0` | Velocity scaling factor |
| `use_perf_counter` | `bool` | `False` | Use `time.perf_counter()` for timestamps |
| **View Parameters** | | | **(Sent to server on start)** |
| `min_cutoff` | `float` | `1.0` | One-Euro filter min cutoff (Hz) |
| `beta` | `float` | `0.02` | One-Euro filter beta (speed coefficient) |
| `jitter_px` | `float` | `2.0` | Jitter suppression threshold (pixels) |
| `merge_dist_norm` | `float` | `0.08` | Multi-touch centroid merge distance |
| `vector_window_ms` | `int` | `200` | Velocity sliding window duration (ms) |

---

### **Data Format**

#### **read() Return Value:**
```python
{
    "time": float,         # Wall-clock timestamp (when read() was called)
    "px": float,           # Position X in [-1, 1]
    "py": float,           # Position Y in [-1, 1] (inverted if invert_y=True)
    "heading": float,      # Direction in [-1, 1] (1 = +π rad)
    "speed01": float,      # Speed magnitude in [0, 1]
    "vx": float,           # Velocity X in [-1, 1]
    "vy": float,           # Velocity Y in [-1, 1] (inverted if invert_y=True)
    "raw": dict            # Original vectorized packet from server
}
```

#### **Raw Packet (from HostTouchClient):**
```python
{
    "mode": "vectorized",
    "heartbeat": bool,
    "point": {
        "x": float,        # [0, 1]
        "y": float,        # [0, 1]
        "age_ms": int
    },
    "vector": {
        "dx": float,       # Displacement [normalized units]
        "dy": float,
        "speed": float,    # Units/sec
        "direction_deg": float,
        "start": {"x": float, "y": float, "t": float},
        "end": {"x": float, "y": float, "t": float}
    },
    "_host": {              # Timing metadata
        "t_rx": float,
        "lag_ms_e2e": float,
        "lag_ms_wire": float
    }
}
```

---

### **Methods**

#### **start()**
```python
client.start()
```
- Starts `HostTouchClient` (background RX thread)
- Sets server mode to `"vectorized"`
- Configures transmission (tx_mode, tx_hz)
- Sends view parameters to server
- Performs clock synchronization
- Starts background RX loop to drain packets

#### **stop()**
```python
client.stop()
```
- Stops background RX loop
- Stops `HostTouchClient`

#### **read() → dict | None**
```python
pkt = client.read()
if pkt:
    px, py = pkt["px"], pkt["py"]  # Position [-1, 1]
    vx, vy = pkt["vx"], pkt["vy"]  # Velocity [-1, 1]
    heading = pkt["heading"]        # Direction [-1, 1]
    speed = pkt["speed01"]          # Magnitude [0, 1]
```
- Returns normalized touch data or `None` if no data yet
- Automatically stores data internally for `get_data()`

#### **latest_packet() → dict | None**
```python
raw_pkt = client.latest_packet()
```
- Returns raw vectorized packet from server (before normalization)

#### **clear()**
```python
client.clear()
```
- Drops cached packets from internal deque

---

### **Coordinate Normalization**

#### **Position Mapping:**
```python
# Server sends x, y in [0, 1]
# TouchClient maps to [-1, 1]:
px = 2.0 * x - 1.0
py = 2.0 * y - 1.0

if invert_y:
    py = -py
```

#### **Velocity Mapping:**
```python
# Server sends dx, dy (displacement in [0,1] units over window_ms)
# TouchClient applies speed_gain and clamps:
vx = clamp(-1, 1, dx * speed_gain)
vy = clamp(-1, 1, dy * speed_gain)

if invert_y:
    vy = -vy
```

#### **Heading Mapping:**
```python
angle_rad = atan2(dy, dx)
heading = angle_rad / π  # [-1, 1] where 1 = +π
```

---

### **Data Logging**

#### **get_data() → dict**
```python
data = client.get_data()
# Returns:
{
    "touch_read_time": [t1, t2, ...],
    "touch_px": [px1, px2, ...],
    "touch_py": [py1, py2, ...],
    "touch_heading": [h1, h2, ...],
    "touch_speed01": [s1, s2, ...],
    "touch_vx": [vx1, vx2, ...],
    "touch_vy": [vy1, vy2, ...]
}
```

#### **get_params() → dict**
```python
params = client.get_params()
# Returns configuration dict for logging
```

---

## DummyTouchClient Class

### **Purpose**
Stand-in for TouchClient when hardware is unavailable. Provides three modes:
1. **`pygame`**: Interactive window (hold LMB to simulate touch)
2. **`constant`**: Fixed position/velocity at specified FPS
3. **`random`**: Random positions with Gaussian velocity

### **Constructor**

```python
DummyTouchClient(
    mode: str = "pygame",
    window_size: Tuple[int, int] = (640, 480),
    invert_y: bool = True,
    speed_gain: float = 1.0,
    fps: int = 120,
    const_vals: Dict[str, float] | None = None,
    seed: int = 0,
    title: str = "Dummy Touch (threaded) — hold LMB; ESC quits",
    bg_color=(10, 10, 14),
    touch_color=(230, 64, 64),
    track_color=(64, 200, 120),
    max_history: int = 1
)
```

#### **Mode-Specific Parameters:**

**`mode="pygame"`:**
- **Window Controls:**
  - **Left Mouse Button (Hold)**: Simulate touch (green border when touching)
  - **ESC**: Quit
- **Output:** Position/velocity follow mouse cursor while LMB is held

**`mode="constant"`:**
- **`const_vals`**: Dict with keys `px, py, vx, vy, heading, speed01, touching`
- **Output:** Static values at `fps` rate

**`mode="random"`:**
- **`seed`**: Random seed for reproducibility
- **Output:** Random positions/velocities in `[-1, 1]`

---

### **API Methods**

Identical to `TouchClient`:
- `start()` / `stop()` / `close()`
- `read()` → dict | None
- `latest_packet()` → dict | None
- `get_data()` → dict
- `get_params()` → dict

---

## Integration with UnityAgentTask

### **Task Configuration**

```python
task = UnityAgentTask(
    teensy=teensy,
    env_path="Build/MouseAR.exe",
    use_touch=True,
    touch_address=("192.168.1.100", 6001),  # Raspberry Pi IP
    touch_tx_mode="rate",
    touch_tx_hz=60.0,
    touch_invert_y=True,
    touch_speed_gain=1.0,
    touch_vector_window_ms=200
)
task.start()
```

### **Dummy Mode Selection**

```python
# Interactive pygame dummy
task = UnityAgentTask(..., touch_address="dummy_pygame")
```

---

## Data Export

### **Logged Data Structure**

```python
data = touch.get_data()
# Keys:
#   touch_read_time:  [t1, t2, ...]
#   touch_px:         [px1, px2, ...]
#   touch_py:         [py1, py2, ...]
#   touch_heading:    [h1, h2, ...]
#   touch_speed01:    [s1, s2, ...]
#   touch_vx:         [vx1, vx2, ...]
#   touch_vy:         [vy1, vy2, ...]
```

**Usage in Task:**
```python
task_data = task.get_data()  # Includes touch data via task.touch_client.get_data()
```

---

## See Also

- **[Touchscreen Module Architecture](../touchscreen/TouchscreenArchitecture.md)** - Complete touchscreen system documentation
- **[TouchController API](../touchscreen/TouchscreenArchitecture.md)** - Server-side configuration
- **[HostTouchClient API](../touchscreen/TouchscreenArchitecture.md)** - Low-level client details
- **[Unity Agent Documentation](../Unity/Agents.md)** - TouchFingerAgent integration
