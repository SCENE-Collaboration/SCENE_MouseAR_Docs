# Python Control System - Overview

## Introduction

The **Python Control System** provides a complete framework for running behavioral neuroscience experiments with Unity ML-Agents environments. It integrates:

- **Pose Tracking** (DeepLabCut)
- **Touchscreen Input** (Raspberry Pi controller)
- **Hardware Control** (Teensy microcontroller)
- **Photodiode Synchronization** (TTL bursts)
- **Multi-behavior Tasks** (Unity ML-Agents)

This modular architecture enables researchers to:
- Run closed-loop experiments with real-time sensory input
- Synchronize behavior with neural recordings
- Control reward delivery and environmental parameters
- Log comprehensive multi-modal data

### **Graphical User Interfaces (GUIs)**

Three PyQt-based GUIs simplify setup and operation:

- **UnityTaskGUI** - Configure and run experiments with live monitoring, parameter editing, and automatic data saving
- **TeensyControlGUI** - Hardware testing, water delivery calibration, and sensor monitoring
- **Data Transfer GUI** (`dj_pipeline/gui_transfer`) - Session metadata entry, file attachment, and local/remote transfer

See [GUIs.md](GUIs.md) for complete user guide.
For transfer workflow details, see [DataTransferGUI.md](DataTransferGUI.md).

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        PYTHON CONTROL LAYER                         │
│                                                                     │
│  ┌────────────────────────────────────────────────────────────┐     │
│  │                    UnityAgentTask                          │     │
│  │  - Orchestrates all control clients                        │     │
│  │  - Routes actions to Unity behaviors                       │     │
│  │  - Aggregates multi-modal data                             │     │
│  └────────────────────────────────────────────────────────────┘     │
│                           │                                         │
│         ┌─────────────────┼─────────────────┬─────────────┐         │
│         │                 │                 │             │         │
│         ▼                 ▼                 ▼             ▼         │
│  ┌──────────┐    ┌──────────────┐   ┌──────────┐   ┌──────────┐     │
│  │   DLC    │    │ TouchClient  │   │  Teensy  │   │   TTL    │     │
│  │  Client  │    │              │   │  Serial  │   │Generator │     │
│  │          │    │ (Touchscreen)│   │          │   │          │     │
│  └────┬─────┘    └──────┬───────┘   └────┬─────┘   └────┬─────┘     │
└───────┼─────────────────┼──────────────────┼────────────┼───────────┘
        │                 │                  │            │
        │ Socket          │ Socket           │ Serial     │ (Internal)
        │ (multiproc)     │ (multiproc)      │ (USB)      │
        │                 │                  │            │
        ▼                 ▼                  ▼            ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────┐
│ DLC Server   │  │  Raspberry   │  │   Teensy     │  │  Unity   │
│ (Pose Est.)  │  │  Pi Touch    │  │ Microctrl.   │  │ Display  │
│              │  │ Controller   │  │              │  │ (Corner) │
└──────────────┘  └──────────────┘  └──────────────┘  └────┬─────┘
                                                           │
                                                           ▼
                                                    ┌────────────┐
                                                    │ Photodiode │
                                                    │  Circuit   │
                                                    └────────────┘
```

---

## Quick Start

### **1. Install Dependencies**

```bash
cd SCENE_MouseAR
pip install -e .
```

### **2. Basic Task Setup**

```python
from mouse_ar.ctrl.teensy_python import Teensy
from mouse_ar.tasks.unity_agent_task import UnityAgentTask
import numpy as np

# Initialize hardware
teensy = Teensy(port="/dev/ttyACM0")

# Create task with DLC pose control
task = UnityAgentTask(
    teensy=teensy,
    env_path="Build/MouseAR.exe",
    subject_id="Mouse42",
    behavior_list=["DLCInput"],
    epochs=np.array([300.0]),

    # Enable DLC (real server)
    use_dlc=True,
    dlc_address=("192.168.1.50", 5005),
    **kwargs
)

# Run task
task.start()
while task.loop()[0]:
    pass
task.stop()

# Save data
task.save_data_to_json()
```

### **3. Testing with Dummy Clients**
One can run the task without hardware by using dummy modes. Hereby we replace the input from DLC with an interactive pygame window:
```python
# Use interactive pygame controls (no hardware needed)
task = UnityAgentTask(
    teensy=teensy,
    env_path="Build/MouseAR.exe",
    behavior_list=["DLCInput"],

    use_dlc=True,
    dlc_address="dummy_pygame"  # Opens interactive window
)

task.start()
# Control agent with mouse and keyboard in pygame window
```

### **4. Using the Graphical Interface**

For easier setup and monitoring, use the UnityTaskGUI:

```bash
# Launch GUI
python -m mouse_ar.gui.unity_task_gui

# In GUI:
# 1. Load config file (*.game.toml)
# 2. Select profile (e.g., "Training")
# 3. Enter mouse name and weight
# 4. Click "Start"
# 5. Monitor live statistics
# 6. Click "Stop" to save data
```

See [GUIs.md](GUIs.md) for complete GUI documentation.

---

## Core Components

### **Graphical User Interfaces**

| GUI | Purpose | Documentation |
|-----|---------|---------------|
| **UnityTaskGUI** | Configure experiments, live monitoring, parameter editing | [GUIs.md](GUIs.md) |
| **TeensyControlGUI** | Hardware testing, water calibration, sensor monitoring | [GUIs.md](GUIs.md) |
| **Data Transfer GUI** | DataJoint dropdown metadata, dataset-based file auto-discovery, transfer to local/remote storage | [DataTransferGUI.md](DataTransferGUI.md) |

### **Control Clients**

| Client | Purpose | Documentation |
|--------|---------|---------------|
| **DLCClient** | DeepLabCut pose tracking → Unity | [DLCClient.md](DLCClient.md) |
| **TouchClient** | Touchscreen input → Unity | [TouchClient.md](TouchClient.md) |
| **Teensy** | Hardware control (reward, TTL, sensors) | [Teensy.md](Teensy.md) |
| **TTLGenerator** | Photodiode sync bursts → Unity | [TTLGenerator.md](TTLGenerator.md) |

### **Task System**
We use an inheritance hierarchy for tasks:
| Layer | Purpose | Documentation |
|-------|---------|---------------|
| **Task** | Base class with hardware integration | [Tasks.md](Tasks.md) |
| **UnityMultibehaviorTask** | Multi-behavior ML-Agents orchestration | [Tasks.md](Tasks.md) |
| **UnityAgentTask** | Full client integration (DLC/Touch/TTL) | [Tasks.md](Tasks.md) |

---

## Data Flow

### **Real-Time Control Loop**

```
EVERY GAME STEP (e.g., 200 Hz):

1. Read Control Clients (if enabled)
   - DLCClient.read()      → [x, y, heading, head_angle]
   - TouchClient.read()    → [px, py, dx, dy]
   - TTLGenerator.read()   → [ttl_state]

2. Route to Unity Behaviors
   - DLCInput   ← DLC data
   - TouchInput ← Touch data
   - TTLInput   ← TTL data

3. Step Unity Environment
   - Unity.step()
   - Collect observations, rewards, done flags

4. Check Reward Conditions
   - If reward > 0 → teensy.give_reward(100ms)

5. Log Data
   - All client reads
   - Unity states/actions/rewards
   - Teensy commands/inputs
   - Runtime parameter changes

6. Check Terminal Conditions
   - Episode done? → Reset episode (no env reset)
   - Epoch done? → Stop or next epoch
```

---

## Configuration Patterns

### **Pattern 1: DLC Pose Control Only**

```python
task = UnityAgentTask(
    teensy=teensy,
    env_path="Build/MouseAR.exe",
    behavior_list=["DLCInput"],

    use_dlc=True,
    dlc_address=("localhost", 6001),
    **dlckwargs,
    use_touch=False,
    use_photottl=False
)
```

**Use Cases:**
- Freely moving mouse with overhead camera
- Closed-loop augmented reality navigation
- Position-triggered stimulus delivery

---

### **Pattern 2: Touchscreen + Photodiode Sync**

```python
task = UnityAgentTask(
    teensy=teensy,
    env_path="Build/MouseAR.exe",
    behavior_list=["TouchInput", "TTLInput"],

    use_touch=True,
    touch_address=("192.168.1.100", 6002),
    touch_tx_hz=120.0,

    use_photottl=True,
    photottl_period_sec=5.0,
    use_dlc=False
)
```


---

### **Pattern 3: All Modalities**

```python
task = UnityAgentTask(
    teensy=teensy,
    env_path="Build/MouseAR.exe",
    behavior_list=["DLCInput", "TouchInput", "TTLInput"],

    use_dlc=True,
    dlc_address=("localhost", 6001),

    use_touch=True,
    touch_address=("192.168.1.100", 6002),

    use_photottl=True
)
```

---

## Dummy Modes for Testing

All clients support dummy modes for hardware-free development:

### **Interactive Testing (Pygame)**

```python
# DLC: Control with mouse + keyboard (WASD, Q/E rotate)
dlc_address="dummy_pygame"

# Touch: Control with mouse (hold LMB to simulate touch)
touch_address="dummy_pygame"
```

### **Constant Values**

```python
# DLC: Static position/heading
dlc_address="dummy_constant"

# Touch: Static position/velocity
touch_address="dummy_constant"
```

### **Random Walk**

```python
# DLC: Random positions/headings
dlc_address="dummy_random"

# Touch: Random positions/velocities
touch_address="dummy_random"
```

---

## Runtime Parameter Control

Adjust Unity environment parameters during task execution using KvSidechannel:

```python
task = UnityAgentTask(...)
task.start()

task.set_runtime_param("key", "value")

```

**Unity C# Receiver:**
```csharp
if (KvChannel.HasMessage("key"))
{
    float value = float.Parse(KvChannel.GetMessage("key"));
    // Apply value...
}
```

---

## Data Logging

### **Logged Data Structure**

All data saved to JSON file via `task.save_data_to_json()`:

```text
{
  "params": {
    "subject_id": "Mouse42",
    "env_path": "Build/MouseAR.exe",
    "epochs": [300.0],
    "use_dlc": true,
    "use_touch": true,
    ...
  },

  "episode": [0, 0, 0, 1, 1, ...],
  "step": [0, 1, 2, 0, 1, ...],
  "step_time": [0.0, 0.016, 0.032, ...],

  "state": [{...}, {...}, ...],
  "action": [{...}, {...}, ...],
  "reward": [0.0, 0.0, 1.0, ...],
  "terminal": [false, false, true, ...],

  "dlc_read_time": [0.0, 0.016, ...],
  "dlc_x": [0.5, 0.51, ...],
  "dlc_y": [0.3, 0.31, ...],
  "dlc_heading": [1.2, 1.21, ...],

  "touch_read_time": [0.0, 0.016, ...],
  "touch_px": [-0.2, -0.19, ...],
  "touch_py": [0.4, 0.41, ...],

  "teensy_input_time": [0.0, 0.01, ...],
  "teensy_input_analog": [512, 515, ...],
  "teensy_input_digital": [0, 0, 1, ...],
  "teensy_output_time": [5.2, 12.3, ...],
  "teensy_output_command": ["W100", "W100", ...],

  "ttl_time": [0.0, 0.05, 0.1, ...],
  "ttl_value": [0.0, 1.0, 0.0, ...],

  "runtime_params": [
    {"difficulty": "0.8", "time": 120.0, "episode": 5, "step": 240},
    ...
  ],

  "kv_messages": [
    {"timestamp": 120.0, "episode": 5, "step": 240, "messages": {...}},
    ...
  ]
}
```

---

## Integration with Unity

### **Behavior Setup**

Unity agents must have matching behavior names:

**Python:**
```python
behavior_list=["DLCInput", "TouchInput", "TTLInput"]
```

**Unity C#:**
```csharp
public class DlcAgent : Agent
{
    public override void Initialize()
    {
        // Behavior name: "DLCInput"
    }
}
```

### **Action Receiving**

**Python sends:**
```python
# DlcAgent actions (from DLC)
actions = [x, y, heading, head_angle]
```

**Unity receives:**
```csharp
public override void OnActionReceived(ActionBuffers actions)
{
    float x = actions.ContinuousActions[0];
    float y = actions.ContinuousActions[1];
    float heading = actions.ContinuousActions[2];
    float headAngle = actions.ContinuousActions[3];

    // Apply to agent transform...
}
```

---

## Hardware Setup

### **Required Components**

| Component | Purpose | Connection |
|-----------|---------|------------|
| **Teensy 4.0** | Reward, TTL, sensors | USB Serial to PC |
| **Solenoid Valve** | Water delivery | Teensy GPIO → MOSFET |
| **DLC Server** | Pose estimation using DLCLive-GUI| Network (multiprocessing) |
| **Raspberry Pi** | Touchscreen controller | Network (multiprocessing) |
| **Photodiode** | Frame sync | Unity display → ADC |

### **Network Topology**

```
┌─────────────────────────────────────────────┐
│        Experimental PC (Python)             │
│  - UnityAgentTask                           │
│  - DLCClient (client)                       │
│  - TouchClient (client)                     │
└───────┬───────────────────┬─────────────────┘
        │ Ethernet          │ Ethernet
        │ 0.0.0.0           │ 192.168.1.x
        │                   │
        ▼                   ▼
┌──────────────────┐  ┌──────────────────────┐
│  DLC Server PC   │  │  Raspberry Pi        │
│  0.0.0.0         │  │  192.168.1.100       │
│  Port: 6000      │  │  Port: 6001          │
│                  │  │  TouchController     │
└──────────────────┘  └──────────────────────┘
```

---

## Related Documentation

### **Python System**
- [GUIs](GUIs.md) - Complete GUI user guide (UnityTaskGUI and TeensyControlGUI)
- [Config System](ConfigSystem.md) - TOML profile system and configuration management
- [Tasks](Tasks.md) - Task system hierarchy and API
- [DLCClient](DLCClient.md) - DeepLabCut integration
- [TouchClient](TouchClient.md) - Touchscreen integration
- [Teensy](Teensy.md) - Hardware control and serial protocol
- [TTLGenerator](TTLGenerator.md) - Photodiode synchronization

### **Unity System**
- [Unity Overview](../Unity/Overview.md) - Unity game architecture
- [Unity Agents](../Unity/Agents.md) - ML-Agents implementation
- [Episode Management](../Unity/EpisodeManagement.md) - Unity episode lifecycle
- [Parameter System](../Unity/ParameterSystem.md) - Environment parameters and KV channels

### **Touchscreen System**
- [Touchscreen Overview](../touchscreen/Overview.md) - Quick reference
- [Touchscreen Architecture](../touchscreen/TouchscreenArchitecture.md) - Complete system design

### **Hardware Guides**
- [Teensy Setup Guide](Teensy.md) - Wiring and firmware
- [DLC Server Setup](DLCClient.md) - Pose estimation server

---

## API Quick Reference

### **Task Creation**

```python
from mouse_ar.tasks.unity_agent_task import UnityAgentTask

task = UnityAgentTask(
    teensy=teensy,
    env_path="path/to/unity.exe",
    behavior_list=["Behavior1", "Behavior2"],

    use_dlc=True,
    dlc_address=("ip", port),

    use_touch=True,
    touch_address=("ip", port),

    use_photottl=True
)
```

### **Task Control**

```python
task.start()                              # Initialize
task.loop()                               # Step once (returns (bool, dict))
task.stop()                               # Clean up
task.save_data_to_json(filename)         # Save data
```

### **Runtime Control**

```python
task.give_reward(duration_ms)            # Water delivery
task.signal_ttl()                        # TTL pulse
task.set_runtime_param(key, value)       # Update Unity parameter
```

### **Data Access**

```python
data = task.get_data()                   # All logged data
params = task.get_params()               # Configuration
info = task.get_info()                   # Current state
```
