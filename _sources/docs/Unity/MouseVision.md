# Mouse Visual Observations

## Overview

The mouse vision system lets `DlcAgent` send camera frames to Python as ML-Agents visual observations. Two complementary pieces work together:

- **`MouseEyeImageEffect`** — a post-process image effect (Built-in RP) attached to the egocentric eye cameras that warps the rendered image to approximate mouse visual perception.
- **`DlcAgent` camera sensor** — creates a `CameraSensorComponent` at runtime (controlled via `MouseVisuals.*` env params) so the selected camera's frames are included in the agent's observation.

---

## Visual Simulation Pipeline (`MouseEyeImageEffect`)

The effect runs four optional stages in order each frame. Every stage can be disabled independently.

### 1. Dichromatic filter (`applyDichromatic`)

Zeros the red channel. Mice have M-cones (~511 nm) and S-cones (~360 nm UV, proxied by blue) but no L-cones, so they cannot distinguish reds from greens of equal luminance.

### 2. Scotopic rod response (`applyScotopic`)

Models the rod-dominant retina (~97 % rods):

| Sub-step | Description |
|----------|-------------|
| Scotopic luminance | Weights channels toward rod peak (~507 nm, blue-green). |
| High gain | Multiplies luminance by `lowLightGain` (default 3×) to simulate large photon catch and single-photon sensitivity. |
| Naka-Rushton compression | `L / (L + sigma)` saturation curve (`rodSigma` default 0.35) matching rod phototransduction. |
| Achromatic tint | Blends toward a faint blue-green tint (507 nm peak) controlled by `scotopicTint` (default 0.35). |

### 3. Gaussian blur (`blurPasses`, `blurSize`)

Each pass runs a separable H + V Gaussian kernel. Mouse spatial acuity is ~0.5 cyc/deg vs ~60 cyc/deg for humans, so 2 passes at `blurSize = 2.5` texels is the default. Set `blurPasses = 0` to disable.

### 4. Circular visual field mask (`applyCircularMask`)

Masks the output to a circle (each eye's visual field is roughly circular). Edge softness is controlled by `circleEdge` (default 0.08). Disabled by default.

### Inspector parameters

| Field | Default | Description |
|-------|---------|-------------|
| `applyDichromatic` | `true` | Zero red channel |
| `applyScotopic` | `true` | Rod gain + compression + tint |
| `lowLightGain` | 3.0 | Linear luminance multiplier |
| `rodSigma` | 0.35 | Naka-Rushton half-saturation |
| `scotopicTint` | 0.35 | Blend toward 507 nm blue-green |
| `blurSize` | 2.5 | Texels per blur pass |
| `blurPasses` | 2 | H+V iterations (0 = no blur) |
| `applyCircularMask` | `false` | Circular field vignette |
| `circleEdge` | 0.08 | Edge softness (0 = hard) |

---

## Enabling Visual Observations

All visual observation settings are set via ML-Agents `EnvironmentParameters` under the `MouseVisuals` namespace. In TOML configs this maps to `[unity.env.MouseVisuals]`.

### Single-camera mode

Set `camera_enabled = 1` and select the desired camera with `camera_index`:

| `camera_index` | Camera | Notes |
|---------------|--------|-------|
| `0` | Bird's-eye (top-down orthographic) | No `MouseEyeImageEffect`, clear overhead view |
| `1` | Egocentric (mouse-eye perspective) | `MouseEyeImageEffect` applied |

The observation is delivered to Python as sensor **`obs_cam`**.

**TOML:**
```toml
[unity.env.MouseVisuals]
camera_enabled  = 1
camera_index    = 1   # egocentric mouse-eye camera
camera_width    = 64
camera_height   = 64
camera_grayscale = 1
```

### Multi-camera (binocular) mode

Set `camera_multi = 1` to receive simultaneous frames from both eye cameras (left + right). `camera_index` is ignored in this mode.

The two observations are delivered as separate sensors:

| Sensor name | Camera |
|-------------|--------|
| `obs_cam_left` | Left eye |
| `obs_cam_right` | Right eye |

`MouseEyeImageEffect` is applied independently on each camera.

**TOML:**
```toml
[unity.env.MouseVisuals]
camera_enabled  = 1
camera_multi    = 1   # binocular mode
camera_width    = 64
camera_height   = 64
camera_grayscale = 1
```

### Complete `MouseVisuals` parameter reference

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `MouseVisuals.camera_enabled` | 0/1 | 0 | Master switch — attach camera sensor to DlcAgent |
| `MouseVisuals.camera_multi` | 0/1 | 0 | 0 = single camera, 1 = binocular (left + right) |
| `MouseVisuals.camera_index` | int | 0 | Camera to use in single-camera mode (0 = birdeye, 1 = egocentric) |
| `MouseVisuals.camera_width` | int | 64 | Sensor output width in pixels |
| `MouseVisuals.camera_height` | int | 64 | Sensor output height in pixels |
| `MouseVisuals.camera_grayscale` | 0/1 | 1 | 1 = grayscale output, 0 = RGB |
| `MouseVisuals.birdeye.ortho_size` | float | 4 | Orthographic half-size for the bird's-eye camera |
| `MouseVisuals.mouseeye.fov` | float | 50 | Perspective field-of-view (degrees) for the egocentric camera |

Camera projection keys (`birdeye.*`, `mouseeye.*`) are read by `CameraEnvConfig` components attached to the respective camera GameObjects.

---

## Python side

When `camera_enabled = 1`, the `DlcAgent` observation dict will contain extra visual entries alongside the standard vector observation. With stable-baselines3 or raw mlagents-envs:

```python
# Single-camera mode — one extra sensor
obs = decision_steps["DLCInput"].obs
# obs[0]: vector obs (shape [5])
# obs[1]: camera frames (shape [N, H, W, C])  sensor name: obs_cam

# Multi-camera mode — two extra sensors
# obs[1]: left-eye frames   sensor name: obs_cam_left
# obs[2]: right-eye frames  sensor name: obs_cam_right
```

The sensor order matches the order in which `DlcAgent.Awake()` adds `CameraSensorComponent`s: vector observations first, then cameras in array order.

---

## See Also

- **[Agent System Reference](Agents.md)** — DlcAgent action/observation space
- **[Parameter System](ParameterSystem.md)** — how env params are set from Python/TOML
- **[RL Gymnasium Wrappers](../../rl/WRAPPER_ARCHITECTURE.md)** — wrapping visual observations for training
