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

The **Rules Scheduler** is an adaptive difficulty engine embedded inside `UnityMultibehaviorTask`. It automatically modifies Unity environment parameters (KV or float) as a session progresses, without requiring any manual intervention in the task loop.

### Concept

A *rule* is a declarative instruction of the form:

> "Every N **successes** / **episodes** / **epochs**, apply operation `op` with value `value` to parameter `target`, clamped to `[min, max]`."

Rules are loaded from the TOML config at startup and run silently in the background. After each episode the task calls scheduler hooks (`on_success`, `on_episode_end`, `on_epoch_advance`); the scheduler accumulates any resulting parameter changes and flushes them at the start of the next episode via `reset_episode()`.

---

### Defining rules in TOML

Rules are stored in two places:

1. **`rules_lib.*`** — a shared library of reusable rule templates (typically in `rules.lib.toml` which is imported by game configs).
2. **`[profile.<name>.rules] use = [...]`** — each profile selects which library rules are active for that session.

#### Rule fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `target` | `str` | ✓ | Parameter path. Use `unity.kv.<section>.<key>` for KV channel parameters or `unity.env.<section>.<key>` for float env parameters. |
| `op` | `str` | ✓ | Operation: `set`, `add`, `mul`, or `subtract`. String-valued targets only support `set`. |
| `value` | `float \| str \| list` | ✓ | Value to apply. A list cycles through its elements on consecutive triggers. |
| `every` | `str` | ✓ | Trigger cadence in the format `<unit>:<N>` where unit is `success`, `episode`, or `epoch` and N is the integer count. |
| `min` | `float` | — | Lower bound applied after the operation (numeric targets only). |
| `max` | `float` | — | Upper bound applied after the operation (numeric targets only). |
| `window` | `int` | — | Sliding window size for rate-based rules (reserved for future use). |

#### Minimal example

```toml
[rules_lib.ramp_distance]
target = "unity.kv.hockeyFloor.move_object_max_distance"
op     = "add"
value  = 0.04
every  = "success:1"   # trigger after every success
min    = 0.5
max    = 5.0
```

This adds 0.04 to `move_object_max_distance` after every successful trial, clamped between 0.5 and 5.0.

#### List-valued rule (step through fixed stages)

```toml
[rules_lib.stage_sequence]
target = "unity.kv.HockeyManager.spawner"
op     = "set"
value  = ["0", "1", "2"]   # cycles: 0 → 1 → 2 → 0 → ...
every  = "epoch:1"
```

Each time an epoch advances the spawner index is incremented cyclically through the list.

#### Selecting rules in a profile

```toml
[profile.trainingstage1.rules]
use = ["ramp_distance"]

[profile.trainingstage2.rules]
use = ["ramp_distance_middlesteps", "reduce_platform_sizex"]
```

Only the named rules are activated; all other `rules_lib` entries are ignored for that profile.

---

### How it works at runtime

```
                 ┌─────────────────────────────────┐
                 │       UnityMultibehaviorTask      │
                 │                                  │
  per episode    │  loop() detects terminal=True    │
  ─────────────► │  ep_reward > 0 → on_success()   │
                 │  on_episode_end()                │
                 │  (epoch boundary) on_epoch_advance() │
                 └──────────────┬──────────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │   LiveParamScheduler    │
                    │                         │
                    │  _maybe_apply(unit)      │
                    │   increment tick counter │
                    │   if tick % N == 0:      │
                    │     _apply_rule(r)       │
                    │     accumulate to        │
                    │     _pending_kv /        │
                    │     _pending_env         │
                    └────────────┬────────────┘
                                 │
                 ┌───────────────▼──────────────────┐
                 │  reset_episode()                  │
                 │  calls get_changes()              │
                 │  → _apply_scheduler_changes()     │
                 │    channel_kv.set(key, val)       │  ──► Unity KV channel
                 │    (env param update disabled)    │
                 │  logs to runtime_params[]         │
                 └──────────────────────────────────┘
```

Key points:
- **Changes are batched**: `_apply_rule()` writes immediately to the in-memory parameter dicts but changes are only sent to Unity when `get_changes()` is called at `reset_episode()`.
- **Only actual changes are sent**: the scheduler compares old and new values; if a rule produced no change (e.g. already at `max`) nothing is transmitted.
- **Changes are logged**: every scheduler-driven update is appended to `self.runtime_params` with a timestamp, episode number, and step, enabling post-hoc reconstruction of training history.
- **`window` counter** is per-rule so multiple rules with different cadences run independently.

---

### Supported target namespaces

| Target prefix | Channel | Value type | Example |
|---------------|---------|------------|---------|
| `unity.kv.<section>.<key>` | `KvChannel` (string) | `float` or `str` | `unity.kv.hockeyFloor.move_object_max_distance` |
| `unity.env.<section>.<key>` | `EnvironmentParametersChannel` (float) | `float` | `unity.env.general.episode_length` |
| `general.<key>` (shorthand) | `KvChannel` (string) | `float` | `general.render_virtual_mouse` |

> **Note**: env parameter changes via the scheduler are currently accumulated but not transmitted (the `channel.set_float_parameter` call is commented out in `_apply_scheduler_changes`). Only KV channel changes are actively applied at runtime.

---

### Full example: Hockey `trainingstage1`

```toml
# rules.lib.toml (imported)
[rules_lib.ramp_distance]
target = "unity.kv.hockeyFloor.move_object_max_distance"
op     = "add"
value  = 0.04
every  = "success:1"
min    = 0.5
max    = 5.0

# hockey.game.toml profile
[profile.trainingstage1.rules]
use = ["ramp_distance"]

[profile.trainingstage1.unity.kv.hockeyFloor]
move_object_max_distance = 1.0   # starting value
```

Session flow:
1. Session starts with `move_object_max_distance = 1.0`.
2. After the first successful trial → scheduler adds 0.04 → `1.04`.
3. After the 100th success → `1.0 + 100 × 0.04 = 5.0` (clamped at max).
4. All subsequent successes leave the value at `5.0`.

---

## Related docs

- [GUIs](GUIs.md) - Using profiles in UnityTaskGUI
- [Overview](Overview.md) - System architecture
- [Tasks](Tasks.md) - UnityAgentTask API
