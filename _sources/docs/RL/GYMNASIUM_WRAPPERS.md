# RL and Replay: User Guide

`rl/` wraps the MouseAR Unity tasks as [Gymnasium](https://gymnasium.farama.org/)
environments. It serves three uses:

1. **[Training RL agents](#1-training-rl-agents)** on the tasks, live or starting from recorded
   trials.
2. **[Replaying recorded sessions](#2-replaying-recorded-sessions)** exactly as they happened,
   to watch them or to save videos.
3. **[What-if replays](#3-what-if-replays)**: replaying a recorded trial with changed
   parameters (drag, push gain, band, ...) to see how the outcome would have differed.

All three run the same Unity player and the same wrappers, so an observation or an action means
the same thing whether an agent is training or a recording is being replayed.

The rest of the page is reference: [parallel environments](#many-environments-in-parallel),
[how replay sets up a trial](#how-replay-sets-up-a-trial),
[writing a wrapper](#writing-a-wrapper), [tests](#tests).

```
rl/
├── __init__.py        public API: from rl import HockeyWrapper, ...
├── base.py            BaseGymUnityWrapper: Unity task, config/session params, episode loop
├── touchdestroy.py    TouchDestroyWrapper   (TouchInput: [x, y] position)
├── dlc.py             DlcAgentWrapper       (DLCInput: [velocity, turn], pose, camera frames)
├── hockey.py          HockeyWrapper, HockeyObsLayout, goalfree_hockey_kwargs
├── sequence.py        SequenceWrapper
├── session.py         SessionData / TrialData: recorded sessions (file or DataJoint)
├── replay.py          ReplayMixin: the replay engine (replay / free / hybrid, what-if overrides)
├── hockey_replay.py   HockeyReplayWrapper   = ReplayMixin + HockeyWrapper
├── sequence_replay.py SequenceReplayWrapper = ReplayMixin + SequenceWrapper
├── video.py           play_trial, visual_replay_kwargs
├── vec.py             create_vec_env, reset_to_trials, bootstrap_cross_trial
└── example_train_hockey_rl.py   PPO / SAC training script
```

---

## Setup

### Python

```bash
uv sync --extra rl --extra dev      # or: pip install -e ".[rl,dev]"
pip install "imageio[ffmpeg]"       # only for saving replay videos
```

`rl` is a package: import with `from rl import ...`, and run its scripts from the repository
root as `python -m rl.<script>`.

### Unity player

Every environment starts its own Unity player (`MouseAR.x86_64` on Linux, `MouseAR.exe` on
Windows). Tell the wrappers where it is, either per environment with `env_path=...`
(`--env-path` for the training script), or once in `mouse_ar/tasks/configs/rl.config.toml`:

```toml
[profile.RL.game]
env_path = "/path/to/MouseAR.x86_64"
```

Build the player from the `UnityAR/` project of the same commit as the Python code: in the
Unity Editor, *File → Build Settings*, a standalone Linux or Windows target with
`Assets/Scenes/SampleScene`. A
[prebuilt player](https://drive.google.com/file/d/14okev4_VVTtz3-klMsoXTNLX4Jjxiy7G/view?usp=sharing)
exists, but it can be older than the code. Goal-free hockey, multi-puck trials and exact replay
need Unity code that older players do not have, and a player that is too old fails in ways that
are hard to see (for example, pucks spawning at random positions in a replay).

To play a task yourself, set `dlc_address = "dummy_pygame"` in
`mouse_ar/tasks/configs/dlc.hw.toml`, run `python mouse_ar/gui/unity_task_gui.py`, load
`hockey.game.toml` and steer the mouse in the pygame window.

### Recorded sessions

Replays read a recorded session from one of:

- a session file written by the task (`UnityData_<subject>_<date>_<time>.json` or `.npz`);
- the DataJoint database, by `dataset_id` (for example `"Tick_20260210_105633"`).

Loading from the database needs a working DataJoint connection. The schema tag and credentials
come from `dj_pipeline/.env` and `dj_pipeline/datajoint.json`, see
[Connections](../datajoint/Connections.md) and [Infrastructure](../datajoint/Infrastructure.md).
DataJoint looks for `datajoint.json` from the working directory upwards, so run from
`dj_pipeline/` with that environment loaded. Without the tag the schema name resolves to an
empty schema and the session is "not found". Session files need none of this.

### Tasks

| Task | Live wrapper | Replay wrapper | Config |
|---|---|---|---|
| Hockey (goal) | `HockeyWrapper` | `HockeyReplayWrapper` | `hockey.game.toml` |
| Hockey, goal-free (displacement band, 1–2 pucks) | `HockeyWrapper` | `HockeyReplayWrapper` | `hockey_goalfree.game.toml` |
| Sequence | `SequenceWrapper` | `SequenceReplayWrapper` | `sequence.game.toml` |
| TouchDestroy | `TouchDestroyWrapper` | – | `touchdestroy.game.toml` |

`rl.CONFIG_DIR` is the repository's config directory. Hockey and the sequence task are played by
the DLC agent and share their controls: the action is `[velocity, turn]`, both in [-1, 1]. The
wrapper turns the agent's *observed* heading by `turn × max_turn_rate` (π/4 per step by
default) and moves it `velocity × velocity_scale` screen units along the new heading. Because
the action is applied to the observed pose, an agent can take over a replayed trial at any step.

---

## 1. Training RL agents

> The training infrastructure works end to end: parallel Unity instances, training, saving,
> loading and evaluating a model. Whether an agent actually *learns* a task has not been worked
> on yet: the example script's reward and hyperparameters are placeholders.

### With the example script

```bash
# Live hockey from the game config, 4 Unity instances in parallel
python -m rl.example_train_hockey_rl --mode train --headless --num-envs 4 \
    --no-init-phase --timesteps 200000 --model runs/hockey_ppo

# Goal-free hockey: a profile of hockey_goalfree.game.toml (bandstage1, taskB, ...)
python -m rl.example_train_hockey_rl --mode train --headless --num-envs 4 \
    --goal-free taskB --no-init-phase --model runs/taskb_ppo

# In the conditions of recorded trials; the agent takes over after 200 recorded steps
python -m rl.example_train_hockey_rl --mode train --headless --num-envs 4 \
    --replay-data data/UnityData_Tick_20260210_105633.json \
    --replay-mode hybrid --handover-step 200 --model runs/replay_ppo

# Evaluate a saved model, or watch it play in a Unity window
python -m rl.example_train_hockey_rl --mode evaluate --headless --no-init-phase \
    --model runs/hockey_ppo --episodes 20
python -m rl.example_train_hockey_rl --mode visualize --no-init-phase --model runs/hockey_ppo

# Sanity check of an environment without any training
python -m rl.example_train_hockey_rl --mode random --headless --no-init-phase --episodes 3
```

| Option | Meaning |
|---|---|
| `--no-init-phase` | Spawn the pucks at the episode start. Without it the task waits for the agent to dwell in the initiation zone first, which an untrained agent practically never does, so no pucks appear. |
| `--num-envs N` | N Unity instances in parallel (training only). |
| `--goal-free PROFILE` | Goal-free hockey; sets config, profile and observation layout. |
| `--config`, `--profile` | Game config and profile(s); stack profiles with `+`, e.g. `taskB+RL`. |
| `--max-pucks`, `--max-targets`, `--obs-features` | Observation layout, see below. |
| `--replay-data`, `--replay-mode`, `--handover-step` | Train in the conditions of recorded trials. |
| `--algorithm ppo\|sac` | Stable-Baselines3 algorithm. |

Checkpoints are written to `./checkpoints/` in the working directory. `evaluate` and
`visualize` build their environment from the same options as `train`, so pass the same ones
(`--goal-free`, `--no-init-phase`, the layout flags): a model only fits the observation layout
it was trained on.

### In your own code

Every live wrapper takes a game config, applies its `RL` profile on top, and starts Unity on
port `base_port + worker_id` (headless unless `render_mode="human"`). Keyword arguments are
explicit: a misspelled one raises.

```python
from stable_baselines3 import PPO
from rl import CONFIG_DIR, HockeyWrapper, create_vec_env

BUILD = "/path/to/MouseAR.x86_64"
CONFIG = str(CONFIG_DIR / "hockey.game.toml")

# One environment
env = HockeyWrapper(config_path=CONFIG, env_path=BUILD, init_phase=False, max_episode_steps=1000)
obs, info = env.reset()
obs, reward, terminated, truncated, info = env.step(env.action_space.sample())
env.close()

# Several in parallel (Stable-Baselines3 SubprocVecEnv; one Unity instance and port each)
vec_env = create_vec_env(
    HockeyWrapper, num_envs=4, config_path=CONFIG, env_path=BUILD, init_phase=False
)
model = PPO("MlpPolicy", vec_env, verbose=1)
model.learn(total_timesteps=200_000)
model.save("runs/hockey_ppo")
vec_env.close()
```

Goal-free hockey (`hockey_goalfree.game.toml`: displacement band, no goal; Task B has two
texture-cued pucks) takes its config, profiles and observation layout from the profile:

```python
from rl import HockeyWrapper, goalfree_hockey_kwargs

env = HockeyWrapper(**goalfree_hockey_kwargs("taskB"), env_path=BUILD, init_phase=False)
print(env.obs_slices)     # name -> slice of the observation vector
```

`goalfree_hockey_kwargs` stacks the profile with `RL` and sizes the observation from it
(`max_pucks = n_move_objects`, `max_targets = 0`, presence / displacement / band, plus cue when
the profile enables it). The sequence task works the same way with `SequenceWrapper` and
`sequence.game.toml`.

Common arguments: `max_episode_steps` (truncation), `step_penalty` (reward on steps without
reward), `init_phase` (`False` spawns at the episode start instead of after the self-initiation
dwell), `config_profile` (profile(s) of the config), `env_path`, `time_scale`,
`capture_frame_rate`, `worker_id` / `base_port`, and `env_params_overrides` /
`env_kv_params_overrides` merged over the loaded parameters.

### Observations, reward and info

`HockeyWrapper`'s observation is a flat vector laid out by `HockeyObsLayout`;
`env.obs_slices` names every part.

| Part | Size | Content |
|---|---|---|
| `agent` | 5 | `[pos_x, pos_z, screen_u, screen_v, heading]` |
| `puck{i}` | 4 each | `[x, z, vx, vz]`, for `i < max_pucks` (default 1) |
| `puck{i}_present` | 1 | with `"presence"`: the puck was reported since the spawn |
| `puck{i}_displacement` | 2 | with `"displacement"`: `[dx, dz]` from its spawn position |
| `puck{i}_cue` | 5 | with `"cue"`: one-hot texture pattern |
| `target{j}` | 2 each | goal `[x, z]`, for `j < max_targets` (default 1, 0 for goal-free) |
| `target{j}_present` | 1 | with `"presence"` |
| `band` | 2 | with `"band"`: `[band_min, band_max]` |

The optional parts are switched on with `obs_features=("presence", "displacement", ...)`. The
defaults give the 11-value `[agent, puck0, target0]`. Values are clipped to the space
(positions ±10, velocities ±20). Puck and goal reports arrive only on some steps; the last
values are held until the next report, spawn or reset, and what was never reported is zero.
Task C's size cue is not in the vector observation.

`SequenceWrapper` observes the agent plus the current target index. `TouchDestroyWrapper(
config_path, max_objects=10)` takes `[x, y]` in [-1, 1] (a touch position) and observes the
object positions `[x1, y1, ...]` in [0, 1], zero-padded to `max_objects`.

`create_mouseview_obs=True` adds mouse-view camera frames: the observation becomes a dict with
`"vector"` and `"camera"` (plus `"camera_left"` / `"camera_right"`, and `"camera"` as their
side-by-side frame, with `mouse_obs_kwargs={"camera_multi": 1}`, which needs a build with the
binocular sensors). **Camera frames need a rendering player:** a headless one
(`render_mode=None`, `--headless`) has no renderer and its frames are a uniform grey.
`create_vec_env` renders only its first environment, so camera observations are not usable for
parallel training yet.

The reward is the task's own: +1 when the trial is solved, otherwise `-step_penalty` per step.
An episode *terminates* when the task ends the trial and is *truncated* at `max_episode_steps`.
`info["trial"]` carries what Unity reported about the trial this episode (`n_pucks`,
`puck_cue`, `puck_gain`, `puck_band`, `puck_roles`, and at the end `trial_outcome` such as
`band_hit` / `overshoot` / `timeout`, and `final_displacement`).

---

## 2. Replaying recorded sessions

A replay resets Unity into a recorded trial's conditions and sends the animal's recorded actions
step by step. It needs no game config: Unity is set up from the session's own parameters.

### Watch a trial or save a video

```python
from rl import HockeyReplayWrapper, play_trial, visual_replay_kwargs

env = HockeyReplayWrapper(
    trial_data_path="data/UnityData_Tick_20260210_105633.json",   # or dataset_id="Tick_20260210_105633"
    env_path="/path/to/MouseAR.x86_64",
    **visual_replay_kwargs(camera_index=0, camera_width=256, camera_height=256),
)
result = play_trial(env, trial_id=25, save_video="outputs/trial_25.mp4", video_fps=200)
print(result)        # trial_id, steps, total_reward, terminated, truncated, video_path
env.close()
```

`visual_replay_kwargs(camera_index=0 | 1, camera_multi, camera_width, camera_height,
camera_grayscale, time_scale, capture_frame_rate)` gives the wrapper arguments for watching:
the Unity window, the virtual mouse, a camera observation (`0` = bird's eye, `1` = the mouse's
view), `"replay"` mode, starting at the recorded spawn. `play_trial` then runs one trial to the
end of its episode. One recorded step is one physics step (5 ms), so `video_fps=200` plays in
real time.

The Unity window (`render_mode="human"`) is required for video: a headless player has no
renderer, and the saved video would be a uniform grey. Replays that only read the vector
observation and `info` work headless.

### Step through a replay yourself

```python
import numpy as np
from rl import HockeyReplayWrapper

env = HockeyReplayWrapper(
    trial_data_path="data/UnityData_Tick_20260210_105633.json",
    env_path="/path/to/MouseAR.x86_64",
    replay_mode="replay",      # send the recorded actions; the passed action is ignored
    max_episode_steps=40000,
)
print(env.session.num_trials, env.session.trial_ids[:5])

obs, info = env.reset(options={"trial_id": 25})   # omit trial_id for a random trial
while True:
    obs, reward, terminated, truncated, info = env.step(np.zeros(2, dtype=np.float32))
    if terminated or truncated:
        break
print(info.get("trial", {}).get("trial_outcome"), info.get("trial_replay_complete"))
env.close()
```

A replay ends when the task ends the trial (`terminated`) or when the recorded actions run out
(`truncated`, with `info["trial_replay_complete"]`). For goal-free or two-puck sessions pass the
matching layout, e.g. `max_pucks=2, max_targets=0, obs_features=("presence", "displacement",
"band")`. `SequenceReplayWrapper` replays sequence sessions with the same arguments.

A replay wrapper is the live wrapper with `ReplayMixin` in front, so spaces, observations and
the action conversion are the same as in training. `replay_mode` decides what reaches Unity
(`info["action_source"]` says which):

| `replay_mode` | Sent to Unity |
|---|---|
| `"replay"` | The recorded action every step (the passed one is ignored). |
| `"hybrid"` | Recorded actions for `handover_step` steps after the replay start, then the passed action. |
| `"free"` | The passed action from the start (the trial only sets the conditions). |

`replay_start_mode` is `"first_non_iti"` (default) or `"initiation_end"` (the recorded spawn).
`reset(options=...)` can set `replay_start_mode` and `handover_step` for one episode, and
`action_trial_id` to replay another trial's actions in this trial's conditions.
`set_replay_mode(mode)` switches modes.

### Loading sessions directly

```python
from rl import SessionData

session = SessionData.load_from_file("UnityData_Tick_20260210_105633.json")  # or .npz
session = SessionData.load_from_dj("Tick_20260210_105633")                    # DataJoint
session.trial_ids, session.get_trial(5), session.runtime_params
```

Pass a loaded session to several wrappers with `session_data=session` to load it once.
`min_trial_length` (default 5) drops shorter trials; a replay wrapper refuses a session that
has none left. A `TrialData` holds equal-length per-step arrays — `observations` (DlcAgent
pose), `actions` (recorded DlcAgent actions), `rewards`, `iti` (1 = inter-trial interval) —
plus the trial's `kv_messages` (key → list of value tuples), `kv_steps` (the game step of each
of those values) and `metadata` (`start_step`, `initiation_end_step`, `start_idx`,
`pre_start_observation`, ...).
Both loaders cut trials the same way: `TrialInfo` rows (DataJoint) or the same trial extraction
(files), mapped to array indices through the recorded game steps.

From DataJoint (`dj_pipeline.schemas.mousear_behavior`) it reads `UnitySession.params`,
`UnitySession.UnityData` (episode, step, reward), `UnitySession.UnityAgentBehavior` (DLCInput
state/action, TTLInput state; `state[:, 1]` is the ITI flag), `UnitySession.UnityMessage` (KV
messages), `UnitySession.UnityRuntimeParams` and `TrialInfo`.

### How exact is a replay?

Unity's physics is deterministic for a fixed frame schedule: a headless replay runs at
`capture_frame_rate=60` unless you pass another, and replaying the same trial twice on one
machine then gives identical results. The frame schedule matters because the player rewrites
interpolated bodies on every rendered frame and checks the end of a trial once per frame. With
the Unity window (`render_mode="human"`) the replay runs in real time instead, and the same trial
can come out differently from run to run: a contact one physics step earlier or later, the trial
ending a few steps apart, occasionally another outcome. Pass `capture_frame_rate` there too when
you need it to repeat.

Whether a replay matches the *original recording* depends on the recording:

- **Sessions recorded with a current player** (one that logs `hockey.spawn_positions`) replay
  exactly: every puck position matches the recording at full float precision for the whole
  trial, with the same outcome (verified on Linux on 26 trials, including Task B).
- **Older sessions** replay the agent's path, the spawn positions (to the logged 3 decimals),
  gains, roles and cues, but the pucks drift from the recording after the first contacts. Most
  trials still end with the same outcome, not all.

Not reproduced exactly: a session's first trial, and recordings from another platform (the
Windows rig replayed on Linux is untested). A recording made in real time also carries the frame
timing of its own run, which a replay does not know. The reasons are in
[How replay sets up a trial](#how-replay-sets-up-a-trial).

---

## 3. What-if replays

A what-if replay sends the animal's recorded actions into a trial whose parameters you changed:
*what would this push have done with twice the drag?* The parameters are Unity KV keys, the same
names as in the game configs (`[unity.kv.hockeyFloor]` → `hockeyFloor.<name>`).

```python
import numpy as np
from rl import HockeyReplayWrapper

env = HockeyReplayWrapper(
    trial_data_path="data/UnityData_<session>.json",       # or dataset_id=...
    env_path="/path/to/MouseAR.x86_64",
    replay_mode="replay",
    max_pucks=2, max_targets=0, obs_features=("presence", "displacement", "band"),
    max_episode_steps=40000,
)

def play(trial_id, kv_overrides=None):
    obs, info = env.reset(options={"trial_id": trial_id, "kv_overrides": kv_overrides or {}})
    steps = 0
    while True:
        obs, reward, terminated, truncated, info = env.step(np.zeros(2, dtype=np.float32))
        steps += 1
        if terminated or truncated:
            trial = info.get("trial", {})
            return trial.get("trial_outcome"), trial.get("final_displacement"), steps

baseline = play(2)                                               # the recorded parameters
more_drag = play(2, {"hockeyFloor.move_object_drag": 84})
equal_gains = play(2, {"hockeyFloor.puck_gains": "1.0,1.0"})
higher_band = play(2, {"hockeyFloor.band_min": 8})
env.close()
```

**Setting the parameters.** `kv_overrides` can be given per trial in `reset(options=...)`, as
above, or once in the constructor (`HockeyReplayWrapper(..., kv_overrides={...})`) for every
trial; the two are merged and the option wins. They are sent last, after the session's
parameters, the parameter changes recorded during the session and the trial's own setup, so
they always win. `info["kv_overrides"]` at reset reports what was applied, and `info["trial"]`
shows what Unity reports back (`puck_gain`, `puck_band`, ...), which is the check that a
parameter arrived. Keys that drive the replay itself (`*.start`, `*.enabled`,
`*.begin_running`, `*.external_running_start`) are refused.

`play_trial(env, trial_id, kv_overrides={...}, save_video=...)` records a video of a what-if
replay. Float *env* parameters (`[unity.env.*]`, e.g. `general.interaction_time_limit`) are not
KV keys: set them at construction with `env_params_overrides={...}`.

**Reading the result.**

- **Compare with the baseline replay, not with the recording.** Headless replays on one machine
  are deterministic, so any difference between the baseline replay and a what-if replay is caused
  by the parameter. Comparing with the recording mixes in whatever the replay did not reproduce
  (see [How exact is a replay?](#how-exact-is-a-replay)).
- **The animal does not react.** It repeats its recorded movements whatever the puck now does.
  The replay answers "what would these movements have done", not "what would the animal have
  done". The further the puck departs from the recorded path, the less the later pushes mean:
  the animal is pushing at where the puck used to be. The first contacts are the most
  informative part.
- **The replay stops with the recording.** If a changed parameter delays the outcome beyond the
  recorded trial, the episode is truncated without an outcome.

For the same question with an agent that does react, use `replay_mode="hybrid"`: recorded
actions up to `handover_step`, then a trained policy.

---

## Reference

### Many environments in parallel

```python
from rl import HockeyReplayWrapper, SessionData, create_vec_env, reset_to_trials
from rl.vec import bootstrap_cross_trial

session = SessionData.load_from_dj("Tick_20260210_105633")  # load once for all envs
vec_env = create_vec_env(HockeyReplayWrapper, num_envs=8, session_data=session)

obs = reset_to_trials(vec_env, [0, 1, 2, 3])  # the others reset to random trials
results = bootstrap_cross_trial(vec_env, session, num_bootstraps_per_trial=20)
vec_env.close()
```

`create_vec_env` works for any wrapper, live or replay. `reset_to_trials` sets each
environment's next-reset options (`VecEnv.set_options`); SB3's automatic resets afterwards pick
random trials. `bootstrap_cross_trial` replays every trial with the actions of randomly chosen
other trials and classifies each play as `rewarded`, `terminated`, `ended` (source actions ran
out) or `truncated`.

### How replay sets up a trial

Unity is reset to the session-start parameters before every trial. On top the replay sends, in
order:

1. **The parameter changes recorded up to the trial** (`SessionData.runtime_params`):
   rules-scheduler changes of this or earlier episodes, GUI changes made before the spawn;
   `.start` / `.enabled` keys excluded.
2. **The trial's spawn** at the recorded puck and goal positions (every puck's with
   `puck_positions` on builds that support it).
3. **The puck setup Unity applied** (`hockey_replay.puck_setup`): `n_move_objects`, gains, cue
   patterns, roles, band. Puck scale is not reported, so Task C's size cue is only reproduced
   through 1.
4. **`kv_overrides`**, if any (what-if replays).

A replay that starts after the first non-ITI step (`"initiation_end"`) is set up at the first
non-ITI step and pre-rolled through the recorded actions, so Unity reaches the spawn the way the
session did.

Puck contacts amplify any difference, so matching the recording needs everything up to the
first contact to be identical:

- *Spawn positions*: `hockey.spawn_positions` carries each puck's requested position (the
  reported transform is a float ulp off it; older recordings fall back to the first
  `object_position`, which is reported after a physics step and with three decimals). An
  episode can hold a spawn at the default settings before the trial's own; pucks, goal and
  puck setup are all taken from the last spawn.
- *Spawn timing*: live, the spawn runs in `Update()` on frame timers. Replay sets
  `HockeyManager.external_running_start=1` and sends `HockeyManager.begin_running=1` in the
  step of the recorded spawn, where a live spawn lands too.
- *Agent timeline*: the agent is placed at the pose one step before the replay start
  (`pre_start_observation` for index 0) and the first recorded action is replayed.

Not covered: a session's first trial (no pose before it; the session may start with an extra
default spawn), and recordings from another platform. The Python rules scheduler is unseeded,
but its drawn values are replayed from the telemetry.

### Writing a wrapper

Subclass `BaseGymUnityWrapper` (or `DlcAgentWrapper` for a DLCInput task) and implement
`_setup_action_space`, `_setup_observation_space`, `_transform_action` (RL action → Unity
action) and `_extract_observation`; optionally `_get_init_action` (sent on reset) and
`_get_info`. Set attributes the spaces depend on before calling `super().__init__()`, which
builds the spaces. Read this step's KV messages from `self.task.kv_messages_current`.

A replay wrapper for a DLCInput task is `class MyReplayWrapper(ReplayMixin, MyWrapper)`
implementing `_trial_conditions(trial, start_mode)` (the task's conditions, parsed from the
trial's KV messages) and `_trial_kv_updates(conditions, include_start=...)` (the KV messages
that put Unity into them).

### Tests

`tests/rl/` runs without Unity: wrappers take an already built `task` (a `MockTask`) instead of
starting one.

```bash
uv run --extra dev --extra rl pytest tests/rl/
```

The Unity-backed replay tests (`tests/rl/test_hockey_replay_integration.py`) run when
`SCENE_UNITY_ENV_PATH` points to a build; see the repository README. The test that compares a
session file with its DataJoint copy also needs the database connection described under
[Recorded sessions](#recorded-sessions).
