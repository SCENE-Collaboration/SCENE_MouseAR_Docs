# Gymnasium Wrappers for Unity ML-Agents

## Overview

The RL training system provides **Gymnasium-compatible wrappers** for Unity ML-Agents environments. The architecture uses inheritance-based design where each game type has its own specialized wrapper that handles game-specific action transformation and observation extraction.

## Architecture

```
BaseGymUnityWrapper (abstract base class)
│
├── Common Functionality:
│   ├── Unity task initialization & lifecycle
│   ├── Config loading from TOML files
│   ├── Render mode handling (headless vs graphics)
│   ├── Episode tracking & info dict construction
│   └── Multi-behavior action distribution
│
├── TouchDestroyWrapper
│   ├── Game: Touch objects on screen to destroy them
│   ├── Action: [x, y] direct position control
│   ├── Observation: Object positions from KV channel
│   └── Behavior: TouchInput (position teleportation)
│
├── HockeyWrapper
│   ├── Game: Navigate to intercept moving objects
│   ├── Action: [velocity, heading_change] velocity control
│   ├── Observation: Agent state + object state + targets
│   └── Behavior: DLCInput (velocity + heading)
│
└── [Your custom wrapper]
    └── Implement: _setup_action_space(), _extract_observation(), etc.
```

---

## Quick Start

### Using Factory Functions

```python
from rl.gym_wrappers import create_hockey_env, create_touchdestroy_env

# Hockey game with sensible defaults
env = create_hockey_env(
    render_mode="human",
    max_episode_steps=1000,
    step_penalty=0.1
)

# TouchDestroy game
env = create_touchdestroy_env(
    max_objects=10,
    render_mode=None,  # headless for training
    step_penalty=0.001
)

# Standard Gymnasium API
obs, info = env.reset()
for _ in range(100):
    action = env.action_space.sample()
    obs, reward, terminated, truncated, info = env.step(action)
    if terminated or truncated:
        obs, info = env.reset()
env.close()
```

### Training with Stable-Baselines3

```python
from stable_baselines3 import PPO
from rl.gym_wrappers import create_hockey_env

# Create environment
env = create_hockey_env(render_mode=None)

# Train PPO agent
model = PPO("MlpPolicy", env, verbose=1)
model.learn(total_timesteps=100_000)
model.save("hockey_ppo")

# Test trained agent
env = create_hockey_env(render_mode="human")
obs, info = env.reset()
for _ in range(1000):
    action, _states = model.predict(obs, deterministic=True)
    obs, reward, terminated, truncated, info = env.step(action)
    if terminated or truncated:
        break
env.close()
```

---

## Wrapper Reference

### TouchDestroyWrapper

**Purpose:** Touch-based game where agent destroys objects by moving to their positions.

**Action Space:** `Box(low=-1, high=1, shape=(2,))`
- `action[0]`: X position in normalized device coordinates [-1, 1]
- `action[1]`: Y position in normalized device coordinates [-1, 1]

**Observation Space:** `Box(low=0, high=1, shape=(max_objects*2,))`
- Flat array of object positions: `[x1, y1, x2, y2, ..., xN, yN]`
- Zero-padded if fewer than `max_objects` exist
- Positions in screen coordinates [0, 1]

**Unity Integration:**
- **Trainable Behavior:** `TouchInput` (TouchFingerAgent or PlayerAgent3DOnScreen)
- **Reward Behavior:** `TTLInput` (TTLReceiverAgent)
- **KV Channel:** Reads `touchScreen.object_positions` for object tracking

**Parameters:**
```python
TouchDestroyWrapper(
    config_path="mouse_ar/tasks/configs/touchdestroy.game.toml",
    max_objects=10,           # Maximum objects to track
    render_mode=None,          # "human" or None
    max_episode_steps=1000,    # Truncation limit
    step_penalty=0.0,          # Per-step penalty (e.g., -0.01)
)
```

**Example:**
```python
from rl.gym_wrappers import create_touchdestroy_env

env = create_touchdestroy_env(max_objects=12, render_mode="human")
obs, info = env.reset()

# obs = [x1, y1, x2, y2, ..., x12, y12]  # 24-dimensional
# Move to first object
action = obs[0:2] * 2 - 1  # Convert [0,1] to [-1,1]
obs, reward, terminated, truncated, info = env.step(action)
```

---

### HockeyWrapper

**Purpose:** Navigation game where agent uses velocity control to intercept moving objects and reach targets.

**Action Space:** `Box(low=[-1, -π/4], high=[1, π/4], shape=(2,))`
- `action[0]`: **Velocity** - forward/backward speed in [-1, 1]
  - Positive: move forward along heading direction
  - Negative: move backward
  - Scaled by `velocity_scale` (default: 0.1) per step

- `action[1]`: **Heading change** - angular velocity in radians [-π/4, π/4]
  - Positive: turn right (clockwise)
  - Negative: turn left (counterclockwise)
  - Maximum turn rate: ±45° per step

**Observation Space:** `Box(shape=(5+4+max_objects*2,))`

Structure:
```python
# Agent state (5D) - from DlcAgent.CollectObservations()
obs[0:5] = [
    pos_x,      # Agent X position in world space (meters)
    pos_z,      # Agent Z position in world space (meters)
    screen_u,   # Screen U coordinate [0, 1]
    screen_v,   # Screen V coordinate [0, 1]
    heading     # Heading angle in radians [-π, π]
]

# Moving object state (4D) - from KV 'hockey.object_position'
obs[5:9] = [
    obj_pos_x,  # Object X position (meters)
    obj_pos_z,  # Object Z position (meters)
    obj_vel_x,  # Object X velocity (m/s)
    obj_vel_z   # Object Z velocity (m/s)
]

# Target positions (max_objects*2) - from KV 'hockey.target_positions'
obs[9:] = [
    tgt1_x, tgt1_z,
    tgt2_x, tgt2_z,
    ...
]
```

**Unity Integration:**
- **Trainable Behavior:** `DLCInput` (DlcAgent)
- **Reward Behavior:** `TTLInput` (TTLReceiverAgent)
- **KV Channels:**
  - `hockey.object_position`: Moving object state (updated every step)
  - `hockey.target_positions`: Target locations (sent once per episode)

**Internal State:**
- Tracks `_agent_heading` (accumulated heading angle)
- Caches `_cached_target_positions` (persists across episode)

**Parameters:**
```python
HockeyWrapper(
    config_path="mouse_ar/tasks/configs/hockey.game.toml",
    max_objects=1,             # Number of targets to track
    render_mode=None,          # "human" or None
    max_episode_steps=1000,    # Truncation limit
    step_penalty=0.0001,       # Per-step penalty (time cost)
    velocity_scale=0.1,        # Velocity → position scaling
)
```

**Action Processing:**
```python
# Wrapper converts [velocity, heading_change] to Unity format:
velocity, heading_change = action

# Update heading
self._agent_heading += heading_change  # Integrate angular velocity
self._agent_heading = normalize(self._agent_heading)  # Keep in [-π, π]

# Get current position from observations
u, v = obs[2], obs[3]  # Screen coordinates [0, 1]
current_x = u * 2 - 1  # Convert to [-1, 1]
current_y = v * 2 - 1

# Calculate position change
dx = velocity * sin(heading) * velocity_scale
dy = velocity * cos(heading) * velocity_scale

# New position
new_x = clip(current_x + dx, -1, 1)
new_y = clip(current_y + dy, -1, 1)

# Convert to Unity format: [x, y, heading_deg, head_angle, emit_action]
unity_action = [new_x, new_y, heading_deg, 0, 0]
```

## BaseGymUnityWrapper API

### Abstract Methods (Must Implement)

```python
class MyGameWrapper(BaseGymUnityWrapper):

    @abstractmethod
    def _setup_action_space(self) -> spaces.Space:
        """Define action space for trainable behavior."""
        return spaces.Box(low=-1, high=1, shape=(2,))

    @abstractmethod
    def _setup_observation_space(self) -> spaces.Space:
        """Define observation space structure."""
        return spaces.Box(low=0, high=1, shape=(10,))

    @abstractmethod
    def _transform_action(self, action: np.ndarray) -> np.ndarray:
        """Convert RL action to Unity format."""
        # Your transformation logic
        return unity_action

    @abstractmethod
    def _extract_observation(self) -> np.ndarray:
        """Extract observation from Unity task."""
        # Read from self.task.behaviors and self.task.channel_kv
        return obs_array
```

### Optional Methods (Can Override)

```python
def _get_init_action(self) -> Optional[np.ndarray]:
    """
    Return initialization action sent at episode start.

    Default: None (no initialization)
    Override to implement custom episode setup.
    """
    return None

def _get_info(self) -> dict:
    """
    Build info dictionary returned from step().

    Default: Episode stats + KV messages
    Override to add custom info.
    """
    info = super()._get_info()
    info["my_metric"] = self._compute_metric()
    return info

def reset(self, seed=None, options=None):
    """
    Reset environment.

    Override to add custom reset logic.
    Remember to call super().reset()!
    """
    # Clear your state
    self._my_state = None

    # Call parent reset
    return super().reset(seed=seed, options=options)
```

### Provided Methods (Use As-Is)

| Method | Purpose |
|--------|---------|
| `__init__()` | Initialize Unity task, load config, setup spaces |
| `step(action)` | Execute action, get reward/obs/done |
| `reset(seed, options)` | Reset environment to initial state |
| `close()` | Cleanup and shutdown Unity |
| `render()` | Handled automatically by Unity window |
| `_send_init_action()` | Send initialization action at reset |

### Accessing Unity Data

```python
# Inside your wrapper methods (_extract_observation, etc.):

# --- ML-Agents observations ---
behavior_name = self.trainable_behavior
obs = self.task.behaviors[behavior_name]["state"].get("obs")
if obs is not None:
    agent_obs = obs[0]  # First agent's observations

# --- KV channel messages ---
kv_dict = dict(self.task.channel_kv.messages)
if "my_key" in kv_dict:
    value_str = kv_dict["my_key"]  # String value
    parsed = [float(v) for v in value_str.split(",")]

# --- Reward and done ---
reward = self.task.behaviors[self.reward_response_behavior]["reward"]
done = self.task.behaviors[self.reward_response_behavior]["done"]

# --- Episode tracking ---
episode_num = self.task.episode
step_num = self.task.step
```

---

## Configuration

### Unity Config Requirements

Your `.game.toml` must specify behaviors:

```toml
[game]
behavior_list = ["MyBehavior", "TTLInput"]

[unity.kv.MyReporter]
kvPrefix = "mygame"
enableReporting = 1
updateInterval = 0.1
```

### Python Wrapper Config

```python
env = MyGameWrapper(
    config_path="path/to/config.toml",  # Required
    render_mode="human",                # "human" or None
    max_episode_steps=1000,             # Truncation limit
    step_penalty=0.01,                  # Per-step cost
    # ... custom parameters
)
```

---

## Performance

### Headless Training
```python
env = create_hockey_env(render_mode=None)  # no_graphics=True
```

### Vectorized Environments
```python
from stable_baselines3.common.vec_env import SubprocVecEnv

def make_env(i):
    def _init():
        return create_hockey_env(
            render_mode=None,
            worker_id=i,  # Different Unity port
        )
    return _init

# Train on 4 parallel environments
envs = SubprocVecEnv([make_env(i) for i in range(4)])
model = PPO("MlpPolicy", envs)
model.learn(total_timesteps=400_000)
```

---

## Summary

| Wrapper | Game | Action Space | Observation Space | Behavior |
|---------|------|--------------|-------------------|----------|
| TouchDestroyWrapper | Touch objects | [x, y] position | Object positions | TouchInput |
| HockeyWrapper | Navigate & intercept | [vel, heading_Δ] | Agent + object + targets | DLCInput |
| BaseGymUnityWrapper | (abstract) | Define in subclass | Define in subclass | Configurable |

---

## See Also

- **[Agents Documentation](../Unity/Agents.md)** - Unity agent implementations
- **[Unity Agent Task](../../mouse_ar/tasks/unity_agent_task.py)** - Task interface
- **[Training Examples](../../rl/train_touchdestroy_rl.py)** - Example training scripts
