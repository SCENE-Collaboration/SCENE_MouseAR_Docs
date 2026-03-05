# Episode Management System

## Overview

Episode managers orchestrate the game lifecycle: starting episodes, tracking time, detecting completion conditions, managing inter-trial intervals (ITI), and firing events. They provide a consistent framework for different task types while remaining agnostic to spatial layout (delegated to spawners).

## Managers ↔ Spawners Interaction Overview

This section summarizes how episode managers and spawners work together at runtime.

### Core idea

- Episode managers own lifecycle and task logic (start, run, success/fail, ITI)
- Spawners own object creation/cleanup (player, targets, walls, zones)
- Managers talk to spawners through `IEpisodeSpawner` (or direct spawner APIs for sequence/grid use cases)
- Runtime control comes from env params (`unity.env.*`) and KV commands (`unity.kv.*`)

### System flow (control path)

```text
Python Config / GUI
   ├─ unity.env.*  ─────→ EnvironmentParametersChannel
   └─ unity.kv.*   ─────→ KvChannel → KvManagersDirector
                                      │
                                      ├─ EpisodeManagerSingleWall
                                      └─ SequenceTargetManager
                                               │
                                               ▼
                                 Spawners (Floor / Screen / Side / Grid)
                                               │
                                               ▼
                                 Spawned objects (targets, walls, move object)
```

### EpisodeManagerSingleWall runtime loop

```text
StartEpisode()
  → Read env params (general.*)
  → Select active IEpisodeSpawner
  → ClearAll()
  → SpawnAll()   [or Init phase first]
  → Running
      ├─ success when TargetsAlive() == 0
      └─ failure when elapsed >= episode_length
  → EndEpisode()
      ├─ ClearAll()
      └─ enter ITI
  → ITI elapsed
      ├─ loopEpisodes=true  → StartEpisode()
      └─ loopEpisodes=false → Idle
```

### SequenceTargetManager runtime loop

```text
StartEpisode()
  → Read env params (timeouts, dwell, iti, random lengths)
  → GridSpawner.SpawnGrid() (targets + walls)
  → Build target sequence + activate hazard walls
  → Running (step-by-step)
      ├─ target completed → advance step
      ├─ wall hit (after grace) → fail
      └─ step timeout → fail
  → EndEpisode(success/fail)
      ├─ deactivate targets/walls
      └─ enter ITI (or immediate restart)
```

### Event flow (what downstream systems listen to)

```text
EpisodeManager events
  OnEpisodeBegin
  OnSpawningComplete
  OnAllTargetsCleared / OnEpisodeTimeout / OnEpisodeSuccess
  OnEpisodeEnd
         │
         ├─ Visual feedback (ColorOverlay / WhiteNoiseOverlayGPU)
         ├─ Agent bridge flags (Init / ITI observations)
         └─ Reporting components (if enabled)
```

### Quick role split for presentations

- **Manager = When and why** (state machine + task rules)
- **Spawner = What and where** (which objects, where they appear)
- **Director/channels = How externally controlled** (profiles, KV, env params)

## Two Manager Types

### EpisodeManagerSingleWall
**Purpose:** Simple "clear all targets" tasks with timeout

### SequenceTargetManager
**Purpose:** Sequential multi-step tasks with hazards.

---

## EpisodeManagerSingleWall

### Core Responsibilities

1. **Lifecycle Management**
   - Start episodes
   - Track elapsed time
   - Detect completion (all targets cleared OR timeout)
   - Manage ITI (inter-trial interval)

2. **Spawner Coordination**
   - Support multiple spawner types via `IEpisodeSpawner`
   - Switch between spawners at runtime
   - Clear and spawn objects at episode boundaries

3. **Event Broadcasting**
   - `OnEpisodeBegin` - Episode started
   - `OnSpawningComplete` - Objects created
   - `OnAllTargetsCleared` - Success condition met
    - `OnInitPhaseComplete` - Init target completed (when init phase is enabled)
   - `OnEpisodeEnd` - Episode finished (success or timeout)

4. **Visual Feedback Integration**
   - Optional green flash on success (`ColorOverlay`)
   - Optional noise overlay on timeout (`WhiteNoiseOverlayGPU`)

### State Machine

```
┌──────────┐
│   Idle   │  (Initial state)
└──────────┘
     │
     │ StartEpisode() called
     ▼
┌──────────┐
│   Init   │  (Optional: player must reach init target)
└──────────┘  [Only if enableInitPhase=true]
     │
     │ Init target completed by player
     │ (skipped if enableInitPhase=false)
     ▼
┌──────────┐
│ Running  │  (Tracking time, checking targets)
└──────────┘
     │
     │ AllTargetsCleared OR Timeout
     ▼
┌──────────┐
│   ITI    │  (Inter-trial interval)
└──────────┘
     │
     │ ITI elapsed
     ▼
  Idle (if loopEpisodes=false)
  OR
  Init/Running (if loopEpisodes=true, auto restart)
```

### Inspector Configuration

```csharp
[Header("Spawners")]
public List<MonoBehaviour> spawnerComponents;  // Drag adapters here
public int activeSpawnerIndex = 0;             // Which to use

[Header("Episode Timing")]
public float episodeLength = 10f;              // Max episode duration
public float itiLength = 2f;                   // Pause between episodes
public bool loopEpisodes = true;               // Auto-restart after ITI?
public bool randomizeItiLength = false;        // Randomize ITI (±25% variation)

[Header("Initialization Phase (optional)")]
public bool enableInitPhase = false;           // Enable init phase?
public SimpleTargetSpawner initSpawner;        // Init target spawner

[Header("Reward Flash on Success")]
public bool displayRewardFlash = false;        // Green flash on success?
public float rewardDisplayDuration = 0.2f;     // Duration

[Header("Noise Overlay")]
public bool displayNoiseOverlay = false;       // Noise on timeout?
public float noiseDisplayDuration = 0.2f;      // Duration

[Header("Events")]
public UnityEvent OnEpisodeBegin;
public UnityEvent OnEpisodeEnd;
public UnityEvent OnSpawningComplete;
public UnityEvent OnAllTargetsCleared;
public UnityEvent OnInitPhaseComplete;
```

### Episode Flow

#### 1. StartEpisode()

```csharp
public void StartEpisode()
{
    // Read environment parameters (ML-Agents)
    var envp = Academy.Instance.EnvironmentParameters;
    itiLength = envp.GetWithDefault("general.iti_length", itiLength);
    episodeLength = envp.GetWithDefault("general.episode_length", episodeLength);
    enableInitPhase = envp.GetWithDefault("general.enable_init_phase", enableInitPhase ? 1f : 0f) > 0.5f;
    randomizeItiLength = envp.GetWithDefault("general.randomize_iti_length", randomizeItiLength ? 1f : 0f) > 0.5f;

    // Optional: Configure reporter
    var reporter = GetComponent<EpisodeManagerSingleWallReporter>();
    if (reporter)
    {
        float v = envp.GetWithDefault("general.enable_reporting", reporter.enableReporting ? 1f : 0f);
        reporter.enableReporting = v > 0.5f;
    }

    OnEpisodeBegin?.Invoke();

    // Clear previous objects
    _active.ClearAll();
    if (initSpawner != null) initSpawner.ClearAll();

    // Optional init phase before running phase
    if (enableInitPhase && initSpawner != null)
    {
        State = EpisodeState.Init;
        initSpawner.SpawnAll();
    }
    else
    {
        StartRunningPhase();
    }
}
```

**Key Points:**
- Reads global env params: `general.iti_length`, `general.episode_length`
- Reads init-related env params: `general.enable_init_phase`, `general.randomize_iti_length`
- Configures optional reporter from env params
- Clears previous objects before spawning
- Enters `Init` state first when init phase is enabled
- Fires `OnInitPhaseComplete` when the init target is completed

#### 2. Running State (Update Loop)

```csharp
void TickRunning()
{
    Elapsed += Time.deltaTime;

    // Check for success condition
    int alive = _active != null ? _active.TargetsAlive() : 0;
    if (!_firedClearedThisEpisode && alive == 0)
    {
        _firedClearedThisEpisode = true;
        OnAllTargetsCleared?.Invoke();

        // Optional green flash
        if (displayRewardFlash)
        {
            var overlay = FindObjectOfType<ColorOverlay>();
            if (overlay) overlay.Play(rewardDisplayDuration);
        }

        EndEpisode();
        return;
    }

    // Check for timeout
    if (Elapsed >= episodeLength)
    {
        // Optional noise overlay
        if (displayNoiseOverlay)
        {
            var overlay = FindObjectOfType<WhiteNoiseOverlayGPU>();
            if (overlay) overlay.Play(noiseDisplayDuration);
        }

        EndEpisode();
    }
}
```

**Detection Logic:**
- **Success:** `TargetsAlive() == 0` (all cleared)
- **Timeout:** `Elapsed >= episodeLength`
- **Visual Feedback:** Overlays triggered automatically if enabled

#### 3. EndEpisode()

```csharp
public void EndEpisode()
{
    State = EpisodeState.ITI;
    ITIElapsed = 0f;

    if (randomizeItiLength)
    {
        float p = itiLength;
        _currentItiDuration = Random.Range(0f, p / 2f) - p / 4f + p;
        _currentItiDuration = Mathf.Max(0f, _currentItiDuration);
    }
    else
    {
        _currentItiDuration = itiLength;
    }

    // Clean up
    _active?.ClearAll();
    if (initSpawner != null) initSpawner.ClearAll();

    OnEpisodeEnd?.Invoke();
}
```

**Actions:**
- Clear all spawned objects
- Clear init target if present
- Compute ITI duration (fixed or randomized ±25%)
- Enter ITI state
- Fire `OnEpisodeEnd` event

#### 4. ITI State (Update Loop)

```csharp
void TickITI()
{
    ITIElapsed += Time.deltaTime;
    if (ITIElapsed >= _currentItiDuration)
    {
        if (loopEpisodes) StartEpisode();
        else State = EpisodeState.Idle;
    }
}
```

**Behavior:**
- Wait `itiLength` seconds
- If `loopEpisodes=true`: Automatically restart
- If `loopEpisodes=false`: Return to Idle (manual restart required)

### Spawner Management

#### Adding Spawners

In Inspector:
```
EpisodeManagerSingleWall
└── spawnerComponents (List)
    ├── Element 0: ScreenSpawnerAdapter
    ├── Element 1: SideTargetsSpawnerAdapter
    └── Element 2: FloorTargetsSpawnerAdapter
```

**Important:** Drag the **adapter component**, not the GameObject!

#### Runtime Switching

**Via KV Channel (from Python):**
```python
kv_channel.send_string("wallL.spawner=1")  # Switch to spawner at index 1
kv_channel.send_string("wallL.start=1")    # Restart episode
```

### Environment Parameters

**Read at StartEpisode():**

| Param Key | Type | Purpose | Default |
|-----------|------|---------|---------|
| `general.iti_length` | float | ITI duration (seconds) | Inspector value |
| `general.episode_length` | float | Episode timeout (seconds) | Inspector value |
| `general.enable_init_phase` | float | Enable init phase (0/1) | Inspector value |
| `general.randomize_iti_length` | float | Randomize ITI ±25% (0/1) | Inspector value |
| `general.enable_reporting` | float | Enable reporter (0/1) | Inspector value |
| `general.reporting_period` | float | Reporter update interval | 0.1 |

**Python Example:**
```python
env_params = {
    "general.iti_length": 3.0,
    "general.episode_length": 15.0,
    "general.enable_reporting": 1.0,
    "general.reporting_period": 0.5
}
```

### KV Channel Control

**Available Commands:**

| Key Pattern | Value | Effect |
|------------|-------|--------|
| `<id>.enabled` | 0/1 | Enable/disable manager |
| `<id>.spawner` | int | Set active spawner index |
| `<id>.episode_length` | float | Set episode duration |
| `<id>.iti_length` | float | Set ITI duration |
| `<id>.loop` | 0/1 | Set loopEpisodes |
| `<id>.display_reward_flash` | 0/1 | Enable/disable success flash |
| `<id>.display_noise_overlay` | 0/1 | Enable/disable timeout noise |
| `<id>.reward_display_duration` | float | Success flash duration |
| `<id>.noise_display_duration` | float | Timeout noise duration |
| `<id>.start` | 1 | Start episode now |


### Disable Behavior

`OnDisable()` is intentionally a no-op in the current implementation to avoid premature cleanup when managers are toggled by `KvManagersDirector`.

Cleanup happens inside explicit lifecycle methods (`StartEpisode`, `EndEpisode`) instead of on-disable.

### Init Phase → TTL Observation Path

For tasks using `TTLReceiverAgent`, init-phase state is exported as observations through this event chain:

1. `EpisodeManagerSingleWall.StartEpisode()` enters `EpisodeState.Init` and spawns `initSpawner` target.
2. Player dwells on target (`SimpleTargetSpawner` + `TargetKillOnPlayerDwell`) until completion.
3. `EpisodeManagerSingleWall.TickInit()` detects `initSpawner.IsCompletedByPlayer()` and fires `OnInitPhaseComplete`.
4. `MultiEpisodeToAgentBridge` listens to manager events and toggles flags:
    - `OnEpisodeBegin` → `initPhaseFlag.StartInitPhase()`
    - `OnInitPhaseComplete` → `initPhaseFlag.EndInitPhase()`
    - `OnEpisodeEnd` → `itiFlag.StartITI()`
5. `TTLReceiverAgent.CollectObservations()` appends both flags:
    - init phase flag (`obs[2]`)
    - ITI flag (`obs[1]`)


This means the policy receives explicit phase context while generating TTL output.
---

## SequenceTargetManager

### Core Responsibilities

1. **Sequential Task Orchestration**
   - Present targets one at a time in sequence
   - Track step-by-step progress
   - Support random or fixed sequences

2. **Parallel Hazards**
   - Activate hazard walls during episode
   - Immediate fail on wall collision (after grace period)
   - Configurable wall sequences

3. **Scoring Integration**
   - Track score via `EpisodeScore` component
   - Require score == target count for success
   - Reset score on wall collision

4. **Grace Period**
   - Ignore wall collisions for initial seconds
   - Prevent unfair fails at episode start

5. **Event Broadcasting**
   - Per-step events (`OnStepAdvanced`, `OnStepLabel`)
   - Success/timeout events
   - Wall grace violations

### State Machine

```
┌──────────┐
│   Idle   │  (Initial state)
└──────────┘
     │
     │ StartEpisode() called
     ▼
┌───────────────────────┐
│      Running          │
│  ┌─────────────────┐  │
│  │ Step 1 Active   │  │
│  └─────────────────┘  │
│         │ Target completed
│         ▼
│  ┌─────────────────┐  │
│  │ Step 2 Active   │  │
│  └─────────────────┘  │
│         │ ...
│         ▼
│  ┌─────────────────┐  │
│  │ Step N Active   │  │
│  └─────────────────┘  │
└───────────────────────┘
     │                   │
     │ All steps done    │ Timeout or Wall hit
     │ (Success)         │ (Failure)
     ▼                   ▼
┌──────────┐         ┌──────────┐
│   ITI    │◄────────│   ITI    │
└──────────┘         └──────────┘
     │
     │ ITI elapsed
     ▼
  StartEpisode() again (always loops)
```

### Inspector Configuration

```csharp
[Header("Wiring")]
public GridTargetsSpawner spawner;   // Grid of targets + walls
public EpisodeScore score;           // Optional scoring component

[Header("Target Sequence")]
public string targetSequenceText = "-1";  // "1593", "1,5,9,3", or "-1" (random)
public int randomTargetLength = 4;
public bool targetNoRepeatsInRandom = true;

[Header("Hazard Walls")]
public string wallSequenceText = "0";  // "ABC", "1,2,3", "0" (none), "-1" (random)
public int randomWallLength = 2;

[Header("Hazard Wall Grace Period")]
public float wallGraceSeconds = 1f;        // Ignore walls for N seconds
public UnityEvent OnWallIgnoredDuringGrace;

[Header("Timing")]
public float stepTimeoutSeconds = 10f;     // Per-step timeout
public float dwellTargetSeconds = 0.3f;    // Target dwell time
public float dwellWallSeconds = 0.1f;      // Wall dwell time (immediate fail)

[Header("ITI")]
public bool enableITI = true;
public float itiSeconds = 2f;

[Header("Task feedback")]
public bool displayNoiseOnTimeout = false;
public float noiseDisplayDuration = 1f;
public bool displayRewardFlash = false;
public float rewardDisplayDuration = 0.2f;
```

### Episode Flow

#### 1. StartEpisode()

```csharp
public void StartEpisode()
{
    // Read environment parameters
    var envp = Academy.Instance.EnvironmentParameters;
    stepTimeoutSeconds = envp.GetWithDefault("step_timeout_seconds", stepTimeoutSeconds);
    dwellTargetSeconds = envp.GetWithDefault("dwell_target_seconds", dwellTargetSeconds);
    dwellWallSeconds = envp.GetWithDefault("dwell_wall_seconds", dwellWallSeconds);
    wallGraceSeconds = envp.GetWithDefault("wall_grace_seconds", wallGraceSeconds);
    itiSeconds = envp.GetWithDefault("general.iti_length", itiSeconds);
    randomTargetLength = (int)envp.GetWithDefault("random_target_length", randomTargetLength);
    targetNoRepeatsInRandom = envp.GetWithDefault("target_no_repeats", targetNoRepeatsInRandom ? 1f : 0f) > 0.5f;

    // Spawn grid (all targets + walls)
    _targets = spawner.SpawnGrid();
    _walls = spawner.Walls?.ToList() ?? new List<GameObject>();

    // Reset all targets to Static
    foreach (var t in _targets)
    {
        t.SetStatic();
        t.dwellSeconds = dwellTargetSeconds;
    }

    // Reset all walls to Inactive
    foreach (var w in _walls)
    {
        var sw = w.GetComponent<StatefulWall>();
        if (sw)
        {
            sw.SetInactive();
            sw.dwellSeconds = dwellWallSeconds;
        }
    }

    // Build target sequence
    _targetRun = BuildTargetSequence(targetSequenceText, randomTargetLength, targetNoRepeatsInRandom, _targets.Count);
    lastRequiredScore = _targetRun.Count;

    // Activate hazard walls
    _hazardWalls.Clear();
    foreach (int wi in BuildWallSet(wallSequenceText, randomWallLength, _walls.Count))
    {
        _hazardWalls.Add(wi);
        var sw = _walls[wi].GetComponent<StatefulWall>();
        if (sw)
        {
            sw.OnCompleted.AddListener(HandleWallTriggered);
            sw.SetActive();
        }
    }

    // Reset scoring
    if (score) score.ResetScore();
    lastScore = 0;

    // Start sequence
    _curStep = -1;
    _stepTimer = 0f;
    lastEpisodeSuccess = false;
    State = RunState.Running;
    _wallGraceTimer = 0f;

    OnEpisodeBegin?.Invoke();
    AdvanceStep();  // Activate first target
}
```

**Key Points:**
- Spawns entire grid (all targets + walls) at once
- Builds target sequence (random or fixed)
- Activates subset of walls as hazards
- Starts at step -1, then advances to step 0 (first target)

#### 2. Target Sequence Formats

**Compact Style (gridSize ≤ 3):**
```
targetSequenceText = "1593"
→ Targets: #1, #5, #9, #3
```

**Comma-Separated (any gridSize):**
```
targetSequenceText = "1, 10, 23, 5"
→ Targets: #1, #10, #23, #5
```

**Random:**
```
targetSequenceText = "-1"
randomTargetLength = 4
targetNoRepeatsInRandom = true
→ Randomly select 4 unique targets
```

#### 3. Wall Sequence Formats

**Letter Style (first 26 walls):**
```
wallSequenceText = "ABC"
→ Walls A (index 0), B (index 1), C (index 2)
```

**Numeric Style:**
```
wallSequenceText = "1, 5, 10"
→ Walls at indices 0, 4, 9 (1-based)
```

**None:**
```
wallSequenceText = "0"
→ No walls active
```

**Random:**
```
wallSequenceText = "-1"
randomWallLength = 3
→ Randomly select 3 walls
```

#### 4. Step Progression

```csharp
void AdvanceStep()
{
    // Deactivate previous target
    if (_curStep >= 0 && _curStep < _targetRun.Count)
    {
        int prev = _targetRun[_curStep];
        _targets[prev].SetStatic();
    }

    _curStep++;

    // Check if sequence complete
    if (_curStep >= _targetRun.Count)
    {
        bool success = !score || score.Score == lastRequiredScore;
        EndEpisode(success);
        return;
    }

    // Activate next target
    int idx = _targetRun[_curStep];
    var cur = _targets[idx];
    cur.OnCompleted.AddListener(HandleTargetCompleted);
    cur.SetActive();

    _stepTimer = 0f;
    OnStepAdvanced?.Invoke(_curStep + 1);  // 1-based for display
    OnStepLabel?.Invoke($"Target #{idx + 1}");
}

void HandleTargetCompleted()
{
    if (score) score.AddPoint(1);
    AdvanceStep();
}
```

**Flow:**
1. Deactivate previous target (set to Static)
2. Increment step counter
3. If all steps done → Check score → EndEpisode()
4. Else: Activate next target in sequence
5. Reset step timer
6. Fire events with step info

#### 5. Parallel Hazard Detection

```csharp
void HandleWallTriggered()
{
    // Ignore during grace period
    if (_wallGraceTimer < wallGraceSeconds)
    {
        OnWallIgnoredDuringGrace?.Invoke();
        return;
    }

    // Trigger failure overlay
    var overlay = FindObjectOfType<WhiteNoiseOverlayGPU>();
    if (overlay) overlay.Play(noiseDisplayDuration);

    // Reset score (immediate fail)
    if (score) score.ResetScore();

    EndEpisode(false);
}
```

**Grace Period Logic:**
- `_wallGraceTimer` increments in Update()
- Wall collisions ignored if `_wallGraceTimer < wallGraceSeconds`
- After grace period: Immediate fail + score reset

**Purpose:**
- Prevent unfair fails when episode just started
- Agent needs time to move away from spawn location

#### 6. Step Timeout

```csharp
void Update()
{
    if (State == RunState.Running)
    {
        _wallGraceTimer += Time.deltaTime;
        _stepTimer += Time.deltaTime;

        if (_stepTimer >= stepTimeoutSeconds)
        {
            OnEpisodeTimeout?.Invoke();

            if (displayNoiseOnTimeout)
            {
                var overlay = FindObjectOfType<WhiteNoiseOverlayGPU>();
                if (overlay) overlay.Play(noiseDisplayDuration);
            }

            EndEpisode(false);
        }
    }
}
```

**Per-Step Timeout:**
- Each step has independent timeout (`stepTimeoutSeconds`)
- Timer resets on each `AdvanceStep()`
- If timeout expires: Fire `OnEpisodeTimeout`, show noise, fail episode

#### 7. EndEpisode()

```csharp
public void EndEpisode(bool success)
{
    // Unhook current target
    if (_curStep >= 0 && _curStep < _targetRun.Count)
    {
        int idx = _targetRun[_curStep];
        _targets[idx].OnCompleted.RemoveListener(HandleTargetCompleted);
        _targets[idx].SetInactive();
    }

    // Inactivate all targets
    foreach (var t in _targets) t.SetInactive();

    // Unhook and inactivate all walls
    foreach (var w in _walls)
    {
        var sw = w.GetComponent<StatefulWall>();
        if (sw)
        {
            sw.OnCompleted.RemoveListener(HandleWallTriggered);
            sw.SetInactive();
        }
    }

    lastEpisodeSuccess = success;
    lastScore = score ? score.Score : 0;

    // Success feedback
    if (success)
    {
        OnEpisodeSuccess?.Invoke();
        if (displayRewardFlash)
        {
            var overlay = FindObjectOfType<ColorOverlay>();
            if (overlay) overlay.Play(rewardDisplayDuration);
        }
    }

    OnEpisodeEnd?.Invoke();

    // Always go to ITI, then auto-restart
    if (enableITI)
    {
        State = RunState.ITI;
        _itiTimer = 0f;
        OnITIStart?.Invoke();
    }
    else
    {
        State = RunState.Idle;
        StartEpisode();
    }
}
```

**Cleanup:**
- Unhook all event listeners
- Inactivate all targets and walls
- Record outcome and score
- Show success overlay if applicable
- Enter ITI → Auto-restart

### Environment Parameters

**Read at StartEpisode():**

| Param Key | Type | Purpose | Default |
|-----------|------|---------|---------|
| `step_timeout_seconds` | float | Per-step timeout | Inspector |
| `dwell_target_seconds` | float | Target dwell time | Inspector |
| `dwell_wall_seconds` | float | Wall dwell time | Inspector |
| `wall_grace_seconds` | float | Wall grace period | Inspector |
| `general.iti_length` | float | ITI duration | Inspector |
| `random_target_length` | int | Random sequence length | Inspector |
| `target_no_repeats` | float | No-repeat random (0/1) | Inspector |

### KV Channel Control

**Available Commands:**

| Key Pattern | Value | Effect |
|------------|-------|--------|
| `<id>.enabled` | 0/1 | Enable/disable manager |
| `<id>.step_timeout_seconds` | float | Per-step timeout |
| `<id>.dwell_target_seconds` | float | Target dwell time |
| `<id>.dwell_wall_seconds` | float | Wall dwell time |
| `<id>.wall_grace_seconds` | float | Wall grace period |
| `<id>.enable_iti` | 0/1 | Enable ITI |
| `<id>.iti_seconds` | float | ITI duration |
| `<id>.target_sequence` | string | Target sequence ("1593", "-1") |
| `<id>.wall_sequence` | string | Wall sequence ("ABC", "0", "-1") |
| `<id>.random_target_length` | int | Random sequence length |
| `<id>.random_wall_length` | int | Random wall count |
| `<id>.target_no_repeats` | 0/1 | No repeats in random |
| `<id>.display_noise_timeout` | 0/1 | Noise on timeout |
| `<id>.noise_display_duration` | float | Noise duration |
| `<id>.display_reward_flash` | 0/1 | Flash on success |
| `<id>.reward_display_duration` | float | Flash duration |
| `<id>.start` | 1 | Start episode now |


### Scoring Integration

#### EpisodeScore Component

```csharp
public class EpisodeScore : MonoBehaviour
{
    public int Score { get; private set; }

    public UnityEvent<int> OnScoreChanged;

    public void ResetScore() { Score = 0; OnScoreChanged?.Invoke(Score); }
    public void AddPoint(int amount = 1) { Score += amount; OnScoreChanged?.Invoke(Score); }
}
```

#### Usage in SequenceTargetManager

```csharp
// At StartEpisode()
if (score) score.ResetScore();
lastRequiredScore = _targetRun.Count;  // Expected score for success

// At each step completion
void HandleTargetCompleted()
{
    if (score) score.AddPoint(1);
    AdvanceStep();
}

// At sequence completion
void AdvanceStep()
{
    if (_curStep >= _targetRun.Count)
    {
        bool success = !score || score.Score == lastRequiredScore;
        EndEpisode(success);
    }
}

// On wall collision
void HandleWallTriggered()
{
    if (score) score.ResetScore();  // Immediate fail
    EndEpisode(false);
}
```

---

## See Also

- **[Architecture Overview](Architecture.md)** - System design
- **[Spawner Reference](Spawners.md)** - All spawner types
- **[Parameter System](ParameterSystem.md)** - Env params and KV control
- **[Agent Integration](Agents.md)** - ML-Agents connection
