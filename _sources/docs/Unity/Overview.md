# Unity Game Documentation

## Overview

This directory contains comprehensive documentation for the Unity-based MouseAR behavioral experiment framework. The system provides a modular architecture for closed loop behavioral experiments as well as reinforcement learning.

## Core Concepts

The framework separates responsibilities into distinct layers:
- **Episode Managers** orchestrate game lifecycle (timing, completion detection, ITI)
- **Spawners** create and place game objects (targets, hazards)
- **Agents** provide ML-Agents integration (observations, actions, rewards)
- **Parameter Systems** enable external configuration (Python → Unity)
- **Visual Feedback** provides feedback (success/failure indicators)

## Unity → Python Data Handoff

Unity session outputs are consumed by Python tooling for downstream processing and transfer.

- Runtime/session data is written to `UnityData_<MouseName>_<Timestamp>.json`.
- These files are typically attached in `dj_pipeline/gui_transfer` as `unity_json_path` entries.
- The Data Transfer GUI can prefill and auto-discover companion files from a shared `dataset_id`/`dataset_name`.

See [Python Data Transfer GUI](../python/DataTransferGUI.md) for transfer and remote-host configuration.

## Documentation Structure

### [Architecture Overview](Architecture.md)
**Core system design and relationships between components**

- Layered architecture diagram
- Component relationships and dependencies
- IEpisodeSpawner interface pattern
- Adapter pattern for spawners
- Parameter control systems (EnvironmentParameters vs KV Channel)
- Episode lifecycle flow

---

### [Episode Management System](EpisodeManagement.md)
**Detailed documentation of episode managers**

#### EpisodeManagerSingleWall
- State machine (Idle → Running → ITI)
- Event system (OnEpisodeBegin, OnAllTargetsCleared, OnEpisodeEnd, etc.)
- Timing control (episode length, ITI)
- Visual feedback integration (ColorOverlay, WhiteNoiseOverlay)
- Spawner management (switching, multiple spawners)
- Environment parameters
- KV channel commands
- Inspector configuration

#### SequenceTargetManager
- Sequential task orchestration
- Step-by-step target progression
- Parallel hazard walls with grace period
- Scoring integration (EpisodeScore)
- Target sequence formats (compact, comma-separated, random)
- Wall sequence formats (letters, numbers, random)
- Per-step events and timeout handling
- Environment parameters
- KV channel commands

---

### [Spawner System Reference](Spawners.md)
**Complete guide to spawner implementations**

#### IEpisodeSpawner Interface
- Interface definition and requirements
- Adapter pattern explanation

#### FloorTargetsSpawner
- 3D floor navigation with physics
- Vertical target areas + movable object
- Non-overlapping Z placement with jitter
- Physics configuration (mass, drag, forces)
- Optional features: distance/rotation-based coloring, jitter, lock-until-action
- EnvParams: 30+ configurable parameters
- Adapter implementation

#### GridTargetsSpawner
- N×N grid of StatefulTarget objects
- Wall segments between tiles
- Local space layout
- Used exclusively by SequenceTargetManager
- EnvParams: Grid layout, target scale, wall dimensions
- Direct IEpisodeSpawner implementation (no adapter)

#### ScreenSpawnerFromObject
- 2D wall surface spawning
- Non-overlapping circular placement
- Player + N targets on OrthoScreenFromObject
- Vertical band control (minY, maxY fractions)
- PlayerAgent3DOnScreen integration
- EnvParams: Target count, placement constraints

#### SideTargetsSpawnerFromObject
- Mixed floor + wall spawning
- Target objects (floor) + target areas (side walls)
- Non-overlapping with padding
- Configurable scales and placement
- EnvParams: Counts, scales, positioning

#### SimpleTargetSpawner
- Single invisible trigger cube
- Fixed position and size
- Minimal configuration
- EnvParams: Position (XYZ), size (XYZ), enabled flag

---

### [Parameter Control System](ParameterSystem.md)
**External configuration via Python**

#### ML-Agents EnvironmentParameters
- Python setup (`EnvironmentParametersChannel`)
- Unity access pattern (wait for Academy, `GetWithDefault`)
- Global parameters (`general.*`)
- Manager-specific parameters
- Spawner EnvParams components
- Complete Python example with all parameter types

#### KV Channel (Key-Value Side Channel)
- Python setup (`KvChannel`)
- Unity router (`KvManagersDirector`)
- Message format: `<namespace>.<property>=<value>`
- Supported commands for episode managers
- Supported commands for spawners
- Message batching and flush logic
- Complete Python example with real-time control


#### KV Reporting (Unity → Python)
- Reporter components
- Message receiving in Python
---

### [Agent System Reference](Agents.md)
**ML-Agents integration and training**

#### DlcAgent
- Action space, observation space details
- Optional camera sensor (visual observations)
- Environment parameter configuration

#### TouchFingerAgent
- Teleportation to NDC coordinates
- Action space: Continuous[2] (direct position)
- Observation space: UV,

#### PlayerAgent3DOnScreen
- Direct position control on wall surface
- Movement modes: Teleport vs smooth follow
- Clamping: Full object inside bounds

#### TTLReceiverAgent
- Reward/punishment from MultiEpisodeToAgentBridge
- Action space: Continuous[1] (TTL signal output)
- Observation space: Patch color, ITI flag
- Reward interface: `OnCorrect()`, `OnIncorrect()`
- Hardware synchronization via photodiode patch

---

### [Hockey Game](HockeyGame.md)
**Complete documentation for the Hockey floor-navigation task**

- Involved Unity scripts and their roles
- Component relationships and how they work together
- Full episode lifecycle (session start → init phase → running → ITI → end)
- Data flow: Python → Unity (EnvironmentParameters + KvChannel reference tables)
- Data flow: Unity → Python (KV telemetry, agent observations, rewards)
- Required TOML configuration for all keys
- Training profiles (`trainingstage1`, `trainingstage2`)
- End-to-end data round-trip diagram
- Troubleshooting

---

### [Visual Feedback & Utilities](VisualFeedback.md)
**Visual feedback systems and helper components**

#### ColorOverlay
- Static color overlay for success feedback
- Multi-display support
- Playback modes: Play, Flash, FadeIn, FadeOut
- Region control (fullscreen, normalized, pixels)
- Default: 1s green flash for success

#### WhiteNoiseOverlayGPU
- Animated noise overlay for punishment
- GPU shader-based rendering
- Configurable FPS and opacity
- Region control
- Used for: Timeouts, failures, wall collisions

#### StatefulTarget
- Interactive target with state machine (Static, Active, Inactive)
- Dwell-to-complete mechanic
- Material switching per state
- OnCompleted event
- Used by: GridTargetsSpawner, SequenceTargetManager

#### StatefulWall
- Similar to StatefulTarget but for hazards
- Used by: GridTargetsSpawner walls

#### MultiEpisodeToAgentBridge
- Connect multiple episode managers to agents
- ITIFlag integration
- Wiring: Managers → Bridge → Agents

#### ITIFlag
- Provide ITI state as observation
- Controlled by MultiEpisodeToAgentBridge

#### Utility Components
- **TargetKillOnPlayerDwell**: Destroy target after sustained player dwell
- **TargetKillOnArea**: Destroy object on TargetArea entry
- **TargetKillOnDistance**: Destroy if travels certain distance
- **ColorByDistance**: Dynamic coloring based on distance to player
- **ColorByRotation**: Dynamic coloring based on rotation of player
- **JitteryMovement**: Add random forces for unpredictability
- **ContainmentInBoxVolume**: Keep objects inside bounds

---

## Common Workflows

### Workflow 1: Touchscreen Task

```
Components:
- EpisodeManagerSingleWall
- ScreenSpawnerFromObject + ScreenSpawnerAdapter
- PlayerAgent3DOnScreen (spawned by ScreenSpawner)
- TTLReceiverAgent
- MultiEpisodeToAgentBridge

Success: All targets cleared (destroyed by player)
Failure: Timeout
```

### Workflow 2: Hockey Floor Navigation

```
Components:
- EpisodeManagerSingleWall
- FloorTargetsSpawner + FloorTargetsSpawnerAdapter
- DlcAgent (player, separate GameObject)
- TTLReceiverAgent
- MultiEpisodeToAgentBridge
- ColorOverlay (success), WhiteNoiseOverlay (timeout)

Success: MoveObject reaches TargetArea (TargetKillOnArea destroys it)
Failure: Timeout
```

### Workflow 3: Grid Sequence Memory Task

```
Components:
- SequenceTargetManager
- GridTargetsSpawner (N×N targets + walls)
- DlcAgent (player)
- EpisodeScore
- TTLReceiverAgent
- MultiEpisodeToAgentBridge
- ColorOverlay (success), WhiteNoiseOverlay (timeout/wall)

Success: Complete target sequence in order
Failure: Timeout, wall collision (grace period)
```
