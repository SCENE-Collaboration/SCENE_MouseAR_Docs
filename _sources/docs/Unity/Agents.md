# Agent System Reference

## Overview

Agents are ML-Agents components that we use to interact between python and Unity game. They collect observations, execute actions, and receive rewards based on episode outcomes.

---

## Why Inputs Are Split Across Multiple Agents

Each physical input source (pose tracking, touchscreen, photodiode sync) is wired to a **separate ML-Agents behavior** rather than merged into a single agent. This is an architectural decision with several concrete reasons:

### 1. ML-Agents requires a fixed action and observation spec per behavior

A Unity behavior's action space (number of continuous/discrete branches, their sizes) and observation space are **fixed at build time** inside the behavior spec. Combining DLC pose (5 continuous actions) and TTL signal (1 continuous action) into one agent would require a 6-element action vector where the TTL slot is always irrelevant to the pose logic and vice versa. Separate behaviors keep each spec minimal and semantically coherent.

### 2. Independent disablement and substitution

Because each input is a distinct behavior, any of them can be dropped, replaced with a dummy, or run offline without touching the others:

```python
# Hockey session: no touchscreen, DLC + TTL only
behavior_list = ["TTLInput", "DLCInput"]
use_dlc   = True
use_touch = False

# RL training: no physical hardware at all, agent provides DLCInput
behavior_list = ["TTLInput", "DLCInput"]
use_dlc   = False
use_photottl = False             # zeros sent for TTLInput
```

Removing a behavior from `behavior_list` or replacing it with zeros does not require recompiling Unity.

### 4. Reward and episode boundary isolation

ML-Agents ties reward issuance and `EndEpisode()` calls to individual agents. `TTLReceiverAgent` is the agent that receives episode outcomes (`OnCorrect` / `OnIncorrect`) from `MultiEpisodeToAgentBridge`. `DlcAgent` observes the scene but never calls `EndEpisode()` itself. Keeping them separate means reward logic is localised to the TTL agent, and the DLC agent's episode boundary is driven purely by the environment reset signal — its `OnEpisodeBegin()` is a no-op.

### 5. Python-side action routing is trivially extensible

`UnityAgentTask.get_action_for(bname)` dispatches by canonical behavior name:

```python
if bare == "DLCInput"   and self.use_dlc:    return ("continuous", self._dlc_action(spec))
if bare == "TouchInput" and self.use_touch:  return ("continuous", self._touch_action(spec))
if bare == "TTLInput"   and self.use_photottl: return ("continuous", self._ttl_action(spec))
# default: zeros
```

Adding a new input source means adding one new Unity agent with its own behavior name, one `if bare == "NewInput"` branch in Python, and nothing else. The step loop in `UnityMultibehaviorTask` iterates over `behavior_list` generically and does not need modification.

### 6. Visual observations can be attached selectively

`DlcAgent` optionally carries a `CameraSensorComponent` for visual observations (e.g. a top-down camera for RL training). Attaching a camera sensor to TTLReceiverAgent would be meaningless. The per-agent separation makes it natural to add or remove sensors from exactly the agents that need them, controlled via env params at runtime (`DlcAgent.camera_enabled`).

---

## Agent Types

### DlcAgent

**Purpose:** Navigate on floor/wall surface using direct position + heading control

**Action Space:** Continuous[5]
- `actions[0]`: X position (normalized -1 to 1, mapped to U coordinate 0-1)
- `actions[1]`: Y position (normalized -1 to 1, mapped to V coordinate 0-1)
- `actions[2]`: Heading in degrees (0 to 360, absolute rotation around Y axis)
- `actions[3]`: Head angle (unused, reserved for future use)
- `actions[4]`: Emitted action (integer, compared to `emitAction` to set interact state)

**Observation Space:** Continuous[5]
- `obs[0]`: World position X (meters)
- `obs[1]`: World position Z (meters)
- `obs[2]`: Screen-space U coordinate (normalized 0-1)
- `obs[3]`: Screen-space V coordinate (normalized 0-1)
- `obs[4]`: Heading angle (radians, relative to +Z axis in x-z plane)
- Optional: Camera sensor (84×84×1 or 84×84×3 pixels if enabled)

**Configuration:**
```csharp
[Header("Wiring")]
public OrthoScreenFromObject screen;  // Wall surface reference

[Header("Placement")]
public float faceOffset = -0.1f;
public bool clampFullyInside = true;

[Header("Actions")]
public int emitAction = 42;  // Action emission tracking

[Header("Visual Sensor")]
public Camera obsCamera;
public string cameraEnvKey = "DlcAgent.camera_enabled";
public bool cameraEnabledDefault = false;
public int cameraWidth = 84;
public int cameraHeight = 84;
public bool cameraGrayscale = false;
public string cameraSensorName = "obs_cam";
```

**Visual Observations (Optional):**
- Camera sensor can be enabled via env param
- Configurable resolution and grayscale
- Auto-attached at Awake() based on `camera_enabled` param


### TouchFingerAgent

**Purpose:** Simple Touch control via teleportation to NDC coordinates, Currently not used. Was replaced by position aware PlayerAgent3DOnScreen for touchscreen tasks.

**Action Space:** Continuous[2]
- `actions[0]`: Y position (normalized device coordinates -1 to 1)
- `actions[1]`: X position (normalized device coordinates -1 to 1)

**Observation Space:** Continuous[3]
- `obs[0]`: U position on projection plane (normalized 0-1)
- `obs[1]`: V position on projection plane (normalized 0-1)
- `obs[2]`: Azimuth (sin of heading angle relative to plane)

**Configuration:**
```csharp
public TouchFingerTeleporter Teleporter;  // Teleportation component
```

**Usage:**
```python
# Python action (direct position)
action = np.array([y_ndc, x_ndc])  # Each in [-1, 1]

# Observation
obs = np.array([
    u,              # UV [0, 1]
    v,              # UV [0, 1]
    azimuth_sin     # Sin of heading angle
])
```


### PlayerAgent3DOnScreen

**Purpose:** TouchFinger controller which is aware of mouse position and viewing angle for AR-based touchscreen interaction with on-line view.

**Action Space:** Continuous[2] (or [4] for compatibility)
- `actions[0]`: X position (normalized -1 to 1, mapped to U 0-1 on screen)
- `actions[1]`: Y position (normalized -1 to 1, mapped to V 0-1 on screen)
- `actions[2]`: Unused (compatibility padding)
- `actions[3]`: Unused (compatibility padding)

**Observation Space:** Continuous[2]
- `obs[0]`: U position on screen (normalized 0-1)
- `obs[1]`: V position on screen (normalized 0-1)

**Configuration:**
```csharp
[Header("Wiring")]
public OrthoScreenFromObject screen;

[Header("Placement")]
public float faceOffset = -0.1f;
public bool clampFullyInside = true;
public bool teleport = true;      // Instant vs smooth movement
public float followLerp = 20f;    // Smooth movement speed
```

**Movement Modes:**
- **Teleport** (`teleport=true`): Instant position update
- **Smooth** (`teleport=false`): Lerp to target with `followLerp` speed

**Clamping:**
- If `clampFullyInside=true`: Keep entire object within screen bounds
- Computes planar half-extents from renderers/colliders
- Pads UV range to prevent clipping

### TTLReceiverAgent

**Purpose:** Emit TTL signal for screen synchronization. Additionally receives episode outcomes from MultiEpisodeToAgentBridge to provide reward/punishment feedback as neutral agent. Also monitors ITI state.

**Implementation note:** class name is `TTLReceiverAgent` (in `Assets/Scripts/Agents/TTLBehavior.cs`).

**Action Space:** Continuous[1]
- `actions[0]`: TTL signal (0 or 1, threshold 0.5)

**Observation Space:** Continuous[4]
- `obs[0]`: Patch channel (0 or 1, indicates TTL state)
- `obs[1]`: ITI flag (0 = episode active, 1 = in ITI period)
- `obs[2]`: Init phase flag (0 = not in init phase, 1 = in init phase)
- `obs[3]`: Latency measurement (Action->EndOfFrame delay in milliseconds)

**Configuration:**
```csharp
[Header("Visual TTL Output")]
public Image patch;           // UI Image for photodiode
public Color onColor = Color.white;
public Color offColor = Color.black;

[Header("Integration")]
public EpisodeScore score;
public ITIFlag itiFlag;
public InitPhaseFlag initPhaseFlag;

[Header("Latency Debug")]
public bool debugLatency = false;  // Enable latency logging
```

**Reward Interface:**
```csharp
public void OnCorrect()
{
    SetReward(+1f);
    EndEpisode();
}

public void OnIncorrect()
{
    SetReward(-1f);
    EndEpisode();
}
```


**TTL Signal:**
- Agent outputs continuous action [0-1]
- If action >= 0.5: patch color = white (onColor)
- If action < 0.5: patch color = black (offColor)
- Patch visible to photodiode for hardware sync

### Init/ITI Observations During Initialization Period

`TTLReceiverAgent` receives explicit phase state from two flag components:

- `InitPhaseFlag` (`InInitPhase`)
- `ITIFlag` (`InITI`)

These flags are driven by `MultiEpisodeToAgentBridge` event wiring:

- `OnEpisodeBegin` → `itiFlag.EndITI()` and `initPhaseFlag.StartInitPhase()` (if init enabled)
- `OnInitPhaseComplete` → `initPhaseFlag.EndInitPhase()`
- `OnEpisodeEnd` → `itiFlag.StartITI()`

`CollectObservations()` then emits:

- patch state (`obs[0]`),
- ITI flag (`obs[1]`),
- init-phase flag (`obs[2]`),
- action→end-of-frame latency ms (`obs[3]`).

This makes the initialization period directly observable to the TTL policy.

**Phase Tracking Components:**

**ITIFlag** - Tracks inter-trial interval state
```csharp
public class ITIFlag : MonoBehaviour
{
    public bool InITI { get; private set; }
    public void StartITI() => InITI = true;
    public void EndITI() => InITI = false;
}
```

**InitPhaseFlag** - Tracks initialization phase state
```csharp
public class InitPhaseFlag : MonoBehaviour
{
    public bool InInitPhase { get; private set; }
    public void StartInitPhase() => InInitPhase = true;
    public void EndInitPhase() => InInitPhase = false;
}
```

**Integration via MultiEpisodeToAgentBridge:**
- Listens to `OnEpisodeBegin` → calls `itiFlag.EndITI()` and `initPhaseFlag.StartInitPhase()` (if init enabled)
- Listens to `OnInitPhaseComplete` → calls `initPhaseFlag.EndInitPhase()`
- Listens to `OnEpisodeEnd` → calls `itiFlag.StartITI()`
- TTLReceiverAgent observes both flags to provide episode state context

**Latency Measurement:**
- High-precision Stopwatch tracks time from `OnActionReceived()` to end of frame
- Measures Unity's internal processing latency (excludes GPU/OS delays)
- Exposed as observation for adaptive timing or analysis
- Optional debug logging via `debugLatency` flag


---

## Integration Patterns

### Pattern 1: SingleWall + PlayerAgent3DOnScreen

```
Scene:
├── Wall (OrthoScreenFromObject)
│   ├── ScreenSpawnerFromObject
│   ├── ScreenSpawnerAdapter
│   └── (spawns Player with PlayerAgent3DOnScreen)
├── EpisodeManagerSingleWall
│   └── spawnerComponents[0] → ScreenSpawnerAdapter
├── MultiEpisodeToAgentBridge
│   ├── wallManagers[0] → EpisodeManagerSingleWall
│   └── agents[0] → TTLReceiverAgent
└── AgentGameObject (TTLReceiverAgent)

Flow:
1. ScreenSpawner creates Player with PlayerAgent3DOnScreen
2. PlayerAgent3DOnScreen receives actions, moves on wall
3. Player destroys targets via collision
4. EpisodeManager detects all cleared
5. Bridge calls TTLReceiverAgent.OnCorrect()
6. TTLReceiverAgent gets +1 reward, episode ends
```

### Pattern 2: FloorTargets + DlcAgent

```
Scene:
├── FloorSpawner
│   ├── FloorTargetsSpawner
│   ├── FloorTargetsSpawnerAdapter
│   └── (spawns MoveObject, TargetAreas)
├── Player (DlcAgent + Rigidbody)
├── EpisodeManagerSingleWall
│   └── spawnerComponents[0] → FloorTargetsSpawnerAdapter
├── MultiEpisodeToAgentBridge
│   ├── wallManagers[0] → EpisodeManagerSingleWall
│   └── agents[0] → TTLReceiverAgent
└── AgentGameObject (TTLReceiverAgent)

Flow:
1. FloorSpawner creates TargetAreas + MoveObject
2. DlcAgent (Player) moves via velocity+heading actions
3. Player pushes MoveObject into TargetArea
4. TargetKillOnArea destroys MoveObject
5. EpisodeManager detects TargetsAlive() == 0
6. Bridge calls TTLReceiverAgent.OnCorrect()
7. TTLReceiverAgent gets +1 reward
```

### Pattern 3: SequenceTarget + DlcAgent

```
Scene:
├── GridSpawner (GridTargetsSpawner)
├── Player (DlcAgent)
├── SequenceTargetManager
│   └── spawner → GridTargetsSpawner
├── EpisodeScore
├── MultiEpisodeToAgentBridge
│   ├── sequenceManagers[0] → SequenceTargetManager
│   └── agents[0] → TTLReceiverAgent
└── AgentGameObject (TTLReceiverAgent)

Flow:
1. GridSpawner creates N×N targets + walls
2. SequenceManager activates targets one at a time
3. DlcAgent navigates to active target, dwells
4. StatefulTarget fires OnCompleted, score increments
5. SequenceManager advances to next target
6. Repeat until sequence complete (success) or timeout (fail)
7. Bridge calls OnCorrect/OnIncorrect on TTLReceiverAgent
```

---


## Observation Space Details

### DlcAgent Observations

| Index | Name | Range | Description |
|-------|------|-------|-------------|
| 0 | world_x | ℝ | World position X coordinate (meters) |
| 1 | world_z | ℝ | World position Z coordinate (meters) |
| 2 | u | [0, 1] | Screen-space U coordinate (horizontal) |
| 3 | v | [0, 1] | Screen-space V coordinate (vertical) |
| 4 | heading | [-π, π] | Heading angle in radians (from +Z axis in x-z plane) |
| 5+ | camera | [0, 1] | Optional visual obs (84×84×1 or 84×84×3) |

### PlayerAgent3DOnScreen Observations

| Index | Name | Range | Description |
|-------|------|-------|-------------|
| 0 | u | [0, 1] | Screen-space U coordinate (horizontal) |
| 1 | v | [0, 1] | Screen-space V coordinate (vertical) |

### TouchFingerAgent Observations

| Index | Name | Range | Description |
|-------|------|-------|-------------|
| 0 | u | [0, 1] | Projection plane U coordinate |
| 1 | v | [0, 1] | Projection plane V coordinate |
| 2 | azimuth_sin | [-1, 1] | Sin of heading angle on plane |

### TTLReceiverAgent Observations

| Index | Name | Range | Description |
|-------|------|-------|-------------|
| 0 | patch_color | {0, 1} | Current TTL patch state |
| 1 | iti_flag | {0, 1} | In ITI (1) or not (0) |
| 2 | init_phase_flag | {0, 1} | In init phase (1) or not (0) |
| 3 | latency_ms | ℝ+ | Last Action->Render delay (milliseconds) |

---

## Action Space Details

### DlcAgent Actions

| Index | Name | Range | Description |
|-------|------|-------|-------------|
| 0 | x_norm | [-1, 1] | Target X position (mapped to U 0-1) |
| 1 | y_norm | [-1, 1] | Target Y position (mapped to V 0-1) |
| 2 | heading_deg | [0, 360] | Absolute heading in degrees (rotation around Y axis) |
| 3 | head_angle | ℝ | Reserved for future use |
| 4 | emit_action | ℝ | Integer action ID (triggers interact when == emitAction) |

**Action Processing:**
```csharp
// Map actions to UV coordinates
float u = 0.5f * (Mathf.Clamp(actions[0], -1f, 1f) + 1f);  // [-1,1] -> [0,1]
float v = 0.5f * (Mathf.Clamp(actions[1], -1f, 1f) + 1f);  // [-1,1] -> [0,1]

// Get heading from action
float headingDeg = Mathf.Repeat(actions[2], 360f);  // Wrap to [0, 360]
Quaternion rotation = Quaternion.Euler(0f, headingDeg, 0f);

// Clamp to keep object within bounds
if (clampFullyInside)
{
    float uPad = halfExtents.x / screenWidth;
    float vPad = halfExtents.y / screenHeight;
    u = Mathf.Clamp(u, uPad, 1f - uPad);
    v = Mathf.Clamp(v, vPad, 1f - vPad);
}

// Compute world target position on screen plane
Vector3 target = screen.BottomLeft
               + screen.Right * u * screenWidth
               + screen.Up * v * screenHeight
               + screen.Normal * faceOffset;

// Apply position and rotation
rigidbody.MovePosition(target);
rigidbody.MoveRotation(rotation);

// Check interaction
int action = (int)actions[4];
bool interact = (action == emitAction);
```

### TouchFingerAgent Actions

| Index | Name | Range | Description |
|-------|------|-------|-------------|
| 0 | y_ndc | [-1, 1] | Y position in normalized device coordinates |
| 1 | x_ndc | [-1, 1] | X position in normalized device coordinates |

### PlayerAgent3DOnScreen Actions

| Index | Name | Range | Description |
|-------|------|-------|-------------|
| 0 | x_norm | [-1, 1] | Target X position (normalized) |
| 1 | y_norm | [-1, 1] | Target Y position (normalized) |
| 2 | (unused) | - | Compatibility padding |
| 3 | (unused) | - | Compatibility padding |

**Action Processing:**
```csharp
float u = 0.5f * (Mathf.Clamp(actions[0], -1f, 1f) + 1f);  // Map [-1,1] to [0,1]
float v = 0.5f * (Mathf.Clamp(actions[1], -1f, 1f) + 1f);  // Map [-1,1] to [0,1]

// Clamp if needed
if (clampFullyInside)
{
    float uPad = halfExtents.x / screen.Width;
    float vPad = halfExtents.y / screen.Height;
    u = Mathf.Clamp(u, uPad, 1f - uPad);
    v = Mathf.Clamp(v, vPad, 1f - vPad);
}

// Compute world position on screen plane
Vector3 target = screen.BottomLeft
               + screen.DirRight * (u * screen.Width)
               + screen.DirUp * (v * screen.Height)
               + screen.DirNormal * faceOffset;

// Apply (teleport or smooth)
if (teleport)
    rigidbody.position = target;
else
    rigidbody.MovePosition(Vector3.Lerp(transform.position, target,
                                        1f - Mathf.Exp(-followLerp * Time.deltaTime)));
```

### TTLReceiverAgent Actions

| Index | Name | Range | Description |
|-------|------|-------|-------------|
| 0 | ttl_signal | [0, 1] | TTL output (>= 0.5 = ON/white, < 0.5 = OFF/black) |

---

## See Also

- **[Architecture Overview](Architecture.md)** - System design
- **[Episode Management](EpisodeManagement.md)** - Episode lifecycle
- **[Parameter System](ParameterSystem.md)** - Configuration
- **[Wrapper Documentation](https://github.com/SCENE-Collaboration/SCENE_MouseAR/blob/main/rl/WRAPPER_ARCHITECTURE.md)** - Python training wrappers
