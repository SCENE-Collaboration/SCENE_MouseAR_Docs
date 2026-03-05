# Task System Documentation

## Overview

The **Task** system provides a hierarchical framework for running behavioral experiments with Unity ML-Agents environments. The architecture consists of three layers:

1. **Task** (Base class): Hardware integration (Teensy) and lifecycle management
2. **UnityMultibehaviorTask**: Multi-behavior ML-Agents environment orchestration
3. **UnityAgentTask**: Full integration with control clients (DLC, Touch, TTL)

This layered design enables:
- Modular client integration (pose tracking, touchscreen, photodiode sync)
- Multi-agent/multi-behavior support
- Runtime parameter adjustment via side channels
- Comprehensive data logging with synchronized timestamps

---

## Architecture

```
┌───────────────────────────────────────────────────────────────────┐
│                       UnityAgentTask                              │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  Control Clients Integration                                │  │
│  │  - DLCClient (pose tracking)                                │  │
│  │  - TouchClient (touchscreen input)                          │  │
│  │  - TTLGenerator (photodiode sync)                           │  │
│  └─────────────────────────────────────────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  get_action_for(behavior_name) → Routes to:                │  │
│  │    - _dlc_action(spec)                                      │  │
│  │    - _touch_action(spec)                                    │  │
│  │    - _ttl_action(spec)                                      │  │
│  └─────────────────────────────────────────────────────────────┘  │
└───────────────────────────────┬───────────────────────────────────┘
                                 │ inherits
                                 ▼
┌───────────────────────────────────────────────────────────────────┐
│                  UnityMultibehaviorTask                           │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  Unity ML-Agents Environment Management                     │  │
│  │  - Multi-behavior support (behavior_list)                   │  │
│  │  - EnvironmentParametersChannel (training-time config)      │  │
│  │  - KvChannel (runtime parameter updates)                    │  │
│  │  - Episode/step/epoch tracking                              │  │
│  │  - LiveParamScheduler (adaptive rule engine)                │  │
│  └─────────────────────────────────────────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  Step Loop:                                                  │  │
│  │  1. Get actions for each behavior                           │  │
│  │  2. Set actions via env.set_actions()                       │  │
│  │  3. Step environment                                         │  │
│  │  4. Collect observations, rewards, done flags               │  │
│  │  5. Check terminal condition (any/all)                      │  │
│  │  6. Fire scheduler hooks; reset episode if done             │  │
│  └─────────────────────────────────────────────────────────────┘  │
└───────────────────────────────┬───────────────────────────────────┘
                                 │ inherits
                                 ▼
┌───────────────────────────────────────────────────────────────────┐
│                          Task (Base)                              │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  Hardware Communication (Teensy)                             │  │
│  │  - Serial interface to Teensy microcontroller               │  │
│  │  - Reward delivery: give_reward(duration_ms)                │  │
│  │  - TTL signaling: signal_ttl()                              │  │
│  │  - Water line draining: drain_water()                       │  │
│  │  - Raw input/output data logging from Teensy                │  │
│  └─────────────────────────────────────────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  Lifecycle & Timing                                          │  │
│  │  - start() / stop() / loop() abstract interface             │  │
│  │  - Configurable timing: time.time() or perf_counter()       │  │
│  │  - Session metadata: subject_id, session_name, start_time   │  │
│  └─────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────┘
```

---

## Inheritance Responsibilities

Each layer in the hierarchy has a clearly scoped responsibility. Understanding what each class owns is important when extending or debugging tasks.

### Task (Base) — Hardware communication layer

`Task` is the single point of contact with physical hardware. All Teensy commands go through this class and nowhere else.

**Owns:**
- Teensy serial interface (`self.teensy`) — initialized and reset in `__init__`
- `give_reward(duration_ms)` — opens the water solenoid via Teensy
- `signal_ttl()` — pulses the TTL output pin via Teensy
- `drain_water()` — holds the solenoid open for priming/draining
- Raw Teensy data export: `get_data()` returns `teensy_inputs` and `teensy_outputs`
- Timing infrastructure: `self.timing_func`, `self.start_time`, `self.cur_time`
- Abstract lifecycle interface: `start()`, `stop()`, `loop()` — each subclass must implement or call `super()`

**Does NOT own:**
- Unity environment — delegated entirely to `UnityMultibehaviorTask`
- Sensory input clients (DLC, Touch, TTL generator) — delegated to `UnityAgentTask`
- Session/episode logic — delegated to `UnityMultibehaviorTask`

---

### UnityMultibehaviorTask — Unity environment & episode orchestration layer

`UnityMultibehaviorTask` manages the full lifecycle of a Unity ML-Agents session: starting the executable, communicating over side channels, running the per-frame step loop, tracking episodes and epochs, and writing data to disk.

**Owns:**
- Unity environment startup and connection (`UnityEnvironment`, display args, port)
- Side channel management:
  - `EnvironmentParametersChannel` (`self.channel`) — float parameters sent at reset time (e.g. `episode_length`, `iti_length`)
  - `KvChannel` (`self.channel_kv`) — string key-value parameters sent at runtime (e.g. spawner config, distances)
  - `EngineConfigurationChannel` (`self.channel_engine`) — frame rate and physics settings
- Multi-behavior support: discovers behaviors from Unity, validates against `behavior_list`, maintains per-behavior state in `self.behaviors`
- Per-frame step loop (`loop()`):
  1. Calls `get_action_for(bname)` for every behavior — overridden by subclasses to supply real actions
  2. Batches all actions and advances the environment with `env.step()`
  3. Reads back states, rewards, and `done` flags per behavior
  4. Applies `reset_condition` policy (`"any"` or `"all"`) to decide when an episode ends
  5. Fires `LiveParamScheduler` hooks (`on_success`, `on_episode_end`, `on_epoch_advance`) and applies any resulting KV changes
  6. Calls `reset_episode()` (scheduler changes + TTL sync pulse) or `reset_environment()` as needed
- Epoch / session duration enforcement: `self.epochs`, `self.epoch_trials`, `self.max_session_duration`
- KV message capture: incoming Unity → Python KV messages are logged per step in `self.kv_messages`
- Runtime parameter change log: `self.runtime_params` records every scheduler-driven or manual KV update
- Data collection: `get_data()` aggregates all step-level arrays and merges with base `Task.get_data()`
- Parameter introspection: `get_params()` serialises the full task configuration
- Default `get_action_for()` returns zero actions — subclasses override this

**Does NOT own:**
- Physical hardware commands — calls `super().give_reward()` / `super().signal_ttl()` which go to `Task`
- Sensory client connections (DLC, Touch, TTL generator) — delegated to `UnityAgentTask`

---

### UnityAgentTask — Sensory client & action-building layer

`UnityAgentTask` is the production task class. It adds the external input pipelines that translate real-world sensor data into ML-Agents actions, while leaving all environment and hardware management to the parent classes.

**Owns:**
- **DLC module communication** (`DLCClient` / `DummyDLCClient`):
  - Socket connection to the DLC pose-estimation server
  - Coordinate normalisation, axis flipping/rotation, One-Euro filter application
  - `_dlc_action(spec)` — reads the latest pose packet and packs it into a continuous action vector
- **Touchscreen communication** (`TouchClient` / `DummyTouchClient`):
  - Socket connection to the touchscreen server
  - Velocity calculation, jitter removal, Y-axis inversion, speed scaling
  - `_touch_action(spec)` — reads the latest touch packet and packs position + velocity into a continuous action vector
- **Photo-TTL sync** (`TTLGenerator`):
  - Generates an 8-bit counter encoded as a photodiode-readable light pulse sequence
  - `_ttl_action(spec)` — exposes the current bit value as a continuous action
- **Action routing** (`get_action_for(bname)`):
  - Dispatches to the correct private method based on canonical behavior name:
    - `"DLCInput"` → `_dlc_action()`
    - `"TouchInput"` → `_touch_action()`
    - `"TTLInput"` → `_ttl_action()`
    - anything else → zeros (default from `UnityMultibehaviorTask`)
- Data enrichment: `get_data()` merges DLC, touch, and TTL client data on top of the parent's data dict

**Does NOT own:**
- Unity step loop — entirely in `UnityMultibehaviorTask.loop()`; `UnityAgentTask` only overrides `get_action_for()`
- Hardware reward/TTL — still in `Task`
- Scheduler logic — still in `UnityMultibehaviorTask`

---

## Task (Base Class)

### **Purpose**
Provides common infrastructure for all behavioral tasks:
- Teensy hardware integration
- Abstract lifecycle methods
- State tracking
- Data aggregation

---

### **Constructor**

```python
Task(teensy: Teensy | DummyTeensy)
```

#### **Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `teensy` | `Teensy` or `DummyTeensy` | Hardware interface for reward/TTL/sensors |

---

### **Abstract Methods** (Must be implemented by subclasses)

#### **start()**
```python
def start(self):
    """Initialize task, start hardware, open connections."""
    pass
```

#### **stop()**
```python
def stop(self):
    """Clean up, close connections, save data."""
    pass
```

#### **loop() → bool**
```python
def loop(self) -> bool:
    """
    Execute one iteration of task logic.

    Returns:
        bool: True to continue, False to stop task
    """
    pass
```

---

### **Hardware Control Methods**

#### **give_reward(duration_ms: int)**
```python
task.give_reward(100)  # 100 ms water pulse
```
- Sends `"W<duration>"` command to Teensy
- Opens solenoid valve for specified duration
- Typical range: 50-200 ms

#### **signal_ttl()**
```python
task.signal_ttl()
```
- Sends `"P"` command to Teensy
- Triggers 5V TTL pulse on output pin
- Duration defined in Teensy firmware (typically 5-10 ms)

#### **drain_water(duration_ms: int)**
```python
task.drain_water(5000)  # 5 seconds
```
- Sends `"D<duration>"` command to Teensy
- Opens valve for extended period (priming/draining)

---

### **Timing Utilities**

```python
task.timing_func()        # Returns current time (time.time() or perf_counter)
task.start_time           # Timestamp when task started
task.cur_time             # Current time (updated in loop)
```

---

### **State Tracking**

```python
task.running              # bool: Task is actively running
task.paused               # bool: Task is paused
task.stopped              # bool: Task has stopped
```

---

### **Data Collection**

#### **get_data() → dict**
```python
data = task.get_data()
# Returns teensy input/output logs:
{
    "teensy_input_time": [...],
    "teensy_input_analog": [...],
    "teensy_input_digital": [...],
    "teensy_output_time": [...],
    "teensy_output_command": [...]
}
```

#### **get_params() → dict**
```python
params = task.get_params()
# Returns task configuration (override in subclasses)
```

---

## UnityMultibehaviorTask

### **Purpose**
Manages Unity ML-Agents environments with multiple behaviors (agent types). Handles:
- Multi-behavior action routing
- Environment parameter channels (training + runtime)
- Episode/step/epoch tracking
- Reset conditions (any agent done vs all agents done)

---

### **Constructor**

```python
UnityMultibehaviorTask(
    teensy: Teensy,
    env_path: str,
    behavior_list: List[str],
    subject_id: str = "UnnamedMouse",
    epochs: np.ndarray = np.array([60.0]),
    epoch_trials: bool = False,
    agent_group: str = "default",
    display_args: Dict | None = None,
    reset_condition: str = "any",
    env_params: Dict | None = None,
    env_kv_params: Dict | None = None,
    reward_size: float = 0.0,
    use_perf_counter: bool = False
)
```

#### **Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `teensy` | `Teensy` | *required* | Hardware interface |
| `env_path` | `str` | *required* | Path to Unity executable |
| `behavior_list` | `list[str]` | *required* | List of behavior names to control |
| `subject_id` | `str` | `"UnnamedMouse"` | Subject identifier for data logging |
| `epochs` | `np.ndarray` | `[60.0]` | Epoch durations (seconds or trial counts) |
| `epoch_trials` | `bool` | `False` | If True, epochs are trial counts; if False, durations |
| `agent_group` | `str` | `"default"` | ML-Agents agent group name |
| `display_args` | `dict` | `None` | Unity display config (width, height, etc.) |
| `reset_condition` | `str` | `"any"` | Episode reset policy: `"any"` or `"all"` |
| `env_params` | `dict` | `None` | EnvironmentParametersChannel (training-time) |
| `env_kv_params` | `dict` | `None` | KvChannel initial parameters (runtime) |
| `reward_size` | `float` | `0.0` | Reward scaling factor |
| `use_perf_counter` | `bool` | `False` | Use `time.perf_counter()` for timing |

---

### **Behavior Management**

#### **Behavior Names**
Unity behaviors may have query string suffixes (e.g., `"MouseAgent?team=0"`). The task automatically canonicalizes names:

```python
# Unity behavior spec: "MouseAgent?team=0"
# Canonical name: "MouseAgent"

behavior_list = ["MouseAgent"]  # Use canonical name
```

#### **Behavior Mapping**
The task builds a `behavior_map` from canonical names to full names:

```python
self.behavior_map = {
    "MouseAgent": "MouseAgent?team=0",
    "TTLAgent": "TTLAgent"
}
```

---

### **Action Routing**

#### **get_action_for(behavior_name: str) → np.ndarray**
```python
def get_action_for(self, behavior_name: str) -> np.ndarray:
    """
    Return action for specified behavior.
    Override in subclasses to provide custom actions.

    Args:
        behavior_name: Canonical behavior name (e.g., "MouseAgent")

    Returns:
        np.ndarray: Action array matching behavior's action spec
    """
    spec = self.behaviors[behavior_name]["spec"]
    # Default: zero action
    if spec.action_spec.continuous_size > 0:
        return np.zeros(spec.action_spec.continuous_size, dtype=np.float32)
    else:
        return np.zeros(spec.action_spec.discrete_branches, dtype=np.int32)
```

---

### **Side Channels**

#### **EnvironmentParametersChannel** (Training-time configuration)
Set during environment initialization. Typically used for:
- Spawn rates
- Difficulty levels
- Environment dimensions

```python
env_params = {
    "spawn_rate": 2.0,
    "difficulty": 0.5,
    "arena_size": 10.0
}
task = UnityMultibehaviorTask(..., env_params=env_params)
```

#### **KvChannel** (Runtime parameter updates)
Set during task execution via `set_runtime_param()`:

```python
task.set_runtime_param("target_speed", "5.0")
task.set_runtime_param("reward_delay", "0.5")
```

**Unity C# Receiver:**
```csharp
public class RuntimeParamListener : MonoBehaviour
{
    void Update()
    {
        if (KvChannel.HasMessage("target_speed"))
        {
            float speed = float.Parse(KvChannel.GetMessage("target_speed"));
            // Apply speed...
        }
    }
}
```

---

### **Reset Conditions**

#### **`reset_condition="any"`** (Default)
Episode ends when **any** behavior reports `done=True`:

```python
# If MouseAgent OR TTLAgent is done → reset episode
```

#### **`reset_condition="all"`**
Episode ends when **all** behaviors report `done=True`:

```python
# Wait until MouseAgent AND TTLAgent are both done → reset episode
```

---

### **Step Loop**

```python
def loop(self) -> (bool, dict):
    # 1. Get actions for each behavior
    action_dict = {}
    for behavior_name in self.behavior_list:
        action_dict[behavior_name] = self.get_action_for(behavior_name)

    # 2. Set actions and step environment
    for behavior_name in self.behavior_list:
        full_name = self.behavior_map[behavior_name]
        self.env.set_actions(full_name, ActionTuple(continuous=action_dict[behavior_name]))
    self.env.step()

    # 3. Collect observations
    for behavior_name in self.behavior_list:
        step_result = self._get_step_result_for(behavior_name)
        state, reward, done = step_result
        self.behaviors[behavior_name]["state"] = state
        self.behaviors[behavior_name]["reward"] = reward
        self.behaviors[behavior_name]["done"] = done

    # 4. Check terminal condition
    any_done = any(self.behaviors[b]["done"] for b in self.behavior_list)
    all_done = all(self.behaviors[b]["done"] for b in self.behavior_list)
    self.terminal = any_done if self.reset_condition == "any" else all_done

    # 5. Reset episode if terminal
    if self.terminal:
        self.episode += 1
        self.reset_episode()
        self.terminal = False

    # 6. Check epoch completion
    if self.cur_time - self.start_time > self.epochs[self.epoch]:
        self.epoch += 1
        if self.epoch >= len(self.epochs):
            return False, self.get_info()  # Stop task

    return True, self.get_info()  # Continue
```

---

### **Data Logging**

#### **get_data() → dict**
```python
data = task.get_data()
# Returns:
{
    "episode": [0, 0, 0, 1, 1, ...],       # Episode numbers
    "step": [0, 1, 2, 0, 1, ...],          # Step within episode
    "step_time": [t0, t1, t2, ...],        # Timestamps
    "state": [state0, state1, ...],        # States per behavior (dict)
    "obs_states": [vis0, vis1, ...],       # Visual observations
    "action": [action0, action1, ...],     # Actions per behavior (dict)
    "reward": [r0, r1, ...],               # Rewards
    "terminal": [False, False, True, ...], # Terminal flags
    "runtime_params": [                    # Parameter changes
        {"key": "value", "time": t, "episode": e, "step": s},
        ...
    ],
    "kv_messages": [                       # KV channel messages
        {"timestamp": t, "episode": e, "step": s, "messages": {...}},
        ...
    ],
    # Plus teensy data from base class:
    "teensy_input_time": [...],
    "teensy_input_analog": [...],
    ...
}
```

---

## UnityAgentTask

### **Purpose**
Extends `UnityMultibehaviorTask` with control client integration:
- **DLCClient**: Pose tracking → Unity actions
- **TouchClient**: Touchscreen input → Unity actions
- **TTLGenerator**: Photodiode sync → Unity actions

---

### **Constructor**

```python
UnityAgentTask(
    # Base parameters (from UnityMultibehaviorTask)
    teensy: Teensy,
    env_path: str,
    subject_id: str = "UnnamedMouse",
    epochs: np.ndarray = np.array([60.0]),
    # ... (all UnityMultibehaviorTask params)

    # Control client parameters
    use_dlc: bool = False,
    dlc_address: str | Tuple = "dummy_constant",
    dlc_filter_mode: str = "always",
    dlc_filter_kwargs: Dict | None = None,
    dlc_flip_x: bool = False,
    dlc_flip_y: bool = False,
    dlc_rotate_90: bool = False,
    dlc_box_extents: List | None = None,

    use_touch: bool = False,
    touch_address: str | Tuple = "dummy_constant",
    touch_tx_mode: str = "rate",
    touch_tx_hz: float = 60.0,
    touch_invert_y: bool = True,
    touch_speed_gain: float = 1.0,
    touch_vector_window_ms: int = 200,

    use_photottl: bool = False,
    photottl_half_cell_sec: float = 0.05,
    photottl_period_sec: float = 5.0,
    photottl_n_bits: int = 8
)
```

#### **Key Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| **DLC Client** | | | |
| `use_dlc` | `bool` | `False` | Enable DLCClient |
| `dlc_address` | `str` or `tuple` | `"dummy_constant"` | IP:port or dummy mode |
| `dlc_filter_mode` | `str` | `"always"` | `"always"`, `"onread"`, or `"never"` |
| `dlc_filter_kwargs` | `dict` | `None` | One-Euro filter params |
| `dlc_flip_x` | `bool` | `False` | Flip X coordinate |
| `dlc_flip_y` | `bool` | `False` | Flip Y coordinate |
| `dlc_rotate_90` | `bool` | `False` | Rotate 90° clockwise |
| `dlc_box_extents` | `list` | `None` | Crop region `[xmin, xmax, ymin, ymax]` |
| **Touch Client** | | | |
| `use_touch` | `bool` | `False` | Enable TouchClient |
| `touch_address` | `str` or `tuple` | `"dummy_constant"` | IP:port or dummy mode |
| `touch_tx_mode` | `str` | `"rate"` | `"event"`, `"rate"`, or `"both"` |
| `touch_tx_hz` | `float` | `60.0` | Rate transmission frequency |
| `touch_invert_y` | `bool` | `True` | Invert Y axis |
| `touch_speed_gain` | `float` | `1.0` | Velocity scaling |
| `touch_vector_window_ms` | `int` | `200` | Velocity window duration |
| **TTL Generator** | | | |
| `use_photottl` | `bool` | `False` | Enable TTLGenerator |
| `photottl_half_cell_sec` | `float` | `0.05` | Half-cell duration (50ms) |
| `photottl_period_sec` | `float` | `5.0` | Burst period (5s) |
| `photottl_n_bits` | `int` | `8` | Counter bit width |

---

### **Dummy Mode Selection**

Instead of IP addresses, use strings to enable dummy clients:

```python
# DLC dummy modes
dlc_address="dummy_pygame"     # Interactive pygame window
dlc_address="dummy_constant"   # Static position/heading
dlc_address="dummy_random"     # Random walk

# Touch dummy modes
touch_address="dummy_pygame"   # Interactive pygame window (hold LMB)
touch_address="dummy_constant" # Static position/velocity
touch_address="dummy_random"   # Random positions

# Real hardware
dlc_address=("192.168.1.50", 5005)         # DLC server
touch_address=("192.168.1.100", 6001)      # Touchscreen server
```

---

### **Action Construction Methods**

#### **_dlc_action(spec) → np.ndarray**
```python
def _dlc_action(self, spec):
    size = spec.action_spec.continuous_size
    empty = np.zeros(size, dtype=np.float32)

    if not self.dlc_client:
        return empty

    pkt = self.dlc_client.read()
    if not pkt:
        return empty

    # Extract [x, y, heading, head_angle, action]
    vals = pkt.get("vals", [])
    vec = vals[1:]  # Drop timestamp
    return self._pack_and_clip(vec, size)
```

**Unity Receives:**
```
actions[0] = x           # Position X
actions[1] = y           # Position Y
actions[2] = heading     # Body direction
actions[3] = head_angle  # Head angle
actions[4] = action      # Auxiliary action
```

#### **_touch_action(spec) → np.ndarray**
```python
def _touch_action(self, spec):
    size = spec.action_spec.continuous_size
    empty = np.zeros(size, dtype=np.float32)
    empty[0] = 1.0  # Default to border

    if not self.touch_client:
        return empty

    pkt = self.touch_client.read()
    if not pkt:
        return empty

    # Pack [px, py, heading, speed01]
    vec = [
        pkt.get("px", 1.0),
        pkt.get("py", 0.0),
        pkt.get("heading", 0.0),
        pkt.get("speed01", 0.0)
    ]
    return self._pack_and_clip(vec, size)
```

**Unity Receives:**
```
actions[0] = px       # Position X [-1, 1]
actions[1] = py       # Position Y [-1, 1]
actions[2] = heading  # Direction [-1, 1]
actions[3] = speed01  # Speed [0, 1]
```

#### **_ttl_action(spec) → np.ndarray**
```python
def _ttl_action(self, spec):
    size = spec.action_spec.continuous_size
    empty = np.zeros(size, dtype=np.float32)

    if not self.ttl_generator:
        return empty

    ttl_val = self.ttl_generator.read()  # [0.0] or [1.0]
    return self._pack_and_clip(ttl_val, size)
```

**Unity Receives:**
```
actions[0] = ttl  # 0.0 or 1.0
```

---

### **Behavior Routing**

The `get_action_for()` method routes to the appropriate client based on behavior name:

```python
def get_action_for(self, behavior_name: str) -> np.ndarray:
    spec = self.behaviors[behavior_name]["spec"]

    if "dlc" in behavior_name.lower() or "mouse" in behavior_name.lower():
        return self._dlc_action(spec)
    elif "touch" in behavior_name.lower() or "finger" in behavior_name.lower():
        return self._touch_action(spec)
    elif "ttl" in behavior_name.lower() or "photo" in behavior_name.lower():
        return self._ttl_action(spec)
    else:
        # Default: zero action
        return np.zeros(spec.action_spec.continuous_size, dtype=np.float32)
```

---

### **Data Aggregation**

```python
def get_data(self) -> dict:
    data = super().get_data()  # UnityMultibehaviorTask data

    # Add DLC data
    if self.dlc_client:
        data.update(self.dlc_client.get_data())

    # Add Touch data
    if self.touch_client:
        data.update(self.touch_client.get_data())

    # Add TTL data
    if self.ttl_generator:
        data.update(self.ttl_generator.get_data())

    return data
```

**Full Data Structure:**
```python
{
    # Unity task data
    "episode": [...],
    "step": [...],
    "step_time": [...],
    "state": [...],
    "action": [...],
    "reward": [...],
    "terminal": [...],

    # Teensy data
    "teensy_input_time": [...],
    "teensy_input_analog": [...],
    "teensy_input_digital": [...],
    "teensy_output_time": [...],
    "teensy_output_command": [...],

    # DLC data (if use_dlc=True)
    "dlc_read_time": [...],
    "dlc_x": [...],
    "dlc_y": [...],
    "dlc_heading": [...],
    "dlc_head_angle": [...],

    # Touch data (if use_touch=True)
    "touch_read_time": [...],
    "touch_px": [...],
    "touch_py": [...],
    "touch_heading": [...],
    "touch_speed01": [...],

    # TTL data (if use_photottl=True)
    "ttl_time": [...],
    "ttl_value": [...]
}
```

---

## Configuration Examples

### **Example 1: DLC Pose Control Only**
```python
from mouse_ar.ctrl.teensy_python import Teensy
from mouse_ar.tasks.unity_agent_task import UnityAgentTask

teensy = Teensy(port="/dev/ttyACM0")

task = UnityAgentTask(
    teensy=teensy,
    env_path="Build/MouseAR.exe",
    subject_id="Mouse42",
    behavior_list=["MouseAgent"],
    epochs=np.array([300.0]),  # 5 minutes

    # Enable DLC with real server
    use_dlc=True,
    dlc_address=("192.168.1.50", 5005),
    dlc_filter_mode="onread",
    dlc_filter_kwargs={"min_cutoff": 1.0, "beta": 0.05},
    dlc_flip_y=True,

    # Disable other clients
    use_touch=False,
    use_photottl=False
)

task.start()
while task.loop()[0]:
    pass
task.stop()
task.save_data_to_json()
```

---

### **Example 2: Touchscreen + TTL Sync**
```python
task = UnityAgentTask(
    teensy=teensy,
    env_path="Build/MouseAR.exe",
    subject_id="Mouse42",
    behavior_list=["TouchFingerAgent", "TTLAgent"],

    # Enable Touch
    use_touch=True,
    touch_address=("192.168.1.100", 6001),
    touch_tx_mode="both",
    touch_tx_hz=120.0,
    touch_invert_y=True,

    # Enable TTL
    use_photottl=True,
    photottl_period_sec=5.0,
    photottl_half_cell_sec=0.05,

    # Disable DLC
    use_dlc=False
)

task.start()
while task.loop()[0]:
    pass
task.stop()
```

---

### **Example 3: All Clients with Dummy Modes (Testing)**
```python
task = UnityAgentTask(
    teensy=teensy,
    env_path="Build/MouseAR.exe",
    behavior_list=["MouseAgent", "TouchFingerAgent", "TTLAgent"],

    # DLC dummy (pygame interactive)
    use_dlc=True,
    dlc_address="dummy_pygame",

    # Touch dummy (constant position)
    use_touch=True,
    touch_address="dummy_constant",

    # TTL generator (always enabled for dummy)
    use_photottl=True
)

task.start()
# DLC pygame window opens; move mouse and press keys for control
```

---

### **Example 4: Runtime Parameter Updates**
```python
task = UnityAgentTask(...)
task.start()

# Change spawn rate at 60s
while task.loop()[0]:
    if task.cur_time - task.start_time > 60.0:
        task.set_runtime_param("spawn_rate", "5.0")
        break

# Change difficulty at 120s
while task.loop()[0]:
    if task.cur_time - task.start_time > 120.0:
        task.set_runtime_param("difficulty", "0.8")
        break

task.stop()
```

---

## Workflow Patterns

### **Pattern 1: Conditional Reward**
```python
class RewardTask(UnityAgentTask):
    def loop(self):
        continuing, info = super().loop()

        # Check for success event
        if self.behaviors["MouseAgent"]["reward"] > 0:
            self.give_reward(100)  # 100ms water

        return continuing, info
```

---

### **Pattern 2: External Event Triggering**
```python
class EventTask(UnityAgentTask):
    def loop(self):
        continuing, info = super().loop()

        # Read Teensy digital input (e.g., barcode scanner)
        if self.teensy.input_deque:
            sample = self.teensy.input_deque[-1]
            if sample["digital"] == 1:
                self.signal_ttl()  # Sync camera
                self.set_runtime_param("trial_start", str(sample["time"]))

        return continuing, info
```

---

### **Pattern 3: Multi-Epoch Training**
```python
# 3 epochs: 5 min warmup, 10 min training, 5 min cooldown
epochs = np.array([300.0, 600.0, 300.0])

task = UnityAgentTask(
    ...,
    epochs=epochs,
    env_params={
        "difficulty": 0.2  # Start easy
    }
)

task.start()
while task.loop()[0]:
    # Adjust difficulty per epoch
    if task.epoch == 1:
        task.set_runtime_param("difficulty", "0.5")
    elif task.epoch == 2:
        task.set_runtime_param("difficulty", "0.2")

task.stop()
```

---

## Data Analysis Example

```python
import json
import numpy as np
import matplotlib.pyplot as plt

# Load data
with open("UnityData_Mouse42_20250130_120000.json", "r") as f:
    data = json.load(f)

# Plot reward over time
episodes = np.array(data["episode"])
rewards = np.array(data["reward"])
step_times = np.array(data["step_time"])

# Cumulative reward per episode
unique_episodes = np.unique(episodes)
cumulative_rewards = [rewards[episodes == ep].sum() for ep in unique_episodes]

plt.figure(figsize=(10, 6))
plt.plot(unique_episodes, cumulative_rewards, 'o-')
plt.xlabel("Episode")
plt.ylabel("Cumulative Reward")
plt.title(f"Learning Curve: {data['params']['subject_id']}")
plt.grid(True)
plt.show()

# Plot DLC trajectory (if available)
if "dlc_x" in data:
    dlc_x = np.array(data["dlc_x"])
    dlc_y = np.array(data["dlc_y"])

    plt.figure(figsize=(8, 8))
    plt.plot(dlc_x, dlc_y, alpha=0.3)
    plt.xlabel("X Position")
    plt.ylabel("Y Position")
    plt.title("Mouse Trajectory")
    plt.axis("equal")
    plt.show()

# Analyze TTL bursts (if available)
if "ttl_time" in data:
    ttl_time = np.array(data["ttl_time"])
    ttl_value = np.array(data["ttl_value"])

    # Detect burst starts (rising edges after idle)
    diff = np.diff(np.concatenate([[0], ttl_value]))
    rising = np.where(diff == 1)[0]
    bursts = rising[np.concatenate([[True], np.diff(ttl_time[rising]) > 1.0])]

    print(f"Detected {len(bursts)} TTL bursts")
    print(f"Burst times: {ttl_time[bursts]}")
```

---

## Troubleshooting

### **Problem: Unity environment doesn't start**

**Solutions:**
1. Check `env_path` is correct:
   ```python
   import os
   assert os.path.exists("Build/MouseAR.exe")
   ```
2. Verify behavior names match Unity:
   ```python
   task.start()
   print(task.behavior_map)  # Should show available behaviors
   ```
3. Check display args:
   ```python
   display_args = {
       "width": 800,
       "height": 600,
       "quality_level": 2,
       "time_scale": 1.0
   }
   ```

---

### **Problem: No actions received by Unity agents**

**Solutions:**
1. Check `get_action_for()` is returning correct shape:
   ```python
   action = task.get_action_for("MouseAgent")
   print(f"Action shape: {action.shape}")
   print(f"Expected: {task.behaviors['MouseAgent']['spec'].action_spec.continuous_size}")
   ```
2. Verify clients are started:
   ```python
   task.start()
   print(f"DLC client: {task.dlc_client is not None}")
   print(f"Touch client: {task.touch_client is not None}")
   ```
3. Check client data availability:
   ```python
   pkt = task.dlc_client.read()
   print(f"DLC packet: {pkt}")
   ```

---

### **Problem: Episode never resets**

**Solutions:**
1. Check reset condition:
   ```python
   print(f"Reset condition: {task.reset_condition}")
   print(f"Behaviors done: {[task.behaviors[b]['done'] for b in task.behavior_list]}")
   ```
2. Verify Unity agents send `done=True`:
   - Check Unity C# `EndEpisode()` is called
3. Adjust reset condition:
   ```python
   task = UnityAgentTask(..., reset_condition="all")  # Wait for all agents
   ```

---

### **Problem: Data logging is incomplete**

**Solutions:**
1. Check clients are logging:
   ```python
   task.stop()
   data = task.get_data()
   print(f"DLC samples: {len(data.get('dlc_read_time', []))}")
   print(f"Touch samples: {len(data.get('touch_read_time', []))}")
   ```
2. Verify clients are reading data:
   ```python
   # In loop:
   if task.step % 100 == 0:
       print(f"DLC deque size: {len(task.dlc_client.filtered_deque)}")
   ```

---

## API Reference

### **Task**
```python
__init__(teensy)
start()                          # Abstract
stop()                           # Abstract
loop() -> bool                   # Abstract
give_reward(duration_ms: int)
signal_ttl()
drain_water(duration_ms: int)
get_data() -> dict
get_params() -> dict
```

### **UnityMultibehaviorTask**
```python
__init__(teensy, env_path, behavior_list, subject_id, epochs, epoch_trials,
         agent_group, display_args, reset_condition, env_params, env_kv_params,
         reward_size, use_perf_counter)
start()
stop()
loop() -> (bool, dict)
get_action_for(behavior_name: str) -> np.ndarray
set_runtime_param(key: str, value: str)
reset_episode()
get_data() -> dict
get_params() -> dict
save_data_to_json(filename: str | None)
```

### **UnityAgentTask**
```python
__init__(
    # All UnityMultibehaviorTask params, plus:
    use_dlc, dlc_address, dlc_filter_mode, dlc_filter_kwargs, dlc_flip_x,
    dlc_flip_y, dlc_rotate_90, dlc_box_extents,
    use_touch, touch_address, touch_tx_mode, touch_tx_hz, touch_invert_y,
    touch_speed_gain, touch_vector_window_ms,
    use_photottl, photottl_half_cell_sec, photottl_period_sec, photottl_n_bits
)
start()
stop()
get_action_for(behavior_name: str) -> np.ndarray
_dlc_action(spec) -> np.ndarray
_touch_action(spec) -> np.ndarray
_ttl_action(spec) -> np.ndarray
get_data() -> dict
```

---

## See Also

- **[DLCClient Documentation](DLCClient.md)** - Pose tracking client details
- **[TouchClient Documentation](TouchClient.md)** - Touchscreen client details
- **[Teensy Documentation](Teensy.md)** - Hardware interface details
- **[TTLGenerator Documentation](TTLGenerator.md)** - Photodiode sync details
- **[Unity Agents](../Unity/Agents.md)** - Unity agent implementation
- **[Unity Episode Management](../Unity/EpisodeManagement.md)** - Unity episode lifecycle

---
