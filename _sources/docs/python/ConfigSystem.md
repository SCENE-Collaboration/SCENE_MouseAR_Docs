# Configuration System - TOML Profiles

## Overview

The `mice_ar_tasks` configuration system uses TOML files plus profile-based overrides.
The examples below are based on values that are actually present in this repository, especially `mouse_ar/tasks/configs/hockey.game.toml` and its imports.

---

## Config files used by Hockey

`hockey.game.toml` imports these files:

```toml
[imports]
files = [
    "./teensy.hw.toml",
    "./dlc.hw.toml",
    "./game.config.toml",
    "./rl.config.toml",
    "./rules.lib.toml",
]
```

So the effective config is the deep merge of imported files, then `hockey.game.toml`, then optional profile overrides.

---

## Section names

The loader in `mouse_ar/ctrl/utils/config_loader.py` expects these sections:

- `[unity.kv.*]` → flattened to string KV pairs for `KvChannel`
- `[unity.env.*]` → flattened to float env params for `EnvironmentParametersChannel`
- `[game]` → python task settings
- `[teensy]`, `[dlc]`, `[touchscreen]` → hardware/input settings
- `[rules_lib.*]` and `[rules.use]` → adaptive rule templates and selected rules

> Note: the correct KV namespace is `unity.kv`, not `unity.env.kv`.

---

## Hockey base values

### Example from `hockey.game.toml`

```toml
[unity.env.general]
episode_length = 60
iti_length = 3
enable_init_phase = true

[unity.kv.HockeyManager]
spawner = 0
display_reward_flash = 1
reward_display_duration = 1.5
display_noise_overlay = 0
noise_display_duration = 0.2
enabled = true

[game]
use_photottl = true
use_touch = false
use_dlc = true
behavior_list = ["TTLInput", "DLCInput"]
```

### Imported base values used by Hockey

From `game.config.toml`:

```toml
[game]
env_path = "C:\\Users\\User\\Repos\\SCENE_MouseAR\\UnityAR\\Build\\MouseAR.exe"
monitor = "1"
reward_size = 100
use_perf_counter = true

[unity.env.general]
enable_reporting = 1
reporting_period = 1
randomize_iti_length = true
rotate_bottom_screen = true

[unity.kv.general]
render_virtual_mouse = false
```

From `dlc.hw.toml`:

```toml
[dlc]
dlc_address = ['localhost', 6000]
dlc_apply_filter_inprocessor = true
dlc_box_extents = [115, 28, 577, 500]
dlc_flip_y = true
dlc_flip_x = true
dlc_rotate_90 = true
```

From `teensy.hw.toml`:

```toml
[teensy]
dummy = false
serial_port = "COM3"
baudrate = 115200
csv_expected = 7
```

---

## Hockey profiles (actual names and values)

`hockey.game.toml` defines:

- `trainingstage1`
- `trainingstage2`
- and `RL` (from imported `rl.config.toml`)

### `trainingstage1`

```toml
[profile.trainingstage1.unity.kv.hockeyFloor]
object_min_distance_z = 0
spawn_target = 0
move_object_max_distance = 2.3
randomize_start_x = 1
move_object_scale = 2

[profile.trainingstage1.game]
reward_size = 150
max_session_duration = 40

[profile.trainingstage1.unity.env.general]
episode_length = 120

[profile.trainingstage1.rules]
use = ["ramp_distance"]
```

### `trainingstage2`

```toml
[profile.trainingstage2.unity.kv.hockeyFloor]
object_min_distance_z = 0
spawn_target = 0
move_object_max_distance = 4.5
randomize_start_x = 1
move_object_scale = 2

[profile.trainingstage2.game]
reward_size = 400
max_session_duration = 1

[profile.trainingstage2.unity.env.rewardAssociation]
size_x = 5
size_z = 5

[profile.trainingstage2.rules]
use = ["ramp_distance_middlesteps"]
```

### `RL` (from `rl.config.toml`)

```toml
[profile.RL.unity.env.general]
enable_reporting = 1
reporting_period = 0
episode_length = 40
iti_length = 0
randomize_iti_length = false

[profile.RL.unity.kv.general]
render_virtual_mouse = true

[profile.RL.teensy]
dummy = true

[profile.RL.game]
env_path = ""
use_touch = false
use_dlc = false
```

---

## How profile merge works

Merge order in `load_config()`:

1. Load file + recursively load imports
2. Deep-merge imported/base values
3. If `profile` is provided, deep-merge `profile.<name>` on top
4. Flatten:
   - `unity.kv.*` → `env_kv` (`dict[str, str]`)
   - `unity.env.*` → `env_params` (`dict[str, float]`)

Example (`hockey.game.toml`, profile `trainingstage1`):

- `unity.env.general.iti_length` stays `3` (base, not overridden)
- `unity.env.general.episode_length` becomes `120` (profile override)
- `unity.kv.hockeyFloor.spawn_target` becomes `"0"` in `env_kv`

---

## Loading configurations

### Programmatic loading

```python
from mouse_ar.ctrl.utils.config_loader import load_config, get_available_profiles

path = "mouse_ar/tasks/configs/hockey.game.toml"

profiles = get_available_profiles(path)
# e.g. ['RL', 'trainingstage1', 'trainingstage2']

env_kv, env_params, cfg = load_config(path)  # base
env_kv_s1, env_params_s1, cfg_s1 = load_config(path, profile="trainingstage1")
```


---

## Rules Scheduler (`LiveParamScheduler`)

The Rules Scheduler is a small rule engine used by `UnityMultibehaviorTask` to mutate runtime parameters between episodes. It operates on two in-memory dictionaries:

- `env_kv` for Unity KV-channel values (stored as strings)
- `env_params` for Unity environment parameter values (stored as floats)

Current integration detail: the scheduler can produce both KV and env changes, but `UnityMultibehaviorTask` currently only pushes KV changes back to Unity and only logs KV changes to `runtime_params`.

### Concept

A rule says:

> "On every `N`th `success`, `episode`, or `epoch`, update `target` using `op`."

The task does not run rules continuously inside an episode. Instead it calls scheduler hooks at episode/epoch boundaries:

- `on_success()` when a terminal episode ended with positive cumulative episode reward
- `on_episode_end()` on every terminal episode
- `on_epoch_advance()` when the task advances to the next epoch

The scheduler applies the rule immediately to its internal dictionaries, accumulates the resulting deltas in pending buffers, and those pending changes are consumed on the next `reset_episode()` through `get_changes()`.

---

### Where rules come from

Rules are typically defined in shared `rules_lib.*` entries and activated by profile selection:

```toml
[profile.trainingstage1.rules]
use = ["ramp_distance"]

[profile.trainingstage2.rules]
use = ["ramp_distance_middlesteps", "reduce_platform_sizex"]
```

By the time `LiveParamScheduler` is constructed, it receives the already-selected `rules_cfg` dictionary for the active session.

### Rule fields

| Field | Type | Required | Current behavior |
|-------|------|----------|------------------|
| `target` | `str` | ✓ except `scenario_choice` | Parameter path to read and write. See namespaces below. `scenario_choice` reads its targets from each scenario param instead. |
| `op` | `str` | ✓ | Supported ops: `set`, `add`, `mul`, `subtract`, `rand`, `random_choice`, `scenario_choice`. |
| `value` | `float \| str \| list` | For `set`/`add`/`mul`/`subtract` | Single value or list of values. Lists cycle on repeated triggers. String values are only valid with `set`. |
| `every` | `str` | ✓ | Format `<unit>:<N>`, where unit is currently `success`, `episode`, or `epoch`. |
| `active_from` | `str` | Optional | Activation lower bound in the same `<unit>:<count>` format. Rule is ignored until that counter reaches the given count. |
| `active_until` | `str` | Optional | Activation upper bound in the same `<unit>:<count>` format. Rule is ignored after that counter exceeds the given count. |
| `min` | `float` | Optional for arithmetic ops; required for `rand`/`random_choice` | Lower clamp for numeric results. |
| `max` | `float` | Optional for arithmetic ops; required for `rand`/`random_choice` | Upper clamp for numeric results. |
| `window` | `int` | — | Parsed and stored, but not currently used by rule evaluation. |
| `scenarios` | `list` | Required for `scenario_choice` | List of scenarios; each scenario is a list of param specs applied together. See [Scenario rules](#scenario-rules-scenario_choice). |

Notes:

- `rand` ignores `value` and samples `random.uniform(min, max)`.
- `random_choice` ignores `value` and currently chooses one of `[min, max]`.
- `scenario_choice` ignores `target`/`value`/`min`/`max` at the top level and instead applies a randomly chosen `scenarios` entry — see below.
- `active_from` and `active_until` are inclusive bounds against the scheduler's cumulative counters. They do not reset the rule's `every` cadence; they only gate whether a matching trigger is allowed to apply.
- Comments in some TOML files mention `trial:N`, but the current implementation only emits `success`, `episode`, and `epoch` ticks.

Example staged switch:

```toml
[rules_lib.random_large_goal_scenario]
op           = "scenario_choice"
every        = "episode:1"
active_until = "episode:15"

[rules_lib.random_large_goal_scenario3]
op          = "scenario_choice"
every       = "episode:1"
active_from = "episode:16"
```

### Supported target namespaces

| Target form | Backing store | Stored type | Notes |
|-------------|---------------|-------------|-------|
| `unity.kv.<section>.<key>` | `env_kv` | `str` | Numeric results are stringified before storage. |
| `unity.env.<section>.<key>` | `env_params` | `float` | Stored as float in the scheduler. |
| `general.<key>` | `env_kv` | `str` | Convenience shorthand for KV targets. |
| any other unprefixed key | `env_params` | `float` | Falls back to env-parameter storage. |

Examples:

- `unity.kv.hockeyFloor.move_object_max_distance`
- `unity.env.general.episode_length`
- `general.render_virtual_mouse`

### Scenario rules (`scenario_choice`)

The ops described so far each touch a single `target`. `scenario_choice` exists for the case where several parameters must change **together** to stay coherent — for example moving a goal and resizing the arena at the same time, where applying only one of the two would leave the environment in an invalid state.

A `scenario_choice` rule does not use the top-level `target`/`value`/`min`/`max` fields. Instead it carries a list of **scenarios**, and each scenario is a list of **param specs**. On each trigger the scheduler picks one scenario uniformly at random (`random.choice`) and applies *all* of its param specs in order.

Each param spec is a self-contained mini-rule with its own namespaced `target` and `op`:

| Param-spec field | Type | Required | Notes |
|------------------|------|----------|-------|
| `target` | `str` | ✓ | Same namespaces as a normal rule (`unity.kv.*`, `unity.env.*`, `general.*`, or unprefixed). |
| `op` | `str` | — | Defaults to `set`. Supports `set`, `add`, `mul`, `subtract`, `rand`, `random_choice`. Nested `scenario_choice` is not allowed. |
| `value` | `float \| str` | For non-`rand`/`random_choice` ops | Single value only — **lists are rejected**. String values require `op = "set"`. |
| `min` | `float` | Required for `rand`/`random_choice` | Also acts as the lower clamp for arithmetic ops. |
| `max` | `float` | Required for `rand`/`random_choice` | Also acts as the upper clamp for arithmetic ops. |

Validation happens when the rule is constructed (`_make_rule`), so a malformed scenario config fails fast with a clear `ValueError`:

- `scenarios` must be present and non-empty.
- Each scenario must be a table with a non-empty `params` list.
- Each param spec must be a table (dict) and must include a `target`.
- `rand`/`random_choice` param specs require both `min` and `max` with `max >= min`.
- Non-`rand` param specs require a non-list `value`; string values are only valid with `op = "set"`.

At trigger time, `_maybe_apply()` chooses a scenario, routes every param spec through the same apply/clamp path as ordinary rules, and records a pending change for each touched target whose value actually changed, so each produces its own pending KV or env change. The usual KV-vs-env integration caveat still applies: only KV changes are pushed back to Unity and logged.

### Runtime behavior

```
                 ┌────────────────────────────────────┐
                 │       UnityMultibehaviorTask       │
                 │                                    │
  terminal step  │  if ep_reward > 0: on_success()   │
  ─────────────► │  on_episode_end()                 │
                 │  maybe on_epoch_advance()         │
                 └───────────────┬────────────────────┘
                                 │
                    ┌────────────▼─────────────┐
                    │    LiveParamScheduler    │
                    │                          │
                    │  per matching rule:      │
                    │  - increment tick count  │
                    │  - if tick % N == 0      │
                    │    apply rule            │
                    │  - record changed keys   │
                    │    in pending buffers    │
                    └────────────┬─────────────┘
                                 │
                    ┌────────────▼─────────────┐
                    │     reset_episode()      │
                    │  changes = get_changes() │
                    │  apply KV changes only   │
                    │  log KV changes only     │
                    └──────────────────────────┘
```

Key points:

- `_apply_rule()` mutates the scheduler's internal parameter dictionaries immediately.
- `get_changes()` returns the pending delta as `{"kv": {...}, "env": {...}}` and then clears the pending buffers.
- If multiple triggers happen before `get_changes()` is called, the pending buffer keeps the latest value per key.
- No pending entry is produced when a rule leaves the target unchanged, for example when a clamped value is already at its bound.
- Per-rule cadence is tracked through an internal tick counter; `window` does not currently participate in scheduling.

### What the task layer currently applies

`UnityMultibehaviorTask._apply_scheduler_changes()` currently does this:

- Sends KV changes with `channel_kv.set(key, value)`
- Appends one `runtime_params` entry with `source = "scheduler"` and `kv.<key>` fields
- Does not send `env` changes to Unity because the `set_float_parameter(...)` branch is still disabled
- Does not log env changes to `runtime_params`

That means env-targeted rules are valid inside `LiveParamScheduler` and appear in `get_changes()["env"]`, but they do not yet affect the running Unity task through the current task integration.

### Examples

#### Increment a KV parameter after every success

```toml
[rules_lib.ramp_distance]
target = "unity.kv.hockeyFloor.move_object_max_distance"
op     = "add"
value  = 0.04
every  = "success:1"
min    = 0.5
max    = 5.0
```

If the starting value is `1.0`, successive rewarded terminal episodes produce `1.04`, `1.08`, `1.12`, and so on until the `max` clamp is reached.

#### Sample a fresh value from a range

```toml
[rules_lib.random_x_puck_position]
target = "unity.kv.hockeyFloor.move_object_x"
op     = "rand"
every  = "success:1"
min    = -5
max    = 5
```

On each successful episode, the scheduler samples a new uniform random value in `[-5, 5]` and stores it in the KV buffer.

#### Alternate among fixed states

```toml
[rules_lib.stage_sequence]
target = "unity.kv.HockeyManager.spawner"
op     = "set"
value  = ["0", "1", "2"]
every  = "epoch:1"
```

Each epoch advance writes the next list element, then wraps back to the start.

#### Apply a coordinated set of parameters (scenario)

```toml
[rules_lib.random_large_goal_scenario]
op    = "scenario_choice"
every = "success:1"

# Scenario 1: goal on the +z wall, puck z fixed, puck x randomised
[[rules_lib.random_large_goal_scenario.scenarios]]
[[rules_lib.random_large_goal_scenario.scenarios.params]]
target = "unity.kv.hockeyFloor.area_thickness_x"
value  = 14
[[rules_lib.random_large_goal_scenario.scenarios.params]]
target = "unity.kv.hockeyFloor.area_width_z"
value  = 3
[[rules_lib.random_large_goal_scenario.scenarios.params]]
target = "unity.kv.hockeyFloor.target_z"
value  = 7.5
[[rules_lib.random_large_goal_scenario.scenarios.params]]
target = "unity.kv.hockeyFloor.move_object_x"
op     = "rand"
min    = -5.5
max    = 5.5

# Scenario 2: goal on the +x wall (arena rotated), puck x fixed, puck z randomised
[[rules_lib.random_large_goal_scenario.scenarios]]
[[rules_lib.random_large_goal_scenario.scenarios.params]]
target = "unity.kv.hockeyFloor.area_thickness_x"
value  = 3
[[rules_lib.random_large_goal_scenario.scenarios.params]]
target = "unity.kv.hockeyFloor.area_width_z"
value  = 18
[[rules_lib.random_large_goal_scenario.scenarios.params]]
target = "unity.kv.hockeyFloor.target_x"
value  = 5.5
[[rules_lib.random_large_goal_scenario.scenarios.params]]
target = "unity.kv.hockeyFloor.move_object_z"
op     = "rand"
min    = -7
max    = 7
```

On each successful episode the scheduler picks one of the two scenarios at random and applies *all* of its params together, so the arena dimensions, goal position, and puck spawn stay mutually consistent. (Note that TOML arrays-of-tables make the nesting verbose: `[[...scenarios]]` opens a new scenario and each following `[[...scenarios.params]]` adds a param spec to it.)

Activate it through a profile like any other rule:

```toml
[profile.trainingstage4c.rules]
use = ["random_large_goal_scenario"]
```

---

## Related docs

- [GUIs](GUIs.md) - Using profiles in UnityTaskGUI
- [Overview](Overview.md) - System architecture
- [Tasks](Tasks.md) - UnityAgentTask API
