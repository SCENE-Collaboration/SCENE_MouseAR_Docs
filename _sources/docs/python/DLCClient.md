# DLC Client Documentation

## Overview

The **DLC (DeepLabCut) Client** provides a real-time interface for pose estimation data from DeepLabCut or simulated sources. It receives streaming pose data via TCP socket, applies optional filtering (One-Euro filter), and exposes a simple `read()` API for tasks to consume normalized position and heading data. The filtering can also be done "at source" in the DLC processor.

---

## Architecture

```
┌────────────────────────────────────────┐
│   DLC Server (Pose Estimation)         │
│   - DeepLabCut inference pipeline      │
│   - Sends: [t, x, y, heading,          │
│              head_angle, action]       │
│   - TCP Server on localhost:6000       │
└──────────────┬─────────────────────────┘
               │ Socket (multiprocessing)
               │
               ▼
┌──────────────────────────────────────────┐
│        DLCClient (Client Side)           │
│  ┌────────────────────────────────────┐  │
│  │   Background Reader Thread         │  │
│  │   - Recv from socket               │  │
│  │   - Optional: Always-filter        │  │
│  │   - Push to deque(maxlen=1)        │  │
│  └────────────┬───────────────────────┘  │
│               │                          │
│               ▼                          │
│  ┌────────────────────────────────────┐  │
│  │   read() → apply_filter_onread?    │  │
│  │   OneEuroFilter (adaptive cutoff)  │  │
│  │   [t, x, y, heading, head_angle]   │  │
│  └────────────┬───────────────────────┘  │
│               │                          │
└───────────────┼──────────────────────────┘
                │
                ▼
      ┌─────────────────────┐
      │  UnityAgentTask     │
      └─────────────────────┘
```

---

## Connection Architecture

The DLCClient connects to a **DLC Processor** (not directly to DLCLive). The processor handles pose estimation and broadcasts to multiple clients:

```
┌─────────────────────────┐
│   DLCLive Camera        │
│   (Pose Estimation)     │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────────────────┐
│  MyProcessor_socket (Server)        │
│  - Receives raw poses from DLCLive  │
│  - Calculates center, heading, etc  │
│  - Optional One-Euro filtering      │
│  - Broadcasts to multiple clients   │
│  - Recording control                │
│  - Port: 6000 (default)             │
└────┬──────────────┬─────────────────┘
     │              │ (Multiple clients)
     ▼              ▼
┌─────────┐    ┌─────────┐
│DLCClient│    │DLCClient│
│(Unity)  │    │(Python) │
└─────────┘    └─────────┘
```

**Connection Details:**
- **Protocol**: TCP socket via `multiprocessing.connection`
- **Authentication**: `authkey=b"secret password"`
- **Data Format**: `[timestamp, x, y, heading, head_angle]`
- **Commands**: Dictionary messages with `{"cmd": "...", ...}`

## DLCClient Class

### **Constructor**

```python
DLCClient(
    address: tuple[str, int] = ("localhost", 6000),
    apply_filter_always: bool = False,
    apply_filter_onread: bool = False,
    apply_filter_inprocessor: bool = False,
    use_perf_counter: bool = False,
    box_extents: tuple[int, int, int, int] = (0, 0, 640, 480),
    flip_y: bool = False,
    flip_x: bool = False,
    rotate_90: bool = False,
    oneeuro_beta: float = 0,
    oneeuro_min_cutoff: float = 1,
    oneeuro_d_cutoff: float = 1.0,
    session_name: str = "default_session"
)
```

#### **Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `address` | `tuple[str, int]` | `("localhost", 6000)` | TCP server address for DLC pose stream |
| `apply_filter_always` | `bool` | `False` | Apply One-Euro filter on every received packet (background thread) |
| `apply_filter_onread` | `bool` | `False` | Apply One-Euro filter when `read()` is called (foreground) |
| `apply_filter_inprocessor` | `bool` | `False` | Request processor to apply filtering (filtering at source) |
| `use_perf_counter` | `bool` | `False` | Use `time.perf_counter()` instead of `time.time()` |
| `box_extents` | `tuple[int, int, int, int]` | `(0, 0, 640, 480)` | Bounding box for coordinate normalization: `(left, top, right, bottom)` |
| `flip_y` | `bool` | `False` | Invert Y-axis before normalization |
| `flip_x` | `bool` | `False` | Invert X-axis before normalization |
| `rotate_90` | `bool` | `False` | Rotate coordinates 90° clockwise after normalization |
| `oneeuro_beta` | `float` | `0` | One-Euro filter speed coefficient |
| `oneeuro_min_cutoff` | `float` | `1` | One-Euro filter minimum cutoff frequency |
| `oneeuro_d_cutoff` | `float` | `1.0` | One-Euro filter derivative cutoff |
| `session_name` | `str` | `"default_session"` | Session name for recording (used in filename) |

---

### **Data Format**

#### **Received Packet (from DLC server):**
```python
[t_since_start, x, y, heading, head_angle, action]
# x, y: pixels in camera frame
# heading: degrees (0-360)
# head_angle: degrees (head orientation relative to body)
# action: optional discrete action index (e.g., for manual control)
```

#### **read() Return Value:**
```python
{
    "time": float,              # Wall-clock or perf_counter timestamp
    "vals": [t, x, y, heading, head_angle, action]
}
```

**Note:** `vals` can have 4-6 elements depending on whether action is included.

---

### **Methods**

#### **start()**
```python
dlc.start()
```
- Connects to DLC server via TCP socket
- Starts background reader thread
- Initializes timing

#### **stop()**
```python
dlc.stop()
```
- Stops background reader thread
- Does not close socket (use `close()` for that)

#### **close()**
```python
dlc.close()
```
- Stops reader thread
- Closes socket connection

#### **read() → dict | None**
```python
packet = dlc.read()
if packet:
    time = packet["time"]
    t, x, y, heading, head_angle = packet["vals"][:5]
    # x, y are automatically normalized to [-1, 1] based on box_extents
```
- Returns latest packet from deque (FIFO, maxlen=1)
- Returns `None` if no data available
- Optionally applies filter if `apply_filter_onread=True`
- **Automatically applies coordinate normalization** via `_map_coordinates()`:
  - Maps `(x, y)` from pixel coordinates to `[-1, 1]` based on `box_extents`
  - Applies flipping and rotation transformations
  - Clamps values to `[-1, 1]` range
- Stores data internally for later retrieval via `get_data()`

#### **Recording Control Methods**

```python
client.set_session_name(session_name: str)
```
- Sets session name on the processor
- Determines filename for saved data: `{session_name}_dlc_processor_data.pkl`

```python
client.start_recording()
```
- Starts recording on the processor
- **Clears all data queues** on the processor
- Processor begins logging pose data

```python
client.stop_recording()
```
- Stops recording on the processor
- Processor continues broadcasting but stops logging

```python
client.trigger_save(filename: str = None)
```
- Triggers the processor to save its logged data
- If `filename` is None, uses session-based filename
- Data saved as pickle file with all logged values

#### **Filter Control Methods**

```python
client.set_filter(use_filter: bool)
```
- Enable or disable filtering on the processor
- Works with processors that support filtering (e.g., `MyProcessor_socket`)
- Changes take effect immediately on next frame
- Example: `client.set_filter(True)`  # Enable filtering

```python
client.set_filter_params(min_cutoff: float = None, beta: float = None, d_cutoff: float = None)
```
- Update One-Euro filter parameters on the processor
- Parameters:
  - `min_cutoff`: Minimum cutoff frequency (lower = smoother, default: 1.0)
  - `beta`: Speed coefficient (higher = more responsive to velocity, default: 0.02)
  - `d_cutoff`: Cutoff for derivative filter (default: 1.0)
- Filters are reinitialized with new parameters on next frame
- Examples:
  ```python
  client.set_filter_params(min_cutoff=0.5, beta=0.01)  # Very smooth
  client.set_filter_params(min_cutoff=2.0, beta=0.05)  # Very responsive
  ```

```python
client.send_command(cmd: str, **kwargs)
```
- Low-level command sender
- Available commands: `"set_session_name"`, `"start_recording"`, `"stop_recording"`, `"save"`

---

### **Filtering (One-Euro Filter)**

**Algorithm:**
```
Adaptive cutoff = min_cutoff + beta * |velocity|
Filtered value = EMA with alpha based on adapted cutoff
```

**Default Parameters:**
- `min_cutoff = 1.0` Hz (moderate cutoff)
- `beta = 0.0` (no speed adaptation)
- `d_cutoff = 1.0` Hz (derivative filter cutoff)

**Filtering Modes:**
- `apply_filter_always=True`: Filter in background thread (lower latency, less CPU in main loop)
- `apply_filter_onread=True`: Filter on demand in main loop (more control, matches old behavior)
- `apply_filter_inprocessor=True`: Request processor to apply filtering at source (recommended for best performance)

**Parameter Tuning:**
- **Lower `min_cutoff`**: Smoother motion, more lag (e.g., 0.5 for very smooth)
- **Higher `min_cutoff`**: More responsive, less smoothing (e.g., 2.0 for fast tracking)
- **Higher `beta`**: More adaptive to velocity changes (e.g., 0.05 for dynamic movements)
- **Lower `beta`**: Less velocity-dependent (e.g., 0.01 for consistent smoothing)

**Note:** Filters `[x, y, heading, head_angle]` but not `t` or `action`.

---

### **Coordinate Mapping**

#### **Automatic Normalization**
The `_map_coordinates()` method is automatically called in `read()` to normalize coordinates to `[-1, 1]` based on `box_extents`.

**Process:**
1. Apply flipping (if enabled)
2. Normalize to `[0, 1]` based on box_extents
3. Apply rotation (if enabled)
4. Clamp to `[0, 1]`
5. Map to `[-1, 1]`

**Implementation:**
```python
def _map_coordinates(self, x: float, y: float) -> tuple[float, float]:
    """Map raw DLC coordinates to normalized [-1..1] based on box_extents.

    Values are clamped to [-1, 1] if outside the box.
    Supports flipping and 90-degree rotation.
    """
    left, top, right, bottom = self.box_extents
    width = right - left
    height = bottom - top

    if width == 0 or height == 0:
        return 0.0, 0.0

    # Apply flipping before normalization
    if self.flip_x:
        x = left + (right - x)
    if self.flip_y:
        y = top + (bottom - y)

    # Normalize to [0..1] range
    norm_x = (x - left) / width
    norm_y = (y - top) / height

    # Apply rotation (swap normalized coordinates)
    if self.rotate_90:
        norm_x, norm_y = norm_y, norm_x

    # Clamp to [0..1] then map to [-1..1]
    norm_x = max(0.0, min(1.0, norm_x))
    norm_y = max(0.0, min(1.0, norm_y))

    # Map from [0..1] to [-1..1]
    norm_x = 2.0 * norm_x - 1.0
    norm_y = 2.0 * norm_y - 1.0

    return norm_x, norm_y
```

**Example:**
```python
# Configure box extents for region of interest
dlc = DLCClient(
    box_extents=(100, 50, 540, 430),  # left, top, right, bottom
    flip_y=True,    # Invert Y for Unity coordinate system
    flip_x=False,
    rotate_90=False
)

# read() automatically applies normalization
pkt = dlc.read()
if pkt:
    t, x, y, heading, head_angle = pkt["vals"][:5]
    # x, y are now in [-1, 1] range
```

---

### **Data Logging**

#### **get_data() → dict**
```python
data = dlc.get_data()
# Returns:
{
    "dlc_read_time": [t1, t2, ...],
    "dlc_x": [x1, x2, ...],
    "dlc_y": [y1, y2, ...],
    "dlc_heading": [h1, h2, ...],
    "dlc_head_angle": [ha1, ha2, ...],
    "dlc_action": [a1, a2, ...]
}
```

#### **get_params() → dict**
```python
params = dlc.get_params()
# Returns configuration dict for logging/reproducibility
```

---

## DummyDLCClient Class

### **Purpose**
Stand-in for DLCClient when hardware is unavailable. Provides three modes:
1. **`pygame`**: Interactive window with mouse control (hold LMB to track cursor)
2. **`constant`**: Fixed position/heading at specified FPS
3. **`random`**: Random walk with Gaussian velocity

### **Constructor**

```python
DummyDLCClient(
    mode: str = "pygame",
    window_size=(640, 480),
    normalize: bool = True,
    invert_y: bool = True,
    fps: int = 120,
    const_vals=None,  # [x, y, heading_deg, head_angle_deg]
    seed: int = 0,
    apply_filter_always: bool = False,
    apply_filter_onread: bool = False,
    use_perf_counter=False
)
```

#### **Mode-Specific Parameters:**

**`mode="pygame"`:**
- **Window Controls:**
  - **Left Mouse Button (LMB)**: Toggle tracking (green border when active)
  - **Arrow Keys (← →)**: Rotate head (adjusts `head_angle`)
  - **Keypad `1` or `1` key**: Set `action=1.0`
  - **ESC**: Quit
- **Output:** Position follows cursor when tracking is ON; heading = direction of movement

**`mode="constant"`:**
- **`const_vals`**: `[x, y, heading, head_angle]` in pixels or normalized [0,1]
- **Output:** Static values at `fps` rate

**`mode="random"`:**
- **`seed`**: Random seed for reproducibility
- **Output:** Random positions with Gaussian velocity (sigma=0.2)

---

### **Data Format**

Same as `DLCClient`:
```python
{
    "time": float,
    "vals": [t_since, x, y, heading, head_angle, action]
}
```

**Normalization Behavior:**
- If `normalize=True`: x, y are mapped to `[-1, 1]` (2*u - 1 where u ∈ [0,1])
- If `normalize=False`: x, y are raw pixel coordinates

---
## Integration with UnityAgentTask

### **Task Configuration**

```python
task = UnityAgentTask(
    teensy=teensy,
    env_path="Build/MouseAR.exe",
    use_dlc=True,
    dlc_address=("localhost", 6000),  # or "dummy_pygame" for testing
    dlc_apply_filter_onread=False,
    dlc_apply_filter=True,  # apply filter in background thread
    dlc_apply_filter_inprocessor=False,  # or True for processor-side filtering
    dlc_box_extents=(0, 0, 640, 480),  # Region of interest
    dlc_flip_y=False,
    dlc_flip_x=False,
    dlc_rotate_90=False,
    dlc_oneeuro_beta=0.0,  # Filter parameters
    dlc_oneeuro_min_cutoff=1.0,
    dlc_oneeuro_d_cutoff=1.0,
    dlc_session_name="my_session"  # For recording
)
task.start()
```

### **Dummy Mode Selection**

```python
# Interactive pygame dummy
task = UnityAgentTask(..., dlc_address="dummy_pygame")

# Constant position dummy
task = UnityAgentTask(..., dlc_address="dummy_constant")

# Random walk dummy
task = UnityAgentTask(..., dlc_address="dummy_random")
```

---

## Data Export

### **Logged Data Structure**

```python
data = dlc.get_data()
# Keys:
#   dlc_read_time:   [t1, t2, ...]
#   dlc_x:           [x1, x2, ...]
#   dlc_y:           [y1, y2, ...]
#   dlc_heading:     [h1, h2, ...]
#   dlc_head_angle:  [ha1, ha2, ...]
#   dlc_action:      [a1, a2, ...]
```

**Usage in Task:**
```python
task_data = task.get_data()  # Includes DLC data via task.dlc_client.get_data()
# Save to JSON or HDF5
```
