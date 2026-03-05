# Unity Game Architecture

## Overview

The Unity game framework is built around a modular architecture that separates concerns into distinct, reusable components. The system enables researchers to configure complex behavioral experiments with minimal code changes through runtime parameter control.

## Core Architecture Layers

```
┌─────────────────────────────────────────────────────────────┐
│                    Python/ML-Agents Layer                   │
│  (Training scripts, Environment Parameters, KV Channels)    │
└─────────────────────────────────────────────────────────────┘
                           ▼ ▼ ▼
┌─────────────────────────────────────────────────────────────┐
│                   Parameter Control Layer                   │
│        KvManagersDirector + EnvParams Components            │
└─────────────────────────────────────────────────────────────┘
                           ▼ ▼ ▼
┌─────────────────────────────────────────────────────────────┐
│                  Episode Management Layer                   │
│     EpisodeManagerSingleWall + SequenceTargetManager        │
│         (Lifecycle, Timing, Events, Rewards)                │
└─────────────────────────────────────────────────────────────┘
                           ▼ ▼ ▼
┌─────────────────────────────────────────────────────────────┐
│                    Spawner Layer                            │
│  IEpisodeSpawner Interface + Concrete Implementations       │
│  (FloorTargets, GridTargets, ScreenSpawner, etc.)           │
└─────────────────────────────────────────────────────────────┘
                           ▼ ▼ ▼
┌─────────────────────────────────────────────────────────────┐
│                      Agent Layer                            │
│   ML-Agents (DlcAgent, TouchFingerAgent, TTLBehavior)       │
│        (Observations, Actions, Sensors)                     │
└─────────────────────────────────────────────────────────────┘
                           ▼ ▼ ▼
┌─────────────────────────────────────────────────────────────┐
│                   Interaction Layer                         │
│  StatefulTarget, StatefulWall, Colliders, Physics           │
└─────────────────────────────────────────────────────────────┘
                           ▼ ▼ ▼
┌─────────────────────────────────────────────────────────────┐
│                    Feedback Layer                           │
│  ColorOverlay, WhiteNoiseOverlayGPU, EpisodeScore           │
└─────────────────────────────────────────────────────────────┘
```

## Component Relationships

### Init/TTL integration

- `InitPhaseFlag`: boolean flag component for init-phase state.
- `SimpleTargetSpawnerAdapter`: exposes `SimpleTargetSpawner` through `IEpisodeSpawner` when needed.

### Camera and display utilities

- `PlaneOffAxisCamera`: computes off-axis projection matrix against a rectangular plane.
- `CameraEnvConfig`: maps env parameters to camera mode/FOV/clip/ortho-size.
- `CameraFollowNoRotation`: follows target position while keeping fixed camera rotation.
- `FollowXZFixedY`: follows target XZ with fixed Y for top/aux camera views.
- `MultiDisplayActivator`: activates selected Unity displays at startup/runtime.
- `RotateBottomScreen`: rotates camera/border layout from env param (`general.rotate_bottom_screen`).

### Interaction/parameter bridge utility

- `MoveByAction`: conditionally unlocks rigidbody movement only while nearby agents signal interaction.
- `ParamBridge`: lightweight direct `KvChannel` bridge for sequence text keys.

### Episode Managers ↔ Spawners

Episode managers orchestrate the game lifecycle but don't know *how* to create game objects. They depend on the `IEpisodeSpawner` interface:

```csharp
public interface IEpisodeSpawner
{
    void ClearAll();         // Remove all spawned objects
    void SpawnAll();         // Create player + targets
    int TargetsAlive();      // Count remaining targets
    GameObject GetPlayer();  // Get player instance
}
```

**Benefits:**
- Episode managers can work with any spawner implementation
- New game scenarios require only new spawner implementations
- Same episode logic works across different spatial layouts

**Connection Pattern:**
```
EpisodeManagerSingleWall
├── spawnerComponents: List<MonoBehaviour>
│   ├── [0] ScreenSpawnerAdapter
│   ├── [1] SideTargetsSpawnerAdapter
│   └── [2] FloorTargetsSpawnerAdapter
└── activeSpawnerIndex: 0  (which to use)
```

### Spawners: Implementation vs Adapter Pattern

Most spawners use a two-component architecture:

**1. Implementation Component** (e.g., `ScreenSpawnerFromObject`)
- Contains spawning logic, placement algorithms, prefab references
- Manages spawned object lifecycle
- Exposes configuration parameters

**2. Adapter Component** (e.g., `ScreenSpawnerAdapter`)
- Implements `IEpisodeSpawner` interface
- Delegates to implementation component
- Provides standardized API for episode managers

**Example:**
```csharp
// Implementation: ScreenSpawnerFromObject.cs
public class ScreenSpawnerFromObject : MonoBehaviour
{
    public void ClearAll() { /* spawning logic */ }
    public void SpawnAll() { /* spawning logic */ }
    public int TargetsAlive() { /* count logic */ }
}

// Adapter: ScreenSpawnerAdapter.cs
public class ScreenSpawnerAdapter : MonoBehaviour, IEpisodeSpawner
{
    public ScreenSpawnerFromObject spawner;

    public void ClearAll() => spawner.ClearAll();
    public void SpawnAll() => spawner.SpawnAll();
    public int TargetsAlive() => spawner.TargetsAlive();
    public GameObject GetPlayer() => spawner.GetPlayer();
}
```

**Why This Pattern?**
- Separates interface compliance from implementation
- Allows reuse of spawner logic without interface dependencies
- Easy to add new episode managers with different interfaces

### Parameter Control: Two Systems

The framework supports two independent parameter control mechanisms:

#### 1. ML-Agents EnvironmentParameters (Env Params)

**Source:** Python scripts → Unity ML-Agents Academy

**Usage:**
```csharp
var envParams = Academy.Instance.EnvironmentParameters;
float duration = envParams.GetWithDefault("episode_length", 10f);
```

**Characteristics:**
- only changed on env reset(cannot be changed mid-episode)
- Best for training-time configuration

**Example Flow:**
```
Python                    Unity
------                    -----
env_params = {            →  Academy.Instance.EnvironmentParameters
  "episode_length": 15        ↓
}                             EpisodeManagerSingleWall.StartEpisode()
                              ↓
                              episodeLength = envParams.GetWithDefault(...)
```

#### 2. KV Channel (Key-Value Side Channel)

**Source:** Python scripts → Unity via `KvChannel` side channel → `KvManagersDirector`

**Usage:**
```python
# Python
kv_channel.send_string("wallL.enabled=1")
kv_channel.send_string("wallL.episode_length=12")
kv_channel.send_string("wallL.start=1")
```

**Characteristics:**
- Control during runtime, some managers redraw, others apply on next episode
- Namespace-based (per-manager control)
- Managed by `KvManagersDirector` component

**Example Flow:**
```
Python                              Unity
------                              -----
kv.send("wallL.enabled=1")       →  KvManagersDirector.OnKv()
                                    ↓
                                    Parse "wallL" namespace
                                    ↓
                                    Find EpisodeManagerSingleWall with key="wallL"
                                    ↓
                                    manager.enabled = true
```

### Episode Lifecycle

#### EpisodeManagerSingleWall

**Simple task lifecycle:** Spawn targets → Agent interacts → Success (all cleared) or Timeout → ITI → Repeat

```
State Machine:
┌──────┐                    ┌─────────┐
│ Idle │────StartEpisode───→│ Running │
└──────┘                    └─────────┘
    ▲                            │
    │                            │ AllTargetsCleared
    │                            │ OR Timeout
    │                            ▼
    │                        ┌──────┐
    │                        │ ITI  │
    │                        └──────┘
    │                            │
    └────────────────────────────┘
         (if loopEpisodes=true)
```

**Event Sequence:**
```
StartEpisode()
  → OnEpisodeBegin (event)
  → _active.ClearAll()
  → _active.SpawnAll()
  → OnSpawningComplete (event)
  ↓
[Running State]
  → Check TargetsAlive()
  → If 0: OnAllTargetsCleared (event) → EndEpisode()
  → If timeout: EndEpisode()
  ↓
EndEpisode()
  → _active.ClearAll()
  → OnEpisodeEnd (event)
  → Enter ITI state
  ↓
[ITI State]
  → Wait itiLength seconds
  → If loopEpisodes: StartEpisode() again
```

#### SequenceTargetManager

**Sequence task lifecycle:** Spawn grid → Present targets one-by-one → Success (complete sequence) or Timeout/Wall collision → ITI → Repeat

```
State Machine:
┌──────┐                    ┌─────────┐
│ Idle │────StartEpisode───→│ Running │
└──────┘                    └─────────┘
    ▲                            │
    │                            │ Sequence Complete (Success)
    │                            │ OR Timeout/Wall Hit (Failure)
    │                            ▼
    │                        ┌──────┐
    │                        │ ITI  │
    │                        └──────┘
    │                            │
    └────────────────────────────┘

```

**Event Sequence:**
```
StartEpisode()
  → OnEpisodeBegin (event)
  → spawner.SpawnGrid() (create all targets + walls)
  → Reset all targets to Static
  → Activate hazard walls (parallel)
  → AdvanceStep() (activate first target)
  ↓
[Running State - Per Step]
  → OnStepAdvanced(stepNum) (event)
  → OnStepLabel("Target #5") (event)
  → Current target = Active
  → Wait for player dwell OR timeout
  ↓
[Step Complete]
  → HandleTargetCompleted()
  → score.AddPoint(1)
  → AdvanceStep() (next target)
  ↓
[Parallel: Hazard Walls]
  → If player hits wall: HandleWallTriggered()
  → If within grace period: OnWallIgnoredDuringGrace (event)
  → Else: EndEpisode(false) → failure
  ↓
[Sequence Complete]
  → All steps done
  → OnEpisodeSuccess (event) → ColorOverlay flash
  → OR OnEpisodeTimeout (event) → WhiteNoiseOverlay
  → EndEpisode(success/fail)
  ↓
EndEpisode()
  → Unhook all targets/walls
  → Set lastEpisodeSuccess, lastScore
  → OnEpisodeEnd (event)
  → Enter ITI state (OnITIStart event)
  → Wait itiSeconds → StartEpisode() again
```

## Agent Integration

### ML-Agents Components

All agents inherit from Unity ML-Agents `Agent` base class:

```csharp
public class DlcAgent : Agent
{
    public override void CollectObservations(VectorSensor sensor)
    {
        // Add observations to network input
    }

    public override void OnActionReceived(ActionBuffers actions)
    {
        // Process network output (continuous/discrete actions)
    }

    public override void Heuristic(in ActionBuffers actionsOut)
    {
        // Manual control for testing
    }
}
```

### Episode Manager ↔ Agent Connection

Agents connect to episode managers through the **`MultiEpisodeToAgentBridge`** component:

```
MultiEpisodeToAgentBridge
├── wallManagers: List<EpisodeManagerSingleWall>
├── sequenceManagers: List<SequenceTargetManager>
└── agents: List<TTLReceiverAgent>

// Bridge listens to manager events:
OnAllTargetsCleared → agent.OnCorrect()  (reward)
OnEpisodeTimeout    → agent.OnIncorrect() (punishment)
```

**TTLReceiverAgent** mixin adds episode outcome tracking:
```csharp
public class TTLReceiverAgent : Agent
{
    public void OnCorrect()  { /* reward, end episode */ }
    public void OnIncorrect() { /* punish, end episode */ }
}
```

### Visual Observations

Agents can include camera sensors for visual observations:

```csharp
// In DlcAgent.cs (configured via env params)
var envParams = Academy.Instance.EnvironmentParameters;
bool cameraEnabled = envParams.GetWithDefault("DlcAgent.camera_enabled", 0f) > 0.5f;
int width = (int)envParams.GetWithDefault("MouseVisuals.camera_width", 84);
int height = (int)envParams.GetWithDefault("MouseVisuals.camera_height", 84);
bool grayscale = envParams.GetWithDefault("MouseVisuals.camera_grayscale", 0f) > 0.5f;

if (cameraEnabled)
{
    var cam = attachGo.AddComponent<CameraSensorComponent>();
    cam.Width = width;
    cam.Height = height;
    cam.Grayscale = grayscale;
}
```

## Spawner Types Overview

### FloorTargetsSpawner
**Use case:** Navigate 2D floor space, push/chase objects
- Spawns 1-3 vertical target areas on floor (trigger volumes)
- Spawns 1 MoveObject (Rigidbody sphere/cube)
- Integer-spaced Z positions with jitter and overlap prevention
- Physics-based object interactions
- Optional distance/rotation-based coloring
- Optional "lock until action" mechanic

### GridTargetsSpawner
**Use case:** Grid-based sequence tasks with walls
- Spawns N×N grid of StatefulTarget objects
- Spawns walls between tiles (hazards)
- Used by SequenceTargetManager for sequential navigation
- Targets have dwell-to-complete mechanic
- Walls can be hazards (immediate fail)

### ScreenSpawnerFromObject
**Use case:** 2D touchscreen-style tasks
- Spawns targets on virtual wall surface (OrthoScreenFromObject)
- Non-overlapping placement with padding
- Configurable vertical band (minYFraction, maxYFraction)
- Player positioned on wall, targets are 2D projections

### SideTargetsSpawnerFromObject
**Use case:** Combined side wall + floor targets
- Spawns 1-4 target objects in floor area
- Spawns 1-2 target areas on side walls
- Configurable positioning and scales
- Mixed 3D navigation + wall interaction

### SimpleTargetSpawner
**Use case:** Minimal navigation target
- Single invisible trigger cube at fixed position
- Simplest possible target setup
- Good for basic navigation tests

## Visual Feedback System

### Success Feedback: ColorOverlay

```csharp
// Triggered on episode success
ColorOverlay overlay;
overlay.SetColor(Color.green);
overlay.Play(0.2f); // brief green flash
```
Multiple playback modes (flash, fade)

### Failure Feedback: WhiteNoiseOverlayGPU

```csharp
// Triggered on timeout/failure
WhiteNoiseOverlayGPU overlay;
overlay.Play(0.5f); // animated noise punishment
```

**Features:**
- GPU shader-based animated noise
- Configurable FPS and opacity
- Region control (fullscreen/partial)
- Punishment signal for agent

### Episode-Manager Hookup

Both managers support automatic overlay triggering:

```csharp
// In EpisodeManagerSingleWall
[Header("Reward Flash on Success")]
public bool displayRewardFlash = false;
public float rewardDisplayDuration = 0.2f;

[Header("Noise Overlay")]
public bool displayNoiseOverlay = false;
public float noiseDisplayDuration = 0.2f;

// Automatic triggering in code:
if (displayRewardFlash)
{
    var overlay = FindObjectOfType<ColorOverlay>();
    if (overlay) overlay.Play(rewardDisplayDuration);
}
```

## Configuration Strategies

### Editor-Only Configuration
Parameters can also be modified directly in the Unity Editor for quick testing.


### GUI Configuration

Interactive experiments, real-time parameter tuning, behavioral testing

**Workflow:**
```bash
# 1. Launch GUI
python -m mouse_ar.gui.unity_task_gui

# 2. Load config file (contains all profiles)
#    File: mouse_ar/tasks/configs/hockey.game.toml

# 3. Select profile from dropdown
#    - "Default" (base parameters)
#    - "RL" (fast execution for training)

# 4. Adjust parameters in Parameters tab
#    - Edit values (turn red when modified)
#    - Click "Send params (diff-only)" to apply

# 5. Monitor live during experiment
#    - Epochs, episodes, steps
#    - Rewards (per-trial and total)
#    - Session duration

# 6. Data automatically saved on Stop
#    UnityData_TestMouse_20251104_143022.json
```

### Programmatic Configuration (Python Scripts)


**Example:**
```python
from mouse_ar.tasks.unity_agent_task import UnityAgentTask
from mouse_ar.ctrl.teensy_python import Teensy

teensy = Teensy(port="/dev/ttyACM0")

# Define parameters (fake examples)
env_kv_params = {
    "difficulty": "0.5",
    "target_color": "blue",
    "reward_type": "immediate"
}

env_params = {
    "episode_length": 15.0,
    "iti_length": 3.0,
    "target_size": 0.3
}

# Create task
task = UnityAgentTask(
    teensy=teensy,
    env_path="Build/Hockey.x86_64",
    behavior_list=["DLCInput"],
    env_kv_params=env_kv_params,
    env_params=env_params,
    use_dlc=True,
    dlc_address=("192.168.1.50", 5005),
    subject_id="Mouse42"
)

# Run experiment
task.start()
while task.loop():
    # Optional: runtime parameter adjustment
    if task.episode == 10:
        task.set_runtime_param("difficulty", "0.7")
task.stop()
task.save_data_to_json()
```

### TOML Config Files (Profile System)

**When to use:** Multiple parameter sets, shared configurations, version control

TOML configuration files support a profile-based system for managing experimental parameters. Profiles allow you to define multiple parameter sets in a single file and switch between them.

**Example:**
```python
from mouse_ar.ctrl.utils.config_loader import load_config

# Load with specific profile
env_kv, env_params, cfg = load_config(
    "mouse_ar/tasks/configs/hockey.game.toml",
    profile="Training"  # or "RL", "Testing", or None for default
)

# Use in task
task = UnityAgentTask(
    teensy=teensy,
    env_kv_params=env_kv,
    env_params=env_params,
    **cfg.get("game", {})
)
```

**See:** [Python Config System Documentation](../python/ConfigSystem.md) for complete TOML profile system details, file structure, and best practices.

### Runtime Parameter Updates

**Example:**
```python
# During task execution
task.start()

for episode in range(100):
    # Curriculum: increase difficulty
    if episode == 25:
        task.set_runtime_param("difficulty", "0.6")
    elif episode == 50:
        task.set_runtime_param("difficulty", "0.8")
    elif episode == 75:
        task.set_runtime_param("difficulty", "1.0")

    task.loop()

task.stop()

# All parameter changes logged in task.runtime_params
# [{"difficulty": "0.6", "time": 120.5, "episode": 25, "step": 1240}, ...]
```

### EnvParams Components (Per-Spawner)

**When to use:** Per-spawner parameter control from Python

**Components:**
- `FloorTargetsSpawnerEnvParams`
- `ScreenSpawnerEnvParams`
- `SideTargetsSpawnerEnvParams`
- `GridTargetsSpawnerEnvParams`
- `SimpleTargetSpawnerEnvParams`

**Pattern:**
```csharp
public class FloorTargetsSpawnerEnvParams : MonoBehaviour
{
    public FloorTargetsSpawner _sp;  // spawner reference

    void Start()
    {
        StartCoroutine(WaitForAcademyAndApply());
    }

    IEnumerator WaitForAcademyAndApply()
    {
        while (!Academy.IsInitialized) yield return null;
        ApplyParams();
    }

    void ApplyParams()
    {
        var envp = Academy.Instance.EnvironmentParameters;
        _sp.numTargetAreas = (int)envp.GetWithDefault($"{prefix}.num_areas", _sp.numTargetAreas);
        _sp.targetX = envp.GetWithDefault($"{prefix}.target_x", _sp.targetX);
        // ... apply all parameters
        TryRespawnOrClear();  // rebuild with new params
    }
}
```


### 1. Separation of Concerns
- **Episode Managers:** Lifecycle and timing only
- **Spawners:** Object creation and placement only
- **Agents:** Observations and actions only
- **Adapters:** Interface compliance only

### 2. Parameter Naming Conventions

**Global params:**
```
general.iti_length
general.episode_length
general.enable_reporting
```

**Namespaced params (KV):**
```
<manager_id>.<property>
wallL.enabled
wallL.episode_length
seqA.target_sequence
```

**Spawner params (Env):**
```
<prefix>.<property>
hockeyFloor.num_areas
touchDestroy.num_targets
simpleTarget.position_x
```



## See Also

### **Unity Documentation**
- **[Episode Management System](EpisodeManagement.md)** - Detailed lifecycle docs
- **[Spawner Reference](Spawners.md)** - All spawner implementations
- **[Parameter Control](ParameterSystem.md)** - Env params and KV channels
- **[Agent System](Agents.md)** - ML-Agents integration
- **[Visual Feedback](VisualFeedback.md)** - Overlays and scoring

### **Python Documentation**
- **[Config System](../python/ConfigSystem.md)** - TOML profile system and configuration management
- **[GUIs](../python/GUIs.md)** - UnityTaskGUI and TeensyControlGUI user guide
- **[Tasks API](../python/Tasks.md)** - UnityAgentTask and task system
- **[Overview](../python/Overview.md)** - Complete system architecture
