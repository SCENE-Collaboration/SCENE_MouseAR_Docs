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
| `PlayerContactFlag` | Collision detector added to the puck — exposes `IsContact` bool (true while DlcAgent is touching) |
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
              positions target + puck based on spawn_mode (0/1/2/3)
              spawns 1 TargetArea (isTrigger, tag=Target)
              spawns 1 puck (Rigidbody + kill components)
              → SendKv("hockey.target_positions", "x,z")

State = Running
  ├─ FixedUpdate: FloorTargetsSpawnerReporter
  │     → SendKv("hockey.object_position",
  │              "pos_x,pos_z,vel_x,vel_z")
  │     → SendKv("hockey.player_contact", "1"/"0")  ← edge-triggered only
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

**Spawn mode** — Controls how the target zone and puck are positioned each episode.

| Key suffix | Type | Effect |
|---|---|---|
| `spawn_mode` | int 0–3 | Positioning strategy (see below) |

- **Mode 0 — Random** (default): Target zone placed at `(target_x, random Z within z_min..z_max)`. If `randomize_target_x=1`, target X is also randomized within `x_min..x_max` instead of using `target_x`. Puck placed randomly (controlled by `randomize_start_x/z` flags), enforcing `min_separation` (2D XZ distance) from the target and, when a Player-tagged object is present, from the player as well. When `randomize_start_x=0` or `randomize_start_z=0`, the corresponding `move_object_x/z` value is used directly.
- **Mode 1 — Fixed**: Target placed at `(target_x, target_z)`, puck at `(move_object_x, move_object_z)`. Same parameters as Mode 0 but used as exact positions — `randomize_start_x/z` flags are ignored. Python has full control over placement for deterministic experiments.
- **Mode 2 — Player-aware**: Puck spawns at `player_spawn_distance` from the Player-tagged object (virtual mouse) at `player_spawn_angle` relative to the mouse-facing direction used by the current scene setup, or within a forward-facing `player_spawn_angle ± 100°` arc when `player_spawn_angle_random=1`. The puck position is then clamped into `x_min..x_max` and `z_min..z_max`. The target no longer mirrors to the opposite side of the player; it is sampled with the same random-placement rules as Mode 0 and must satisfy `min_separation` from the puck. Falls back to Mode 0 if no Player object is found.
- **Mode 3 — Distance-from-goal**: The goal (target zone) is placed at `(target_x, target_z)`, clamped so the zone stays fully inside the arena. The puck is then spawned at a **random location whose distance to the goal zone's nearest edge equals `goal_distance`** — distance is measured to the closest edge of the box, not its center, so the set of valid spawn points forms the goal outline expanded outward by `goal_distance` (a rounded rectangle). Only points that land inside `x_min..x_max` / `z_min..z_max` (minus a half-puck margin) are kept, and one is picked uniformly at random. If `goal_distance` is too large for any valid point to fit inside the arena, it is automatically reduced to the largest feasible distance (the farthest reachable arena corner), guaranteeing an in-bounds spawn.

Compared with the previous implementation (before march 2026), the current spawner no longer builds up to three Z-spaced goal walls or derives player-aware target placement by mirroring the goal across the mouse. The current behavior always spawns a single target area, uses a shared random target sampler, extends Mode 0 separation checks so randomized puck placement also avoids the player, and changes Mode 2 so the puck is the player-aware object while the goal is sampled independently under the usual random-goal rules. In the same refactor, player-aware angle randomization changed from full 360 degree sampling to a forward-facing 200 degree window, and the player-facing basis was flipped to match the virtual mouse orientation used in this project.

**Target zone position & dimensions**

| Key suffix | Type | Effect |
|---|---|---|
| `target_x` | float | Target world X (Mode 0: used when `randomize_target_x=0`; Mode 1: exact X) |
| `target_z` | float | Target world Z (Mode 1 only; Mode 0 randomizes Z) |
| `randomize_target_x` | bool | Randomize target X within `x_min..x_max` (Mode 0 only; default false) |
| `area_width_z` | float | Zone width along Z (m) |
| `area_thickness_x` | float | Zone trigger depth (m) |
| `area_center_y` | float | Zone height center (m) |
| `area_height_y` | float | Zone height (m) |

**Arena bounds**

| Key suffix | Type | Effect |
|---|---|---|
| `z_min` / `z_max` | float | Arena Z bounds (Mode 0 random range, Mode 2 clamping) |
| `x_min` / `x_max` | float | Arena X bounds (Mode 0 random range when `randomize_start_x=1`, Mode 2 clamping) |
| `min_separation` | float | Min XZ distance between target and puck at spawn |

**Puck spawn & physics**

| Key suffix | Type | Effect |
|---|---|---|
| `move_object_x` | float | Puck X position (Mode 0: default when `randomize_start_x=0`; Mode 1: exact) |
| `move_object_y` | float | Puck Y position (all modes) |
| `move_object_z` | float | Puck Z position (Mode 0: default when `randomize_start_z=0`; Mode 1: exact) |
| `randomize_start_z` | bool | Random Z spawn within `z_min..z_max` (Mode 0 only) |
| `randomize_start_x` | bool | Random X spawn within `x_min..x_max` (Mode 0 only) |
| `move_object_scale` | float | Puck scale (X and Z; Y fixed) |
| `move_object_mass` | float | Rigidbody mass (kg) |
| `move_object_drag` | float | Linear drag |
| `move_object_angular_drag` | float | Angular drag |
| `move_object_max_distance` | float | Travel limit (0 = disabled) |
| `spawn_target` | bool | Spawn goal zone (false = distance-only task) |

**Player-aware spawn (Mode 2)**

| Key suffix | Type | Effect |
|---|---|---|
| `player_spawn_distance` | float | Distance from Player to spawn puck |
| `player_spawn_angle` | float | Angle (deg) relative to Player's forward |
| `player_spawn_angle_random` | bool | Randomize angle within a forward-facing `player_spawn_angle ± 100°` arc |

The Player reference is resolved by `FindWithTag("Player")` at spawn time (the DLC-controlled virtual mouse avatar). Can also be set via Inspector (`playerTransform` field) for explicit wiring.

**Distance-from-goal spawn (Mode 3)**

| Key suffix | Type | Effect |
|---|---|---|
| `goal_distance` | float | Target distance from the puck to the goal zone's nearest edge. Automatically clamped down to the largest value that still fits inside the arena bounds |

The goal position is taken from `target_x` / `target_z` (clamped into bounds); the goal zone dimensions come from `area_thickness_x` / `area_width_z`. Distance is measured to the nearest *edge* of the goal box, so `goal_distance=0` would spawn the puck right against the goal.

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
| `hockey.target_positions` | `"x,z"` | Once at spawn — world XZ of the target area |
| `hockey.object_position` | `"pos_x,pos_z,vel_x,vel_z"` | Every `reportingPeriod` steps — puck XZ + velocity |
| `hockey.player_contact` | `"1"` or `"0"` | Edge-triggered: `"1"` when DlcAgent first touches puck, `"0"` when contact ends or puck is destroyed during contact |

`hockey.player_contact` is sent only on state changes (not every frame). If the puck is destroyed while contact is active, a final `"0"` is synthesised in the next `FixedUpdate` to ensure Python always sees a clean contact-end. Python receives the event via `UnityAgentTask._on_kv_events()` → `on_player_contact(contact: bool)`.

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
# Spawn mode: 0=random, 1=fixed, 2=player-aware, 3=distance-from-goal
spawn_mode             = 0

# Target zone position & dimensions
target_x               = -7       # world X (Mode 0 & 1)
target_z               = 0        # world Z (Mode 1 only; Mode 0 randomizes)
randomize_target_x     = 0        # Mode 0: randomize target X in x_min..x_max
area_thickness_x       = 2
area_width_z           = 2
area_center_y          = -0.099
area_height_y          = 0.1

# Arena bounds
z_min                  = -7
z_max                  = 7
x_min                  = -8       # X bounds for random spawn / clamping
x_max                  = 8

# Separation
min_separation         = 1.5      # min XZ distance between target and puck

# Puck position & physics
# Mode 0: default position (or random if randomize_start_x/z = 1)
# Mode 1: exact position (randomize flags ignored)
move_object_x          = 4
move_object_y          = -0.14
move_object_z          = 0
randomize_start_z      = 1        # Mode 0 only
randomize_start_x      = 0        # Mode 0 only
move_object_scale      = 1.0
move_object_mass       = 1
move_object_drag       = 10
move_object_angular_drag = 0.1
move_object_max_distance = 0      # 0 = disabled
spawn_target           = 1

# Player-aware spawn (Mode 2 only)
player_spawn_distance      = 3.0
player_spawn_angle         = 0    # degrees from player's forward
player_spawn_angle_random  = 1    # randomize angle

# Distance-from-goal spawn (Mode 3 only)
goal_distance              = 3.0  # puck distance to goal zone's nearest edge (auto-clamped to fit bounds)

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
random_seed     = -1               # -1 = choose a fresh Unity seed on each run; any other int is used as-is
reward_size     = 100              # water solenoid pulse duration (ms)

# Optional haptic / auditory feedback
vibration_on_interaction = false  # vibrate on every puck-contact start
use_tone_reward_cue      = false  # play 3 kHz tone alongside each reward
tone_duration            = 200    # tone duration (ms) when use_tone_reward_cue = true
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

### `trainingstage1` — large puck, no goal, automatic distance ramp

```toml
[profile.trainingstage1.unity.kv.hockeyFloor]
spawn_mode               = 0     # random within bounds
spawn_target             = 0     # no goal wall — puck destruction IS the success signal
move_object_max_distance = 0.5   # barely touch the puck (rules will increase this)
randomize_start_x        = true
randomize_start_z        = true
move_object_scale        = 2     # larger puck for easier early training

[profile.trainingstage1.unity.env.general]
episode_length = 60

[profile.trainingstage1.game]
reward_size          = 150
max_session_duration = 40  # minutes

[profile.trainingstage1.rules]
use = ["ramp_distance"]    # adds 0.04 to move_object_max_distance per success, range 0.5–5.0
```

Two variants of this stage also exist: `trainingstage1a` (Mode 2 player-aware, `player_spawn_distance = 5`) and `trainingstage1alt` (Mode 1 fixed with a large goal directly).

### `trainingstage2` — steeper distance ramp

```toml
[profile.trainingstage2.unity.kv.hockeyFloor]
spawn_mode               = 0
spawn_target             = 0
move_object_max_distance = 3
randomize_start_x        = 1
randomize_start_z        = 1

[profile.trainingstage2.game]
reward_size          = 150
max_session_duration = 45  # minutes

[profile.trainingstage2.rules]
use = ["ramp_distance_middlesteps"]  # adds 0.1 per success, range 3–15
```

Rule definitions live in [`rules.lib.toml`](../../mouse_ar/tasks/configs/rules.lib.toml) and are referenced by name in the `[profile.*.rules]` `use` list.

---

## Complete Python → Unity → Python Data Round-Trip

```
task.start()
  ──[env params]──► FloorTargetsSpawnerEnvParams
  ──[kv normal] ──► KvManagersDirector → FloorTargetsSpawner
  ──[kv enabled]──► EpisodeManagerSingleWall.StartEpisode()
                      └─► SpawnAll()
  ◄──[hockey.target_positions]──  (once per episode)

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

  ◄──[hockey.object_position]──  (every N physics steps)
  ◄──[hockey.player_contact]───  (edge-triggered: "1" on start, "0" on end)
         │
         └─► UnityAgentTask._on_kv_events()
               └─► on_player_contact(contact)
                     ├─ [vibration_on_interaction=True]
                     │    → task.give_vibration() ──[Teensy]──► vibration motor
                     └─ (override for custom reactions)

  puck → TargetArea:
    reward > 0 in step result
    task.give_reward() ──[Teensy]──► solenoid
      └─ [use_tone_reward_cue=True]
           → task.give_tone() ──[Teensy]──► speaker (3 kHz)

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
