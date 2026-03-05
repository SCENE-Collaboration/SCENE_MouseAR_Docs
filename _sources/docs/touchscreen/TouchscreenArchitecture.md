# Touchscreen Module Architecture

## Overview

The touchscreen module provides a **server-client architecture** for capturing, processing, and streaming multitouch input data from Linux-based touchscreen devices (or Raspberry Pi if Windows is used as host machine) to remote control/visualization hosts. The system is designed for low-latency behavioral experiments with precise timing measurements and flexible data processing pipelines.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      RASPBERRY PI (Server)                  │
│                                                             │
│  ┌──────────────┐      ┌──────────────────────────────────┐ │
│  │ evdev Device │──►   │      TouchController             │ │
│  │ /dev/input/* │      │  ┌────────────────────────────┐  │ │
│  └──────────────┘      │  │      RawStore              │  │ │
│                        │  │  (Ring Buffer of Frames)   │  │ │
│                        │  └────────────┬───────────────┘  │ │
│                        │               │                  │ │
│                        │               ▼                  │ │
│                        │  ┌────────────────────────────┐  │ │
│                        │  │      View Pipeline         │  │ │
│                        │  │  • Raw                     │  │ │
│                        │  │  • Normalized [0,1]        │  │ │
│                        │  │  • Filtered (One-Euro)     │  │ │
│                        │  │  • Reduced (Single Touch)  │  │ │
│                        │  │  • Vectorized (Velocity)   │  │ │
│                        │  └────────────┬───────────────┘  │ │
│                        │               │                  │ │
│                        │               ▼                  │ │
│                        │  ┌────────────────────────────┐  │ │
│                        │  │   Transmission Engine      │  │ │
│                        │  │  • Event-driven (on touch) │  │ │
│                        │  │  • Rate-based (60Hz)       │  │ │
│                        │  │  • Both (hybrid)           │  │ │
│                        │  └────────────┬───────────────┘  │ │
│                        └───────────────┼──────────────────┘ │
│                                        │                    │
│  ┌─────────────────────────────────────▼──────────────────┐ │
│  │              ConnectionHub (Multicast Server)          │ │
│  │         0.0.0.0:6001 (multiprocessing.Listener)        │ │
│  └─────────────────────────────────────┬──────────────────┘ │
└────────────────────────────────────────┼────────────────────┘
                                         │ TCP Connection
                                         │ (multiprocessing)
                          ┌──────────────┼──────────────┐
                          │              │              │
                          ▼              ▼              ▼
              ┌──────────────────┐  ┌──────────────────┐
              │  HOST PC #1      │  │  HOST PC #2      │
              │                  │  │                  │
              │ HostTouchClient  │  │ HostTouchClient  │
              │  • RX Thread     │  │  • RX Thread     │
              │  • Timing Annot. │  │  • Timing Annot. │
              │  • Clock Sync    │  │  • Clock Sync    │
              │  • Recorder      │  │  • Recorder      │
              └────────┬─────────┘  └────────┬─────────┘
                       │                     │
                       ▼                     ▼
             ┌─────────────────┐   ┌─────────────────┐
             │ host_vis_gui.py │   │ Experiment      │
             │ (PyQt6 Monitor) │   │ (Custom Logic)  │
             └─────────────────┘   └─────────────────┘
```

---

## Core Components

### 1. **TouchController** (Server-Side)
**Location:** `touch_controller.py`

The main server component running on Raspberry Pi (or could also run on the host compute if its running Linux). Captures raw touch events from Linux evdev, processes them through a view pipeline, and broadcasts to connected clients.

#### **Responsibilities:**
- **Device Input:** Read multitouch events from `/dev/input/eventX` via `evdev` library
- **Event Parsing:** Convert low-level kernel events (`ABS_MT_*`, `SYN_REPORT`) into structured frames
- **Frame Storage:** Maintain ring buffer of recent frames (default: 2000 frames)
- **View Pipeline:** Apply data transformations (normalization, filtering, reduction, vectorization)
- **Broadcasting:** Send packets to all connected clients via ConnectionHub
- **Runtime Control:** Accept remote commands (mode switching, parameter updates, time sync)

#### **Key Features:**
- **Slot Tracking:** Multi-finger tracking via `ABS_MT_SLOT` and `ABS_MT_TRACKING_ID`
- **Device Auto-Discovery:** Automatically finds touchscreen device if path is `"auto"`
- **Exclusive Grab:** Prevents OS from interfering with touch events during experiments
- **Flexible Transmission:**
  - **Event Mode:** Send packet on every touch event (lowest latency)
  - **Rate Mode:** Send at fixed Hz (e.g., 60 Hz) with "hold-last" semantics
  - **Both Mode:** Combine event-driven and rate-based transmission

#### **Constructor Parameters:**
```python
TouchController(
    device_path="auto",              # Device path or "auto" for discovery
    mode="reduced",                  # Default view mode
    store_max_frames=2000,           # Ring buffer size

    # View filtering params
    min_cutoff=1.0,                  # One-Euro filter min cutoff
    beta=0.02,                       # One-Euro filter beta
    jitter_px=2.0,                   # Jitter suppression threshold (raw pixels)
    merge_dist_norm=0.08,            # Distance for centroid merge (normalized)
    vector_window_ms=200,            # Vectorized view sliding window

    # Transmission params
    tx_mode="rate",                  # "event" | "rate" | "both"
    tx_hz=60.0,                      # Rate in Hz for rate mode
    max_source_stale_ms=300,         # Max age before heartbeat/hold
    hold_last_when_touch_present=True,  # Hold stale data if finger is down

    # Server params
    serve_addr=("0.0.0.0", 6001),   # Listen address
    authkey=b"touchbus",             # Authentication key
    log_level=logging.INFO,
    backend="auto"                   # "evdev" | "win" | "stub"
)
```

#### **API Methods:**
```python
tc = TouchController(...)
tc.start()                           # Start capture and transmission
tc.stop()                            # Stop all threads and cleanup
tc.set_mode("vectorized")            # Switch view mode at runtime
tc.latest()                          # Get latest frame from current view
tc.since(seq)                        # Get all frames since sequence number
```

---

### 2. **RawStore** (Frame Buffer)
**Location:** `touch_data_utils.py`

Ring buffer storing raw touch frames with monotonic sequence numbers.

#### **Data Structure:**
```python
@dataclass
class RawPoint:
    slot: int                        # Kernel slot number
    tracking_id: Optional[int]       # Kernel tracking ID (unique per touch)
    x: Optional[int]                 # Raw X coordinate (device units)
    y: Optional[int]                 # Raw Y coordinate (device units)
    active: bool                     # Touch is in contact
    t_start: Optional[float]         # Touch down time (wall clock)
    t_now: Optional[float]           # Last update time
    t_end: Optional[float]           # Touch up time

@dataclass
class TouchFrame:
    seq: int                         # Monotonic sequence number
    t_host: float                    # Host timestamp when frame was emitted
    t_evt: float                     # Kernel event timestamp
    points: List[RawPoint]           # All active/inactive touches in this frame
    meta: Dict[str, Any]             # Device metadata (absinfo, device name)
```

---

### 3. **View Pipeline** (Data Transformations)
**Location:** `touch_data_utils.py`

Five progressive views over the raw data, each building on the previous:

#### **3.1 RawView**
- **Output:** Exactly as captured from kernel
- **Format:** List of points with raw integer coordinates

**Output Schema:**
```python
{
    "schema": "touch/v1",
    "mode": "raw",
    "seq": 42,
    "t": 1698765432.123,
    "t_evt": 1698765432.100,
    "points": [
        {
            "slot": 0,
            "id": 123,           # tracking_id
            "x": 2048,           # raw device units
            "y": 1536,
            "active": True,
            "t_start": 1698765430.0,
            "t_now": 1698765432.1,
            "t_end": None
        }
    ],
    "meta": {
        "device": "Touchscreen Name",
        "abs_xmin": 0, "abs_xmax": 4095,
        "abs_ymin": 0, "abs_ymax": 4095
    }
}
```

---

#### **3.2 NormalizedView**
- **Input:** RawView
- **Transform:** Map `[abs_xmin, abs_xmax] × [abs_ymin, abs_ymax]` → `[0, 1] × [0, 1]`

**Output Schema:**
```python
{
    "schema": "touch/v1",
    "mode": "normalized",
    "seq": 42,
    "t": 1698765432.123,
    "points": [
        {
            "id": 123,
            "x": 0.500,          # normalized [0,1]
            "y": 0.375,
            "age_ms": 2100       # time since t_start
        }
    ]
}
```

---

#### **3.3 FilteredView** (One-Euro Filter)
- **Input:** NormalizedView
- **Transform:** Per-finger One-Euro low-pass filter (adaptive cutoff based on velocity)
- **Parameters:**
  - `min_cutoff`: Minimum cutoff frequency (Hz) for slow movements
  - `beta`: Speed coefficient for adaptive cutoff
  - `jitter_px`: Raw pixel threshold to suppress jitter (locks to input if below)


**Output Schema:** Same as NormalizedView, but coordinates are filtered

---

#### **3.4 ReducedView** (Single Touch Reduction)
- **Input:** FilteredView
- **Transform:** Collapse multiple touches into ONE representative touch
- **Algorithm:**
  1. **Clustered Mode:** If all touches are within `merge_dist_norm` of centroid → emit centroid
  2. **Separated Mode:** Else, emit the **newest** touch (by `age_ms`)

**Output Schema:**
```python
{
    "schema": "touch/v1",
    "mode": "reduced",
    "seq": 42,
    "t": 1698765432.123,
    "point": {               # Single representative touch or None
        "id": 123,
        "x": 0.500,
        "y": 0.375,
        "age_ms": 2100
    },
    "points": [...],         # List containing the single point (or empty)
    "n_active": 3            # Total number of active touches before reduction
}
```

---

#### **3.5 VectorizedView** (Sliding Window Velocity)
- **Input:** ReducedView (single touch)
- **Transform:** Compute velocity vector over sliding time window
- **Parameters:**
  - `window_ms`: Window duration (e.g., 200ms)
- **Algorithm:**
  1. Maintain deque of `(t, x, y)` samples from reduced single-touch
  2. Remove samples older than `now - window_ms`
  3. Compute `end_point - start_point` and derive velocity
  4. If no new events, synthesize end point at current time with last known position (stationary finger → zero velocity)

**Output Schema:**
```python
{
    "schema": "touch/v1",
    "mode": "vectorized",
    "seq": 42,
    "t": 1698765432.123,
    "window_ms": 200,
    "point": {...},          # Current single-touch point (same as ReducedView)
    "n_active": 3,
    "vector": {              # None if no touch
        "dx": 0.120,         # Displacement in normalized units
        "dy": -0.085,
        "dt_ms": 200,        # Actual time span
        "len": 0.147,        # Euclidean length
        "speed": 0.735,      # Units per second
        "vx": 0.600,         # Velocity components
        "vy": -0.425,
        "direction_deg": -35.2,  # Atan2(dy, dx) in degrees
        "start": {"t": 1698765432.0, "x": 0.380, "y": 0.460},
        "end":   {"t": 1698765432.2, "x": 0.500, "y": 0.375}
    }
}
```

---

### 4. **ConnectionHub** (Multicast Server)
**Location:** `socket_utils.py`

Lightweight TCP server using Python's `multiprocessing.connection.Listener`. Allows multiple clients to connect/disconnect dynamically without disrupting the touch pipeline.

#### **Features:**
- **Multi-Client:** Broadcast to all connected clients simultaneously
- **Accept Loop:** Continuously accepts new connections in background thread
- **Per-Client RX:** Each client has a receive thread for bidirectional control commands
- **Callback:** `on_message(conn, msg)` for handling incoming commands
---

### 5. **HostTouchClient** (Client-Side)
**Location:** `host_client.py`

Client component running on control/visualization host PC. Connects to TouchController server, receives packets in background thread, annotates with timing metadata, and optionally records to disk.

#### **Responsibilities:**
- **Connection Management:** Automatic reconnection with configurable delay
- **Packet Reception:** Background thread with deque buffer (default: 2048 packets)
- **Timing Annotation:** Add host-side timing metadata (`t_rx`, lag measurements)
- **Clock Synchronization:** NTP-style offset estimation for cross-host timing
- **Recording:** Async JSONL writer with gzip support
- **Command Sending:** Remote control of server (mode, tx params, view params)

#### **Constructor Parameters:**
```python
HostTouchClient(
    host="127.0.0.1",
    port=6001,
    authkey=b"touchbus",
    max_packets=2048,               # Deque buffer size
    reconnect=True,                 # Auto-reconnect on disconnect
    reconnect_delay=1.0             # Reconnect interval
)
```

#### **API Methods:**
```python
client = HostTouchClient(...)
client.start()                      # Start RX thread
client.stop()                       # Stop and cleanup
client.connected()                  # Bool: connection status

# Data access
client.latest()                     # Get most recent packet
client.drain()                      # Pop all queued packets, return latest

# Commands to server
client.set_mode("vectorized")       # Switch view mode
client.set_tx(mode="rate", hz=120)  # Update transmission params
client.set_view_params(min_cutoff=2.0, beta=0.05, window_ms=150)  # Update filter params
client.sync_time(attempts=6)        # Clock synchronization

# Recording
client.set_recorder(AsyncJSONLRecorder("data.jsonl.gz"))
client.stop()  # Auto-closes recorder
```

#### **Clock Synchronization (NTP-Style):**
```python
res = client.sync_time(attempts=6, timeout=2.0)
# Returns: {
#   "ok": True,
#   "offset_s": -0.0123,            # Host clock = Server clock - offset
#   "offset_ms": -12.3,
#   "rtt_ms": 4.2,                  # Round-trip time
#   "samples": [...]                # All attempts
# }
```

**Algorithm:**
1. Client sends `{"cmd": "time_sync", "t0": <client_time>}`
2. Server replies immediately with `{"t1": <recv_time>, "t2": <send_time>}`
3. Client marks `t3` on receipt
4. Compute: `offset = ((t1 - t0) + (t2 - t3)) / 2`, `rtt = (t3 - t0) - (t2 - t1)`
5. Repeat N times, select sample with minimal RTT (most symmetric path)

---

### 6. **AsyncJSONLRecorder** (Logging)
**Location:** `host_client.py`

Non-blocking JSONL logger with background writer thread. Supports gzip compression.

#### **Features:**
- **Non-Blocking Enqueue:** RX thread never blocks on disk I/O
- **Batch Writing:** Drains up to 256 lines per write syscall
- **Drop Policies:** `"block"` | `"drop_new"` | `"drop_oldest"` on queue full
- **Header Line:** Automatically writes metadata header on new file
- **Gzip Support:** Auto-detects `.gz` extension

#### **API:**
```python
recorder = AsyncJSONLRecorder(
    path="data.jsonl.gz",
    metadata={"device": "Touchscreen", "experiment": "trial_001"},
    flush_every=64,                 # Flush to disk every N lines
    max_queue=10000,                # Queue capacity
    drop_policy="drop_oldest"       # Backpressure handling
)
recorder.record(packet)             # Non-blocking enqueue
recorder.close()                    # Flush and stop writer thread
recorder.stats()                    # {"written": N, "dropped": M, "queued": K}
```

---

### 7. **host_vis_gui.py** (Real-Time Monitor)
**Location:** `host_vis_gui.py`

PyQt6-based GUI for visualizing touch input and monitoring system performance.

#### **Features:**
- **Live Canvas:** Render touch points, reduced point, velocity vectors
- **Connection Control:** Connect/disconnect with custom host/port/auth
- **Mode Switching:** Change view mode at runtime
- **TX Parameter Control:** Adjust transmission mode, rate, staleness, hold-last
- **View Parameter Control:** Update filter parameters (cutoff, beta, jitter, merge distance, window)
- **Recording Control:** Start/stop JSONL recording with file browser
- **Clock Sync:** Trigger NTP-style synchronization
- **Timing Overlay:** Display lag metrics (e2e, wire, stale, gap, RTT, offset)
- **Invert Y:** Coordinate system flip for different screen orientations

#### **UI Layout:**
```
┌────────────────────────────────────────────────────────────┐
│              [Touch Canvas - Live Visualization]           │
│  • Touch points: Blue circles                              │
│  • Reduced point: Yellow circle (larger)                   │
│  • Velocity vector: Green arrow (vectorized mode)          │
│  • Stats overlay: mode, seq, lag, sync                     │
└────────────────────────────────────────────────────────────┘
│ Connection: [Host: 128.178.51.86] [Port: 6001] [Auth: ...] │
│             [Connect] [Disconnect]                         │
├────────────────────────────────────────────────────────────┤
│ Mode: [reduced ▼] [Set Mode]                               │
│ TX: [rate ▼] Hz:[60] MaxStale:[300] [Hold-last ☑] [Apply]  │
│ [Invert Y ☐]                                               │
├────────────────────────────────────────────────────────────┤
│ Record: [./logs/run_20250930_120000.jsonl] [Browse...]     │
│         [Start Rec] [Stop Rec]  REC: on (w:1234 d:0 q:12)  │
├────────────────────────────────────────────────────────────┤
│ [Sync Time] offset: -12.3 ms | rtt: 4.2 ms [Get Meta]      │
├────────────────────────────────────────────────────────────┤
│ Connected | RX:60.0 pkt/s | mode:reduced | hb:False        │
│ e2e:15.2ms wire:3.1ms stale:0.0ms gap:-0.5ms               │
│ synced:yes offset:-12.3ms rtt:4.2ms                        │
└────────────────────────────────────────────────────────────┘
```

#### **Usage:**
```bash
python host_vis_gui.py
# Then use GUI controls to connect and configure
```

---

## Timing Architecture

### **Timestamps in the Pipeline**

The system tracks multiple timestamps at different stages:

```
Touch Event on Pi → t_evt (kernel timestamp)
    ↓
Frame Emit → t_host (Pi wall clock)
    ↓
TX Send → t_tx (Pi wall clock), t_tx_mono (Pi monotonic)
    ↓
Network Transit
    ↓
RX Recv → t_rx (Host wall clock), t_rx_mono (Host monotonic)
    ↓
Annotation → _host metadata
```

### **Host Timing Metadata (`_host` field)**

Added by `HostTouchClient._annotate_packet()`:

```python
{
    "t_rx": 1698765432.456,           # Host wall clock receive time
    "t_rx_mono": 1234567.890,         # Host monotonic time
    "offset": -0.0123,                # Clock offset (if synced)
    "synced": True,                   # Clock sync status
    "rtt_ms": 4.2,                    # Last sync RTT

    # Lag measurements
    "fresh": True,                    # Is this a new source frame?
    "stale_ms": 0.0,                  # Time since last fresh frame arrived at host
    "lag_ms_e2e": 15.2,               # End-to-end: (t_rx - source_t) - offset [FROZEN on repeat frames]
    "lag_ms_wire": 3.1,               # Wire delay: (t_rx - t_tx) - offset [COMPUTED EVERY PACKET]

    # Monotonic tick diagnostics (no cross-host sync needed)
    "srv_tick_ms": 16.7,              # Server inter-packet interval (monotonic)
    "rx_tick_ms": 17.2,               # Host inter-arrival interval (monotonic)
    "gap_ms": 0.5                     # rx_tick - srv_tick (network jitter)
}
```

### **Lag Measurement Semantics**

1. **`lag_ms_e2e` (End-to-End Latency):**
   - Measures: **Touch event on Pi → Packet received on Host**
   - Computed: `(t_rx - source_t) - clock_offset`
   - **Frozen Behavior:** Only updated when a NEW source frame arrives (fresh=True)
   - **Rationale:** In "rate" mode, server may send same source frame multiple times. Lag should NOT increase artificially on repeated transmissions.
   - **Use Case:** True touch-to-host latency for fresh events

2. **`stale_ms` (Staleness):**
   - Measures: **Time since last fresh frame was received**
   - Computed: `t_rx_now - t_rx_last_fresh`
   - **Always Increasing:** Increments on every packet until a fresh frame arrives
   - **Use Case:** Detect when server is repeating old data (hold-last mode)

3. **`lag_ms_wire` (Network Latency):**
   - Measures: **Packet send on Pi → Packet received on Host**
   - Computed: `(t_rx - t_tx) - clock_offset`
   - **Computed Every Packet:** Includes both fresh and repeated frames
   - **Use Case:** Monitor network performance

4. **`gap_ms` (Jitter):**
   - Measures: **Difference between host RX interval and server TX interval**
   - Computed: `rx_tick_ms - srv_tick_ms`
   - **Monotonic-Based:** No cross-host sync required (uses monotonic clocks)
   - **Interpretation:**
     - `gap_ms > 0`: Packet arrived later than expected (network delay)
     - `gap_ms < 0`: Packet arrived earlier (batching or clock drift)
   - **Use Case:** Diagnose network jitter

### **Rate Mode Heartbeat/Hold Semantics**

In `tx_mode="rate"` with `tx_hz=60`:

- Server sends packet every 16.7ms (60 Hz) regardless of touch events
- If source frame age > `max_source_stale_ms`:
  - **No touch present OR `hold_last_when_touch_present=False`:**
    - Send **heartbeat packet** (`heartbeat=True`, no data)
  - **Touch present AND `hold_last_when_touch_present=True`:**
    - Send **held packet** (`held=True`, repeat last data)
    - Useful for maintaining smooth visualization during brief event gaps

---


### **Client Configuration (Host PC)**

#### **Basic Connection:**
```python
from touchscreen.host_client import HostTouchClient

client = HostTouchClient(
    host="192.168.1.100",  # Raspberry Pi IP
    port=6001,
    authkey=b"touchbus",
    reconnect=True
)
client.start()

# Synchronize clocks
sync_result = client.sync_time(attempts=6)
print(f"Offset: {sync_result['offset_ms']:.1f} ms, RTT: {sync_result['rtt_ms']:.1f} ms")

# Main loop
try:
    while True:
        pkt = client.drain()  # Get latest packet
        if pkt and pkt.get("point"):
            point = pkt["point"]
            print(f"Touch at ({point['x']:.3f}, {point['y']:.3f})")
        time.sleep(0.016)  # ~60 fps
finally:
    client.stop()
```

#### **With Recording:**
```python
from touchscreen.host_client import HostTouchClient, AsyncJSONLRecorder

client = HostTouchClient(host="192.168.1.100", port=6001, authkey=b"touchbus")
client.start()
client.sync_time(attempts=6)

# Start recording
recorder = AsyncJSONLRecorder(
    path="./logs/experiment_001.jsonl.gz",
    metadata={"subject": "mouse_001", "session": "training_day_3"},
    flush_every=64
)
client.set_recorder(recorder)

try:
    # Your experiment loop
    for trial in range(100):
        # ... run trial ...
        pass
finally:
    client.stop()  # Auto-closes recorder
```

#### **Runtime Parameter Control:**
```python
client = HostTouchClient(host="192.168.1.100", port=6001)
client.start()

# Switch to vectorized mode
client.set_mode("vectorized")

# Increase rate to 120 Hz
client.set_tx(mode="rate", hz=120.0)

# Update filter parameters
client.set_view_params(
    min_cutoff=2.0,      # More aggressive filtering
    beta=0.05,
    jitter_px=3.0,
    merge_dist_norm=0.10,
    window_ms=150        # Shorter velocity window
)
```

---

## Hardware Setup

### **Raspberry Pi Configuration**

#### **1. Find Touch Device:**
```bash
# List all input devices
sudo libinput list-devices

# Or use evtest
sudo apt-get install evtest
sudo evtest
# Select device and test by touching screen
```

#### **2. Check Device Capabilities:**
```bash
# Install evdev tools
pip install evdev

# Auto-detect touchscreen
python -c "from touchscreen.touch_controller import TouchController; tc = TouchController(device_path='auto'); print(tc.device_path)"
```

#### **3. Get Raspberry Pi IP:**
```bash
hostname -I
# Example: 192.168.1.100
```

#### **4. Run Server on Boot (systemd service):**
```ini
# /etc/systemd/system/touchscreen.service
[Unit]
Description=Touchscreen Server
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/mice_ar_tasks
ExecStart=/home/pi/mice_ar_tasks/venv/bin/python -m touchscreen.touch_controller --device auto --mode reduced --tx-mode rate --tx-hz 60
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable touchscreen.service
sudo systemctl start touchscreen.service
sudo systemctl status touchscreen.service
```

---

#### **Low-Latency Network Settings (Optional):**
```bash
# Disable power management on WiFi
sudo iwconfig wlan0 power off

# Increase TCP buffer sizes
sudo sysctl -w net.core.rmem_max=8388608
sudo sysctl -w net.core.wmem_max=8388608
```
---

### **Offline Analysis of Recorded Data**

```python
import gzip
import json

# Read recorded JSONL
with gzip.open("logs/experiment_001.jsonl.gz", "rt") as f:
    header = json.loads(f.readline())
    print("Device:", header["meta"]["device"])

    packets = [json.loads(line) for line in f if json.loads(line)["type"] == "packet"]

# Extract trajectories
trajectories = []
for pkt in packets:
    if pkt.get("point") and not pkt.get("heartbeat"):
        trajectories.append({
            "t": pkt["t"],
            "x": pkt["point"]["x"],
            "y": pkt["point"]["y"],
            "lag_ms": pkt.get("_host", {}).get("lag_ms_e2e", 0)
        })

# Analyze
import numpy as np
lags = [t["lag_ms"] for t in trajectories]
print(f"Mean lag: {np.mean(lags):.1f} ms")
print(f"P95 lag: {np.percentile(lags, 95):.1f} ms")
```
