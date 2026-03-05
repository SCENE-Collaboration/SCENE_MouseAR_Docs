# Parameter Control System

## Overview

The Unity game supports two independent parameter control mechanisms for runtime configuration:

1. **ML-Agents EnvironmentParameters** - Training-time configuration from Python
2. **KV Channel** - Real-time control via key-value side channel

Both systems allow external control without recompiling Unity, enabling flexible experimentation and training.

## System Comparison

| Feature | EnvironmentParameters | KV Channel |
|---------|----------------------|------------|
| **Source** | Python → ML-Agents Academy | Python → KvChannel → KvManagersDirector |
| **Timing** | Read at episode start | Real-time, immediate |
| **Scope** | Global (all managers share) | Namespaced (per-manager) |
| **API** | `envParams.GetWithDefault(key, default)` | `kv.send_string("key=value")` |
| **Batching** | Single dict at env creation | Individual messages |

---

## ML-Agents EnvironmentParameters

### Python Setup

```python
from mlagents_envs.environment_parameters import EnvironmentParametersChannel

# Create channel
env_channel = EnvironmentParametersChannel()

# Set parameters
env_channel.set_float_parameter("episode_length", 15.0)
env_channel.set_float_parameter("general.iti_length", 2.0)
env_channel.set_float_parameter("step_timeout_seconds", 8.0)

# Create environment with channel
env = UnityEnvironment(
    file_name="Build/game.exe",
    side_channels=[env_channel]
)
```

### Unity Access

```csharp
using Unity.MLAgents;

public class MyScript : MonoBehaviour
{
    IEnumerator Start()
    {
        // Wait for Academy initialization
        while (!Academy.IsInitialized)
            yield return null;

        // Read parameters
        var envp = Academy.Instance.EnvironmentParameters;
        float episodeLen = envp.GetWithDefault("episode_length", 10f);
        float itiLen = envp.GetWithDefault("general.iti_length", 2f);

        Debug.Log($"Episode length: {episodeLen}, ITI: {itiLen}");
    }
}
```

### Global Parameters

**Naming Convention:** `general.<property>`

| Key | Type | Purpose | Used By |
|-----|------|---------|---------|
| `general.iti_length` | float | ITI duration (seconds) | Both episode managers |
| `general.episode_length` | float | Episode timeout (SingleWall only) | EpisodeManagerSingleWall |
| `general.enable_init_phase` | float | Enable init phase (0/1) | EpisodeManagerSingleWall |
| `general.randomize_iti_length` | float | Randomize ITI ±25% (0/1) | Episode managers |
| `general.rotate_bottom_screen` | float | Rotate bottom-screen layout (0/1) | RotateBottomScreen |
| `general.enable_reporting` | float | Enable KV reporting (0/1) | Reporter components |
| `general.reporting_period` | float | Reporter update interval | Reporter components |

### Manager-Specific Parameters

#### EpisodeManagerSingleWall

Read at `StartEpisode()`:
```csharp
var envp = Academy.Instance.EnvironmentParameters;
episodeLength = envp.GetWithDefault("general.episode_length", episodeLength);
itiLength = envp.GetWithDefault("general.iti_length", itiLength);
enableInitPhase = envp.GetWithDefault("general.enable_init_phase", enableInitPhase ? 1f : 0f) > 0.5f;
randomizeItiLength = envp.GetWithDefault("general.randomize_iti_length", randomizeItiLength ? 1f : 0f) > 0.5f;
```

#### SequenceTargetManager

Read at `StartEpisode()`:
```csharp
var envp = Academy.Instance.EnvironmentParameters;
stepTimeoutSeconds = envp.GetWithDefault("step_timeout_seconds", stepTimeoutSeconds);
dwellTargetSeconds = envp.GetWithDefault("dwell_target_seconds", dwellTargetSeconds);
dwellWallSeconds = envp.GetWithDefault("dwell_wall_seconds", dwellWallSeconds);
wallGraceSeconds = envp.GetWithDefault("wall_grace_seconds", wallGraceSeconds);
itiSeconds = envp.GetWithDefault("general.iti_length", itiSeconds);
randomTargetLength = (int)envp.GetWithDefault("random_target_length", randomTargetLength);
targetNoRepeatsInRandom = envp.GetWithDefault("target_no_repeats", targetNoRepeatsInRandom ? 1f : 0f) > 0.5f;
```

### Spawner EnvParams Components

Each spawner type has an optional `*EnvParams` component that reads parameters at startup:

**Pattern:**
```csharp
public class SomeSpawnerEnvParams : MonoBehaviour
{
    public string prefix = "spawnerName";  // Namespace prefix
    public SomeSpawner _sp;                // Spawner reference

    IEnumerator Start()
    {
        // Wait for Academy
        while (!Academy.IsInitialized)
            yield return null;

        ApplyParams();
        TryRespawnOrClear();  // Apply immediately
    }

    void ApplyParams()
    {
        var envp = Academy.Instance.EnvironmentParameters;

        // Read with prefix
        _sp.someProperty = envp.GetWithDefault($"{prefix}.some_property", _sp.someProperty);
        _sp.anotherProperty = envp.GetWithDefault($"{prefix}.another_property", _sp.anotherProperty);
    }

    public void TryRespawnOrClear()
    {
        float enabled = Academy.Instance.EnvironmentParameters.GetWithDefault($"{prefix}.enabled", 1f);
        if (enabled > 0.5f)
        {
            _sp.ClearAll();
            _sp.SpawnAll();
        }
        else
        {
            _sp.ClearAll();
        }
    }
}
```

### Additional EnvParam-Driven Components

#### SimpleTargetSpawnerEnvParams

Controls init-target placement/shape/visibility for `SimpleTargetSpawner`.

| Key Pattern | Type | Purpose |
|-------------|------|---------|
| `<prefix>.enabled` | bool | Enable/disable |
| `<prefix>.position_x/y/z` | float | Target world position |
| `<prefix>.size_x/y/z` | float | Target scale |
| `<prefix>.visible` | bool | `BottomView` (1) vs `Invisible` (0) |
| `<prefix>.dwell_time` | float | Required dwell seconds |

#### CameraEnvConfig

Controls camera projection parameters from env params (prefix set by `configKey`).

| Key Pattern | Type | Purpose |
|-------------|------|---------|
| `<key>.is_ortho` | bool | Camera mode (0 perspective / 1 orthographic) |
| `<key>.ortho_size` | float | Orthographic size |
| `<key>.fov` | float | Perspective field of view |
| `<key>.near_clip` | float | Near clipping plane |
| `<key>.far_clip` | float | Far clipping plane |

---

## KV Channel (Key-Value Side Channel)

### Python Setup

```python
from mouse_ar.ctrl.utils.kv_channel import KvChannel

# Create channel
kv = KvChannel()

# Send messages
kv.send_string("wallL.enabled=1")
kv.send_string("wallL.episode_length=12")
kv.send_string("wallL.start=1")

# Create environment with channel
env = UnityEnvironment(
    file_name="Build/game.exe",
    side_channels=[kv]
)
```

### Unity: KvManagersDirector

**Purpose:** Central router for KV messages to episode managers and spawners

**Configuration:**
```csharp
public class KvManagersDirector : MonoBehaviour
{
    [Serializable]
    public class WallManaged
    {
        public string key = "wallL";  // Namespace
        public EpisodeManagerSingleWall manager;
    }

    [Serializable]
    public class SeqManaged
    {
        public string key = "seqA";   // Namespace
        public SequenceTargetManager manager;
    }

    [Header("Managed Single-Wall episodes")]
    public WallManaged[] walls;

    [Header("Managed SequenceTarget episodes")]
    public SeqManaged[] sequences;

    [Header("Managed spawners")]
    public FloorSpawnerManaged[] floorSpawners;
    public ScreenSpawnerManaged[] screenSpawners;
    public SideTargetsSpawnerManaged[] sideSpawners;
    public GridSpawnerManaged[] gridSpawners;
}
```

**Inspector Setup:**
```
KvManagersDirector:
├── walls[0]:
│   ├── key: "wallL"
│   └── manager: → EpisodeManagerSingleWall
├── walls[1]:
│   ├── key: "wallR"
│   └── manager: → EpisodeManagerSingleWall
├── sequences[0]:
│   ├── key: "seqA"
│   └── manager: → SequenceTargetManager
├── floorSpawners[0]:
│   ├── key: "hockeyFloor"
│   └── envParams: → FloorTargetsSpawnerEnvParams
└── screenSpawners[0]:
    ├── key: "touchDestroy"
    └── env: → ScreenSpawnerEnvParams
```

### Message Format

**Pattern:** `<namespace>.<property>=<value>`

**Examples:**
```
wallL.enabled=1
wallL.episode_length=12.5
wallL.spawner=0
wallL.start=1

seqA.target_sequence=-1
seqA.random_target_length=5
seqA.wall_sequence=ABC
seqA.start=1

hockeyFloor.num_target_areas=3
hockeyFloor.target_x=-8.0
```

### Supported Commands

#### EpisodeManagerSingleWall

| Key | Value Type | Effect |
|-----|-----------|--------|
| `<id>.enabled` | 0/1 | Enable/disable manager |
| `<id>.spawner` | int | Set active spawner index |
| `<id>.episode_length` | float | Episode duration |
| `<id>.iti_length` | float | ITI duration |
| `<id>.loop` | 0/1 | Auto-restart episodes |
| `<id>.display_reward_flash` | 0/1 | Green flash on success |
| `<id>.display_noise_overlay` | 0/1 | Noise on timeout |
| `<id>.reward_display_duration` | float | Flash duration |
| `<id>.noise_display_duration` | float | Noise duration |
| `<id>.start` | 1 | Start episode now |

#### SequenceTargetManager

| Key | Value Type | Effect |
|-----|-----------|--------|
| `<id>.enabled` | 0/1 | Enable/disable |
| `<id>.step_timeout_seconds` | float | Per-step timeout |
| `<id>.dwell_target_seconds` | float | Target dwell time |
| `<id>.dwell_wall_seconds` | float | Wall dwell time |
| `<id>.wall_grace_seconds` | float | Grace period |
| `<id>.enable_iti` | 0/1 | Enable ITI |
| `<id>.iti_seconds` | float | ITI duration |
| `<id>.target_sequence` | string | "1593", "-1" |
| `<id>.wall_sequence` | string | "ABC", "0", "-1" |
| `<id>.random_target_length` | int | Random length |
| `<id>.random_wall_length` | int | Random wall count |
| `<id>.target_no_repeats` | 0/1 | No-repeat random |
| `<id>.display_noise_timeout` | 0/1 | Noise on timeout |
| `<id>.display_reward_flash` | 0/1 | Flash on success |
| `<id>.start` | 1 | Start episode |

#### Spawner Parameters

See [Spawners.md](Spawners.md) for complete spawner parameter lists.

---

## KV Reporting (Unity → Python)

KvManagersDirector can send state information back to Python. We use this to flexibly send observations from different managers, depending on the experiment.

```csharp
[Header("Reporting")]
public bool enableReporting = true;

// Send KV message from Unity
public void SendKv(string key, string value)
{
    if (!enableReporting || _kv == null) return;
    _kv.Send(key, value);
}
```

**Python Receiving:**
```python
# KvChannel receives messages in message_received callback
def handle_kv(key, value):
    print(f"Unity sent: {key} = {value}")

kv.message_received += handle_kv
```

**Example Reporters:**
- `EpisodeManagerSingleWallReporter`
- `SequenceTargetManagerReporter`
- `FloorTargetsSpawnerReporter`

---


### Message Ordering

For KV, send configuration before `.start`:

```python
# Good: Configure, then start
kv.send_string("wallL.episode_length=15")
kv.send_string("wallL.spawner=1")
kv.send_string("wallL.start=1")  # Apply all

# Avoid: Start, then configure (too late)
kv.send_string("wallL.start=1")
kv.send_string("wallL.episode_length=15")  # Won't affect running episode
```

---

## See Also

- **[Architecture Overview](Architecture.md)** - System design
- **[Episode Management](EpisodeManagement.md)** - Manager configuration
- **[Spawner Reference](Spawners.md)** - Spawner parameters
