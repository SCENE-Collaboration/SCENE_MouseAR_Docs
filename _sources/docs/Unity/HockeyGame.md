# Hockey Game Documentation

## Overview

The Hockey Game is a floor-based navigation task in which the mouse (tracked via DLC) pushes a movable puck-like object along a 3D arena floor until it enters one or more vertical target areas ("goal walls"). A second ML-Agents behavior sends a photodiode-synchronisation TTL signal each frame. Both behaviors run inside a single Unity ML-Agents environment and are driven entirely from Python.

---

## Involved Unity Scripts

**Episode management**

| Script | Role |
|--------|------|
| `EpisodeManagerSingleWall` | State machine (Idle → Init → Running → ITI); owns timing and success/failure detection |
| `EpisodeManagerSingleWallReporter` | Sends KV telemetry (object positions) to Python while Running |

**Spawners**

| Script | Role |
|--------|------|
| `FloorTargetsSpawner` | Spawns the puck and vertical target areas at episode start |
| `FloorTargetsSpawnerAdapter` | Adapts `FloorTargetsSpawner` to the `IEpisodeSpawner` interface |
| `FloorTargetsSpawnerEnvParams` | Applies `unity.env.*` floats to `FloorTargetsSpawner` on env reset |
| `FloorTargetsSpawnerReporter` | Sends puck position/velocity KV messages to Python |
| `SimpleTargetSpawner` | Optional init-phase target the mouse must reach before the episode starts |

**Agents**

| Script | Role |
|--------|------|
| `DlcAgent` | Receives pose actions from Python; teleports virtual-mouse on the screen plane |
| `TTLReceiverAgent` | Receives TTL bit from Python; drives the photodiode sync patch |

**Utilities**

| Script | Role |
|--------|------|
| `KvManagersDirector` | Singleton KV router: Python → managers/spawners and Unity → Python |
| `KvChannel` | ML-Agents side channel for bidirectional string key-value transport |
| `TargetKillOnArea` | Destroys puck on `TargetArea` overlap → signals success |
| `TargetKillOnDistance` | Destroys puck after exceeding cumulative travel limit |
| `ContainmentInBoxVolume` | Clamps puck inside arena with elastic bounce |
| `ColorOverlay` | Full-screen color flash on success |
| `WhiteNoiseOverlayGPU` | Full-screen noise overlay on episode timeout |

---

## Component Relationships & How They Work Together

```
# --- Python side channels ---

UnityAgentTask
  ├─ EnvParamsChannel [unity.env.*]
  │     → FloorTargetsSpawnerEnvParams.OnEnvReset()
  │
  ├─ KvChannel [unity.kv.*]
  │     → KvManagersDirector
  │           ├─ HockeyManager.* → EpisodeManagerSingleWall
  │           └─ hockeyFloor.*   → FloorTargetsSpawnerEnvParams
  │
  ├─ DLCInput behavior
  │     actions [x, y, hdg, ha, act]
  │     → DlcAgent.OnActionReceived()
  │     ← DlcAgent.CollectObservations() [wx, wz, u, v, hdg]
  │
  └─ TTLInput behavior
        actions [ttl_bit]
        → TTLReceiverAgent.OnActionReceived()
        ← TTLReceiverAgent.CollectObservations() [brightness, iti]

# --- Unity episode loop ---

KvManagersDirector: HockeyManager.enabled=1
  └─► EpisodeManagerSingleWall.StartEpisode()
        reads: episode_length, iti_length,
               enable_init_phase, enable_reporting
        │
        ├─ [if enable_init_phase]
        │    SimpleTargetSpawner.SpawnAll()
        │    wait until init target destroyed
        │    → OnInitPhaseComplete
        │
        └─► FloorTargetsSpawner.SpawnAll()
              spawns ≥1 TargetArea (isTrigger, tag=Target)
              spawns 1 puck (Rigidbody + kill components)
              → SendKv("floor.target_positions", "x0,z0,...")

State = Running
  ├─ FixedUpdate: FloorTargetsSpawnerReporter
  │     → SendKv("floor.object_position",
  │              "pos_x,pos_z,vel_x,vel_z")
  │
  ├─ ContainmentInBoxVolume: clamp + bounce puck
  ├─ TargetKillOnDistance: destroy puck if travel > max
  │
  └─ puck.OnTriggerStay(TargetArea)
        TargetKillOnArea destroys puck
        TargetsAlive() == 0
        → OnAllTargetsCleared
        → [ColorOverlay if display_reward_flash]
        → EndEpisode() → State = ITI

State = ITI
  wait itiLength (±25% jitter)
  → StartEpisode()
```

---

## Episode Lifecycle in Detail

### 1. Session start

1. Python calls `task.start()` → Teensy starts, `UnityEnvironment` is opened.
2. `set_channel()` sends all `unity.env.*` floats via `EnvironmentParametersChannel` (episode length, ITI, init-phase flag, reporting toggle).
3. `set_channel()` sends all `unity.kv.*` strings in order: normal keys → `.start` keys → `.enabled` keys (the enabled key for `HockeyManager` comes last to ensure spawner config is applied before episode begins).
4. `KvManagersDirector` receives `HockeyManager.enabled=1`, calls `EpisodeManagerSingleWall.StartEpisode()`.

### 2. Episode start (`StartEpisode`)

- `EpisodeManagerSingleWall` reads current EnvironmentParameters (episode_length, iti_length, randomize_iti_length, enable_init_phase, enable_reporting).
- Calls `_active.ClearAll()` to remove any leftover objects from the previous episode.
- **Init phase** (if `enable_init_phase=true`): spawns a single init target; waits for the DLC-controlled marker to overlap it. Once cleared → `OnInitPhaseComplete` → proceeds to the running phase.
- **Running phase**: `_active.SpawnAll()` → `FloorTargetsSpawner.SpawnAll()` places TargetArea(s) and the puck. `FloorTargetsSpawnerReporter.OnSpawn()` immediately sends target positions to Python.

### 3. Running phase

- `EpisodeManagerSingleWall.TickRunning()` runs every Unity frame:
  - Checks `TargetsAlive()` (number of living `TargetArea` GameObjects in the spawner).
  - If 0: all targets cleared → success path → `OnAllTargetsCleared` → `EndEpisode()`.
  - If `Elapsed >= episodeLength`: timeout → `EndEpisode()` (with optional noise overlay).
- `FloorTargetsSpawnerReporter.FixedUpdate()` sends puck position + velocity to Python every `reportingPeriod` physics steps.
- `ContainmentInBoxVolume.FixedUpdate()` (on puck) keeps puck inside arena.
- `TargetKillOnDistance.Update()` (on puck) accumulates travel distance; destroys puck when `> moveObjectMaxDistance` (which also triggers TargetsAlive==0 → success on next frame tick).

### 4. Reward and ITI

- `EndEpisode()` clears all spawned objects, fires `OnEpisodeEnd`, enters ITI state.
- On the Python side: `ep_reward > 0` (reward was non-zero during the episode) → `task.give_reward(reward_size)` sends water-solenoid pulse to Teensy.
- After ITI elapses (possibly randomized), `StartEpisode()` is called again.

### 5. Session end

- Either `epoch` counter exceeds the epoch list, `max_session_duration` is exceeded, or the GUI stops the task.
- Python writes all data to `UnityData_<SubjectId>_<Timestamp>.json`.

---

## Data Flow: Python → Unity

### Channel 1: `EnvironmentParametersChannel` (`unity.env.*` floats)

Sent at `env.reset()`. Applied by `FloorTargetsSpawnerEnvParams.OnEnvReset()` and
read directly by `EpisodeManagerSingleWall.StartEpisode()`.

| Key | Consumed by | Effect |
|-----|------------|--------|
| `general.episode_length` | `EpisodeManagerSingleWall` | Max running duration (s) |
| `general.iti_length` | `EpisodeManagerSingleWall` | Base ITI duration (s) |
| `general.randomize_iti_length` | `EpisodeManagerSingleWall` | ±25% ITI jitter |
| `general.enable_init_phase` | `EpisodeManagerSingleWall` | Enable init target |
| `general.enable_reporting` | Reporter + EnvParams | Toggle KV reporting |
| `general.reporting_period` | `FloorTargetsSpawnerEnvParams` | Reporter interval (steps) |
| `rewardAssociation.position_x/y/z` | Init-phase spawner | Init zone position |
| `rewardAssociation.size_x/y/z` | Init-phase spawner | Init zone size |
| `rewardAssociation.dwell_time` | Init-phase spawner | Dwell before cleared (s) |

### Channel 2: `KvChannel` (`unity.kv.*` strings)

Sent at any time. Received by `KvManagersDirector` and routed by namespace prefix.

#### `HockeyManager.*` → `EpisodeManagerSingleWall`

| Key suffix | Type | Effect |
|---|---|---|
| `enabled` | bool | Start (1) or disable (0) the manager |
| `spawner` | int | Active spawner index (0 = FloorTargets) |
| `display_reward_flash` | bool | ColorOverlay on success |
| `reward_display_duration` | float | Flash duration (s) |
| `display_noise_overlay` | bool | Noise overlay on timeout |
| `noise_display_duration` | float | Noise duration (s) |
| `start` | bool | Trigger `StartEpisode()` immediately |

#### `hockeyFloor.*` → `FloorTargetsSpawnerEnvParams` (live during session)

These override `FloorTargetsSpawner` fields and optionally respawn immediately.

**Target zone layout**

| Key suffix | Type | Effect |
|---|---|---|
| `num_target_areas` | int 1–3 | Number of target zones |
| `target_x` | float | World X of the goal wall |
| `area_width_z` | float | Zone width along Z (m) |
| `area_thickness_x` | float | Zone trigger depth (m) |
| `area_center_y` | float | Zone height center (m) |
| `area_height_y` | float | Zone height (m) |
| `z_min` / `z_max` | float | Z placement band |
| `min_gap_z` | float | Min gap between zone centers |
| `jitter_z` | float | Random Z jitter on placement |
| `snap_z_to_integers` | bool | Snap zone Z to integer grid |

**Puck spawn & physics**

| Key suffix | Type | Effect |
|---|---|---|
| `move_object_x/y/z` | float | Default spawn position |
| `randomize_start_z` | bool | Random Z spawn (avoids targets) |
| `randomize_start_x` | bool | Random X spawn |
| `object_min_distance_z` | float | Min Z gap from target at spawn |
| `move_object_scale` | float | Puck scale (X and Z; Y fixed) |
| `move_object_mass` | float | Rigidbody mass (kg) |
| `move_object_drag` | float | Linear drag |
| `move_object_angular_drag` | float | Angular drag |
| `move_object_max_distance` | float | Travel limit (0 = disabled) |
| `spawn_target` | bool | Spawn goal zones (false = distance-only task) |

**Optional features**

| Key suffix | Type | Effect |
|---|---|---|
| `enable_distance_color` | bool | Colour puck by distance from camera |
| `enable_rotation_color` | bool | Colour puck by camera Y-rotation |
| `enable_move_by_action` | bool | Lock puck until agent releases it |
| `enable_jitter` | bool | Add random jitter force |
| `jitter_weighting_factor` | float | Jitter force magnitude |
| `jitter_frequency` | float | Jitter frequency (Hz) |
| `jitter_base_angle_deg` | float | Base angle for jitter direction |
| `start` | bool | Force respawn immediately |

#### `general.*` (global KV keys)

| Key | Effect |
|---|---|
| `general.render_virtual_mouse` | Show/hide DLC virtual-mouse GameObject (layer toggle) |

#### `TouchManager.enabled` / `SequenceManager.enabled`

Set to `false` in `hockey.game.toml` to disable non-hockey managers.

---

## Data Flow: Unity → Python

Unity sends data back to Python via the **same `KvChannel`** (bidirectional). Python buffers all incoming key-value pairs in `kv_messages_current` (per-step mirror dict) and `kv_messages` (timestamped list, saved to disk).

### Messages sent by `FloorTargetsSpawnerReporter`

| Key | Format | When |
|-----|--------|------|
| `floor.target_positions` | `"x0,z0[,x1,z1,...]"` | Once at spawn — world XZ of each TargetArea |
| `floor.object_position` | `"pos_x,pos_z,vel_x,vel_z"` | Every `reportingPeriod` steps — puck XZ + velocity |

### Observations from `DlcAgent.CollectObservations()`

Sent as per-step ML-Agents vector observation (part of the `DLCInput` behavior step result read by `task._get_step_result_for("DLCInput")`).

| Index | Value | Description |
|---|---|---|
| 0 | `world_x` | Virtual-mouse world X position |
| 1 | `world_z` | Virtual-mouse world Z position |
| 2 | `screen_u` | Screen-space U coordinate [0, 1] |
| 3 | `screen_v` | Screen-space V coordinate [0, 1] |
| 4 | `heading` | Body heading (radians, atan2(fwd.x, fwd.z)) |

### Observations from `TTLReceiverAgent.CollectObservations()`

| Index | Value | Description |
|---|---|---|
| 0 | `patch_blue` | Current photodiode patch brightness (0 or 1) |
| 1 | `iti_flag` | 1.0 if episode is in ITI, 0.0 otherwise |
| 2 | `init_flag` | 1.0 if episode is in Init phase, 0.0 otherwise |

### Rewards

| Behavior | Reward |
|----------|--------|
| `DLCInput` | Non-zero positive on puck entering TargetArea |
| `TTLInput` | Always 0 (not used as reward signal) |

Python detects `ep_reward > 0` (sum across the episode) → triggers `task.give_reward(reward_size)` → Teensy water solenoid pulse.

---

## Required Configuration Reference

The complete set of config keys required for a working Hockey session, cross-referenced with the scripts that consume them.

### `[unity.env.general]` (via EnvironmentParametersChannel)

```toml
[unity.env.general]
episode_length       = 60       # → EpisodeManagerSingleWall.episodeLength
iti_length           = 3        # → EpisodeManagerSingleWall.itiLength
enable_init_phase    = true     # → EpisodeManagerSingleWall.enableInitPhase
enable_reporting     = 1        # → EpisodeManagerSingleWallReporter + FloorTargetsSpawnerEnvParams
reporting_period     = 1        # → FloorTargetsSpawnerEnvParams.reportingPeriod
randomize_iti_length = true     # → EpisodeManagerSingleWall.randomizeItiLength
```

### `[unity.env.rewardAssociation]` (optional, init-phase zone)

```toml
[unity.env.rewardAssociation]
position_x = 0
position_y = 0
position_z = 0
size_x     = 4    # width of init target zone (X)
size_y     = 0.1  # height (thin slab on floor)
size_z     = 4    # depth of init target zone (Z)
dwell_time = 0.1  # seconds mouse must remain in zone
```

### `[unity.kv.HockeyManager]` (controls EpisodeManagerSingleWall)

```toml
[unity.kv.HockeyManager]
spawner                 = 0     # 0 = FloorTargetsSpawnerAdapter
display_reward_flash    = 1
reward_display_duration = 1.5
display_noise_overlay   = 0
noise_display_duration  = 0.2
enabled                 = true  # sent last → starts the first episode
```

### `[unity.kv.hockeyFloor]` (controls FloorTargetsSpawner)

```toml
[unity.kv.hockeyFloor]
# Target zone layout
num_target_areas       = 1
target_x               = -7
area_thickness_x       = 2
area_width_z           = 2
area_center_y          = -0.099
area_height_y          = 0.1
z_min                  = -7
z_max                  = 7
min_gap_z              = 1
jitter_z               = 10
snap_z_to_integers     = 1

# Puck
move_object_scale      = 1.0
move_object_mass       = 1
move_object_drag       = 10
move_object_angular_drag = 0.1
move_object_x          = 4
move_object_y          = -0.14
randomize_start_z      = 1
randomize_start_x      = 0
move_object_max_distance = 0   # 0 = disabled
spawn_target           = 1

# Optional features
enable_distance_color  = 0
enable_jitter          = 0
enable_move_by_action  = 0
```

### `[game]` (Python task configuration)

```toml
[game]
use_photottl    = true             # enable TTLGenerator → TTLInput behavior
use_dlc         = true             # enable DLCClient → DLCInput behavior
use_touch       = false
behavior_list   = ["TTLInput", "DLCInput"]
reward_size     = 100              # water solenoid pulse duration (ms)
```

### Disabled managers (must be turned off)

```toml
[unity.kv.TouchManager]
enabled = false    # disables the TouchGame manager

[unity.kv.SequenceManager]
enabled = false    # disables the Sequence manager
```

---

## Training Profiles

Profiles override the base configuration for staged training. See [ConfigSystem.md](../python/ConfigSystem.md) for how profiles and rule schedulers work.

### `trainingstage1` — large puck, short task, automatic distance ramp

```toml
[profile.trainingstage1.unity.kv.hockeyFloor]
move_object_max_distance = 2.3   # starting max travel (rules will increase this)
randomize_start_x        = 1
move_object_scale        = 2     # larger puck for easier early training
spawn_target             = 0     # no goal wall — puck destruction IS the success signal

[profile.trainingstage1.unity.env.general]
episode_length = 120

[profile.trainingstage1.game]
reward_size          = 150
max_session_duration = 40  # minutes

[profile.trainingstage1.rules]
use = ["ramp_distance"]    # adds 0.04 to move_object_max_distance per success, capped at 5.0
```

### `trainingstage2` — harder init zone, steeper ramp

```toml
[profile.trainingstage2.unity.kv.hockeyFloor]
move_object_max_distance = 4.5
randomize_start_x        = 1
move_object_scale        = 2
spawn_target             = 0

[profile.trainingstage2.unity.env.rewardAssociation]
size_x = 5
size_z = 5

[profile.trainingstage2.game]
reward_size          = 400
max_session_duration = 1

[profile.trainingstage2.rules]
use = ["ramp_distance_middlesteps"]  # adds 0.1 per success, capped at 15.0
```

---

## Complete Python → Unity → Python Data Round-Trip

```
task.start()
  ──[env params]──► FloorTargetsSpawnerEnvParams
  ──[kv normal] ──► KvManagersDirector → FloorTargetsSpawner
  ──[kv enabled]──► EpisodeManagerSingleWall.StartEpisode()
                      └─► SpawnAll()
  ◄──[floor.target_positions]──  (once per episode)

loop():
  DLCInput actions [x,y,hdg,ha,act]
    ──────────────► DlcAgent.OnActionReceived()
  ◄──────────────  DlcAgent.CollectObservations()
                   [wx, wz, u, v, hdg]

  TTLInput actions [ttl_bit]
    ──────────────► TTLReceiverAgent.OnActionReceived()
  ◄──────────────  TTLReceiverAgent.CollectObservations()
                   [brightness, iti]

  env.step()

  ◄──[floor.object_position]──  (every N physics steps)

  puck → TargetArea:
    reward > 0 in step result
    task.give_reward() ──[Teensy]──► solenoid

  saved: kv_messages, state_vec, reward_vec,
         runtime_params, ...
```

---

## See Also

- [Episode Management System](EpisodeManagement.md) — `EpisodeManagerSingleWall` state machine and event system
- [Spawners Reference](Spawners.md) — `FloorTargetsSpawner` configuration in full detail
- [Parameter System](ParameterSystem.md) — KvChannel and EnvironmentParameters internals
- [Python Tasks](../python/Tasks.md) — `UnityAgentTask` and behavior routing
- [Config System](../python/ConfigSystem.md) — TOML profiles and Rules Scheduler
