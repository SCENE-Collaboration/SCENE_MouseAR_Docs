# DLC Processor Documentation

## Overview

**DLC Processors** are server-side components that process pose estimation data from DLCLive and broadcast it to multiple clients. They provide:

- Multi-client broadcasting (no blocking on connection acceptance)
- Real-time pose calculations (center, heading, head angle)
- Optional One-Euro filtering
- Remote recording control from clients
- Thread-safe operation
- Session-based data logging

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    DLCLive Pipeline                          │
│  Camera → DLC Model → Processor.process(pose) → Return pose  │
└─────────────────────────┬────────────────────────────────────┘
                          │
                          ▼
        ┌─────────────────────────────────────┐
        │    MyProcessor_socket (Server)       │
        │                                      │
        │  Main Thread:                        │
        │  • process(pose) - called by DLCLive│
        │  • Calculate center/heading/angle    │
        │  • Optional filtering                │
        │  • Broadcast to all clients          │
        │  • Conditional logging (if recording)│
        │                                      │
        │  Background Threads:                 │
        │  • _accept_loop() - accept new       │
        │    connections (non-blocking)        │
        │  • _rx_loop(client) - per-client     │
        │    command receiver                  │
        │                                      │
        │  Thread-Safe:                        │
        │  • self._recording (Event)           │
        │  • self._stop (Event)                │
        │  • self.conns (set with locks)       │
        └────┬─────────────────┬────────────────┘
             │                 │
             │                 │ (Multiple clients)
             ▼                 ▼
        ┌─────────┐       ┌─────────┐
        │ Client1 │       │ Client2 │
        │ (Unity) │       │(Python) │
        └─────────┘       └─────────┘
```

---

## Class Hierarchy

```
Processor (from dlclive)
    │
    ├─ BaseProcessor_socket
    │   • Network setup (Listener, accept loop, broadcast)
    │   • Timing function selection
    │   • Basic data logging (timestamps, steps, original pose)
    │   • Recording control (Event-based flag)
    │   • Session name management
    │
    └─ MyProcessor_socket (inherits BaseProcessor_socket)
        • Pose calculations (center, heading, head angle)
        • One-Euro filtering (optional)
        • Additional data storage (center_x, center_y, heading, head_angle)
```

---

## BaseProcessor_socket

### **Purpose**
Base class providing network infrastructure, timing, and basic data logging. Designed for easy extension with custom pose processing logic.

### **Constructor**

```python
BaseProcessor_socket(
    bind=("0.0.0.0", 6000),
    authkey=b"secret password",
    use_perf_counter=False,
    save_original=False
)
```

#### **Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `bind` | `tuple[str, int]` | `("0.0.0.0", 6000)` | Server address and port |
| `authkey` | `bytes` | `b"secret password"` | Authentication key for clients |
| `use_perf_counter` | `bool` | `False` | Use `time.perf_counter()` instead of `time.time()` |
| `save_original` | `bool` | `False` | Save raw DLC pose arrays (54 keypoints) |

### **Key Features**

**1. Multi-Client Broadcasting**
- Non-blocking connection acceptance via background thread
- Automatic dead connection cleanup
- Thread-safe connection set

**2. Recording Control**
- Thread-safe `_recording` Event flag
- Only logs data when recording is active
- Remote control via client commands

**3. Session Management**
- `session_name` property sets filename automatically
- Format: `{session_name}_dlc_processor_data.pkl`

**4. Command Handling**
Processes control messages from clients:
- `set_session_name` - Updates session name and filename
- `start_recording` - Sets recording flag, clears queues
- `stop_recording` - Clears recording flag
- `save` - Triggers data save to file
- `set_filter` - Enable/disable filtering (MyProcessor_socket only) ⭐ NEW
- `set_filter_params` - Update filter parameters (MyProcessor_socket only) ⭐ NEW

### **Methods**

```python
process(pose, **kwargs) -> pose
```
- Base implementation: saves original pose, broadcasts raw pose
- Override in subclasses for custom processing
- Always returns unmodified pose (DLCLive requirement)

```python
broadcast(payload)
```
- Sends payload to all connected clients
- Automatically removes dead connections

```python
stop()
```
- Stops accept loop
- Closes all client connections
- Cleans up resources

```python
save(filename) -> int
```
- Saves logged data to pickle file
- Returns: 1 (success), 0 (no file), -1 (error)

```python
get_data() -> dict
```
- Returns dictionary with all logged data
- Keys: `time_stamp`, `step`, `frame_time`, `pose_time`, `original_pose`

---

## MyProcessor_socket

### **Purpose**
Production-ready processor that calculates mouse pose metrics (center, heading, head angle) with optional One-Euro filtering.

### **Constructor**

```python
MyProcessor_socket(
    bind=("0.0.0.0", 6000),
    authkey=b"secret password",
    use_perf_counter=False,
    use_filter=False,
    filter_kwargs=None,
    save_original=False
)
```

#### **Additional Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `use_filter` | `bool` | `False` | Apply One-Euro filter to calculated values |
| `filter_kwargs` | `dict` | `{"min_cutoff": 1.0, "beta": 0.02, "d_cutoff": 1.0}` | Filter parameters |

### **Pose Calculations**

**1. Weighted Center**
```python
# Head keypoints: nose, left/right ear, head base
head_xy = xy[[0, 1, 2, 3, 4, 5, 6, 26], :]
head_conf = conf[[0, 1, 2, 3, 4, 5, 6, 26]]
center = np.average(head_xy, axis=0, weights=head_conf)
```

**2. Heading (Body Orientation)**
```python
# Body axis: tail_base → neck
body_axis = xy[7] - xy[13]
body_axis /= sqrt(np.sum(body_axis**2))
heading = atan2(body_axis[1], body_axis[0])
heading_degrees = degrees(heading)  # [0, 360)
```

**3. Head Angle (Head vs Body)**
```python
# Head axis: neck → nose
head_axis = xy[0] - xy[7]
head_axis /= sqrt(np.sum(head_axis**2))
# Angle between body and head axes
head_angle = acos(body_axis @ head_axis) * sign  # radians
```

### **Filtering**

**One-Euro Filter Applied to:**
- `center_x`
- `center_y`
- `heading` (filtered in unwrapped space, wrapped after)
- `head_angle`

**Filtering Strategy:**
1. Filter calculated values (4 filters) NOT raw keypoints (54 filters)
2. Confidence-weighted averaging happens BEFORE filtering
3. Heading filtered in unwrapped space, wrapped to [0, 360) after

**Why Filter Calculated Values?**
- More efficient (4 vs 54 filters)
- Better signal quality (weighted average vs individual noisy points)
- Easier parameter tuning
- More intuitive behavior

### **Broadcast Format**

```python
payload = [timestamp, center_x, center_y, heading_degrees, head_angle_radians]
```

### **Data Export**

```python
save_dict = {
    # Base class data
    "start_time": float,
    "time_stamp": np.array,
    "step": np.array,
    "frame_time": np.array,
    "pose_time": np.array,
    "use_perf_counter": bool,

    # MyProcessor specific
    "x_pos": np.array,
    "y_pos": np.array,
    "heading_direction": np.array,
    "head_angle": np.array,
    "use_filter": bool,
    "filter_kwargs": dict
}
```

---

## Usage Examples

### **Example 1: Basic Usage with DLCLive**

```python
from dlclive import DLCLive
from dlc_processor_socket import MyProcessor_socket

# Create processor
processor = MyProcessor_socket(
    bind=("0.0.0.0", 6000),
    use_filter=True,
    filter_kwargs={"min_cutoff": 1.0, "beta": 0.02, "d_cutoff": 1.0}
)

# Create DLCLive instance with processor
dlc_live = DLCLive(
    model_path="/path/to/dlc/model",
    processor=processor
)

# Initialize
dlc_live.init_inference()

# Process frames
for frame in video_stream:
    pose = dlc_live.get_pose(frame)
    # Processor automatically broadcasts to clients
```

### **Example 2: Multiple Sessions**

```python
# Processor runs continuously, clients control recording

# Client controls (from DLCClient):
client.set_session_name("trial_001")
client.start_recording()
# ... run trial ...
client.stop_recording()
client.trigger_save()  # Saves "trial_001_dlc_processor_data.pkl"

# Next trial
client.set_session_name("trial_002")
client.start_recording()
# ... run trial ...
client.stop_recording()
client.trigger_save()  # Saves "trial_002_dlc_processor_data.pkl"
```

### **Example 3: Custom Processor**

```python
from dlc_processor_socket import BaseProcessor_socket

class MyCustomProcessor(BaseProcessor_socket):
    """Custom processor that only tracks nose position."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.nose_x = deque()
        self.nose_y = deque()

    def _clear_data_queues(self):
        """Clear custom queues."""
        super()._clear_data_queues()
        self.nose_x.clear()
        self.nose_y.clear()

    def process(self, pose, **kwargs):
        """Extract and broadcast nose position."""
        curr_time = self.timing_func()

        # Extract nose (keypoint 0)
        nose_x, nose_y = pose[0, :2]

        # Store if recording
        if self.recording:
            self.nose_x.append(nose_x)
            self.nose_y.append(nose_y)
            self.time_stamp.append(curr_time)

        # Broadcast
        payload = [curr_time, nose_x, nose_y]
        self.broadcast(payload)

        return pose

    def get_data(self):
        """Export custom data."""
        save_dict = super().get_data()
        save_dict["nose_x"] = np.array(self.nose_x)
        save_dict["nose_y"] = np.array(self.nose_y)
        return save_dict
```

---

## Recording Control

### **Recording Flag (Thread-Safe)**

```python
self._recording = Event()  # Thread-safe flag

@property
def recording(self):
    return self._recording.is_set()
```

**Why Event instead of bool?**
- Thread-safe atomic operations
- No race conditions between RX thread (commands) and main thread (processing)
- Python's recommended pattern for inter-thread signaling

### **Recording Workflow**

```
[Client] → set_session_name("exp_001")
                ↓
[Processor] session_name = "exp_001"
            filename = "exp_001_dlc_processor_data.pkl"

[Client] → start_recording()
                ↓
[Processor] _recording.set()  # Enable recording
            _clear_data_queues()  # Clear all deques
            curr_step = 0

[DLCLive] calls process(pose) continuously
                ↓
[Processor] if self.recording:
                self.time_stamp.append(time)
                self.center_x.append(x)
                # ... store data
            self.broadcast(payload)  # Always broadcast

[Client] → stop_recording()
                ↓
[Processor] _recording.clear()  # Disable recording

[Client] → trigger_save()
                ↓
[Processor] pickle.dump(get_data(), file)
            Saves to "exp_001_dlc_processor_data.pkl"
```

---

## Thread Safety

### **Thread-Safe Components**

1. **Recording Flag**: `Event()` with atomic operations
2. **Stop Flag**: `Event()` for clean shutdown
3. **Connection Set**: Operations on `set` are atomic in CPython

### **Thread Interactions**

| Thread | Purpose | Accesses |
|--------|---------|----------|
| Main (DLCLive) | `process(pose)` | Read `self.recording`, write to deques |
| Accept Loop | Accept new clients | Write to `self.conns` |
| RX Loop (per-client) | Receive commands | Call `_handle_client_message()` |
| Command Handler | Process commands | Set/clear `self._recording`, call `_clear_data_queues()` |

### **Potential Race Conditions**

✅ **Safe**: Reading `self.recording` while command thread sets it
- `Event.is_set()` is atomic

✅ **Safe**: Multiple clients sending commands
- Commands processed sequentially in each client's RX thread

⚠️ **Not thread-safe**: `deque` modifications
- But only modified in main thread when `recording=True`
- Commands only clear queues when setting `recording=True`
- No concurrent writes to deques

---

## Performance

**Latency:**
- Pose calculation: ~0.5 ms
- Filtering (if enabled): ~0.1 ms
- Broadcast to 2 clients: ~0.5 ms
- **Total overhead**: ~1-2 ms per frame

**Throughput:**
- Supports up to 200 fps camera
- Limited by DLCLive inference speed, not processor

**Memory:**
- Base: ~5 MB
- Per session (10 min @ 60 fps): ~20 MB
- Unbounded deques: grows until stopped

**CPU:**
- Idle: <1%
- Active (60 fps): ~2-3%
- Accept loop: negligible

---

## Configuration Tips

### **For Low Latency**
```python
processor = MyProcessor_socket(
    use_perf_counter=True,  # More precise timing
    use_filter=False        # No filtering delay
)
```

### **For Smooth Motion**
```python
processor = MyProcessor_socket(
    use_filter=True,
    filter_kwargs={
        "min_cutoff": 0.5,   # Lower = smoother
        "beta": 0.01,        # Lower = less responsive
        "d_cutoff": 1.0
    }
)
```

### **For Maximum Data Logging**
```python
processor = MyProcessor_socket(
    save_original=True  # Save raw 54-keypoint poses
)
```

---

## Troubleshooting

### **Problem: Clients can't connect**

**Solutions:**
1. Check processor is running:
   ```bash
   netstat -an | grep 6000
   ```
2. Verify firewall allows port 6000
3. Check bind address:
   ```python
   processor = MyProcessor_socket(bind=("0.0.0.0", 6000))  # Allow external
   # vs
   processor = MyProcessor_socket(bind=("127.0.0.1", 6000))  # Localhost only
   ```

### **Problem: Recording not starting**

**Solutions:**
1. Check client is connected before sending commands
2. Verify command format:
   ```python
   client.send_command("start_recording")  # Correct
   # NOT: client.send("start_recording")
   ```
3. Check processor logs:
   ```
   LOG.info("Recording started, data queues cleared")
   ```

### **Problem: Data file is empty**

**Solutions:**
1. Ensure recording was started: `client.start_recording()`
2. Check recording flag: processor should log "Recording started"
3. Verify session name was set: `client.set_session_name("...")`
4. Confirm trigger_save() was called after stop_recording()

### **Problem: Heading jumps at 0°/360° boundary**

**Solution:**
- Already handled! Heading is filtered in unwrapped space, then wrapped:
  ```python
  # Filter in unwrapped space (e.g., -10° to 370°)
  filtered_heading = self.filters["heading"](t, heading)
  # Then wrap to [0, 360)
  heading = filtered_heading % 360
  ```

---

## API Reference

### **BaseProcessor_socket**

```python
__init__(bind, authkey, use_perf_counter, save_original)
process(pose, **kwargs) -> pose
broadcast(payload)
stop()
save(filename) -> int
get_data() -> dict

# Properties
session_name: str
recording: bool (read-only)

# Protected methods (override in subclasses)
_clear_data_queues()
_handle_client_message(msg)
```

### **MyProcessor_socket**

```python
__init__(bind, authkey, use_perf_counter, use_filter, filter_kwargs, save_original)
process(pose, **kwargs) -> pose
get_data() -> dict

# Inherited from BaseProcessor_socket
broadcast(payload)
stop()
save(filename) -> int
session_name: str
recording: bool
```
