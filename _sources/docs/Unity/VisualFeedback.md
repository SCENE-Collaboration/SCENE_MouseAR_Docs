# Visual Feedback & Utility Components

## Overview

This document covers visual feedback systems, interaction components, and utility scripts used throughout the Unity game.

---

## Visual Feedback

### ColorOverlay

**Purpose:** Display solid color overlay for visual feedback (success, checkpoints, etc.)

**Features:**
- Static color display (vs animated)
- Multi-display support
- Multiple playback modes: flash, fade in/out
- Configurable opacity and duration

**Configuration:**
```csharp
[Header("Color & Opacity")]
public Color overlayColor = Color.green;
[Range(0f,1f)] public float opacity = 0.5f;

[Header("Displays")]
public int[] targetDisplays = new int[] { 0 };
public bool autoActivateDisplays = true;

[Header("Region")]
public RegionMode regionMode = RegionMode.Fullscreen;
public Rect regionNormalized = new Rect(0, 0, 1, 1);
public RectInt regionPixels = new RectInt(0, 0, 1920, 1080);

[Header("Default Duration")]
public float defaultDuration = 0.2f;
```

**Integration with Episode Managers:**
```csharp
// EpisodeManagerSingleWall
[Header("Reward Flash on Success")]
public bool displayRewardFlash = false;
public float rewardDisplayDuration = 0.2f;

// Automatic triggering in code:
if (displayRewardFlash)
{
    var overlay = FindObjectOfType<ColorOverlay>();
    if (overlay) overlay.Play(rewardDisplayDuration);
}
```

### WhiteNoiseOverlayGPU

**Purpose:** Animated noise overlay for punishment/failure feedback

**Features:**
- GPU shader-based animated white noise
- Multi-display support
- Region control (fullscreen or partial)
- Configurable FPS and opacity

**Configuration:**
```csharp
[Header("Material & Look")]
public Material noiseMaterial;  // Assign FullscreenNoise shader material
[Range(0f,1f)] public float opacity = 1f;
public float noiseFps = 60f;

[Header("Displays")]
public int[] targetDisplays = new int[] { 0 };
public bool autoActivateDisplays = true;

[Header("Region")]
public RegionMode regionMode = RegionMode.Fullscreen;
public Rect regionNormalized = new Rect(0, 0, 1, 1);
public RectInt regionPixels = new RectInt(0, 0, 1920, 1080);
```

**Integration:**
```csharp
// EpisodeManagerSingleWall
[Header("Noise Overlay")]
public bool displayNoiseOverlay = false;
public float noiseDisplayDuration = 0.2f;

// Automatic on timeout:
if (displayNoiseOverlay)
{
    var overlay = FindObjectOfType<WhiteNoiseOverlayGPU>();
    if (overlay) overlay.Play(noiseDisplayDuration);
}

// SequenceTargetManager - on wall collision:
void HandleWallTriggered()
{
    var overlay = FindObjectOfType<WhiteNoiseOverlayGPU>();
    if (overlay) overlay.Play(noiseDisplayDuration);
    EndEpisode(false);
}
```
---

## Interaction Components

### StatefulTarget

**Purpose:** Interactive target with dwell-to-complete mechanic

**States:**
- **Static:** Visible but not interactive (sawdust material)
- **Active:** Interactive, waiting for player (checked material)
- **Inactive:** Hidden, no collision (disabled renderers)

**Configuration:**
```csharp
[Header("Materials / Visuals")]
public Material matSawDust;     // Static appearance
public Material matChecked;     // Active appearance
public bool disableRenderersWhenInactive = true;

[Header("Interaction")]
public float dwellSeconds = 0.3f;  // Required dwell time

[Header("Events")]
public UnityEvent OnCompleted;  // Fired when player completes dwell
```

**API:**
```csharp
StatefulTarget target;

// State control
target.SetStatic();    // Visible, not interactive
target.SetActive();    // Visible, interactive (start listening for player)
target.SetInactive();  // Hidden, disabled

// Check state
var state = target.State;  // TargetState.Static/Active/Inactive

// Event subscription
target.OnCompleted.AddListener(HandleTargetCompleted);
```

**Interaction Logic:**
1. Player enters trigger → Start dwell timer
2. Player stays inside for `dwellSeconds` → Fire `OnCompleted`
3. Player exits before completion → Reset timer
4. Multiple players tracked (count maintained)

**Used By:**
- GridTargetsSpawner (sequence tasks)
- SequenceTargetManager (step-by-step progression)

**Requirements:**
- GameObject has `Collider` (isTrigger=true)
- Player tagged "Player"
- At least one has Rigidbody for trigger detection

### StatefulWall

**Purpose:** Hazard wall with similar state system (not documented in provided files but referenced)

**Similar to StatefulTarget:**
- States: Static, Active, Inactive
- Dwell mechanic (but much shorter, e.g., 0.1s)
- OnCompleted event (used for immediate fail)

**Used By:**
- GridTargetsSpawner (hazard walls)
- SequenceTargetManager (parallel hazards)

---

## Bridge Components

### MultiEpisodeToAgentBridge

**Purpose:** Connect multiple episode managers to ML-Agents, translating episode outcomes to agent rewards/punishments

**Responsibilities:**
1. Listen to episode manager events
2. Detect success/failure conditions
3. Call agent reward/punishment methods
4. Prevent duplicate calls per episode
5. Manage ITI flag for observations

**Configuration:**
```csharp
[Header("Listen to these managers")]
public List<EpisodeManagerSingleWall> wallManagers = new();
public List<SequenceTargetManager> sequenceManagers = new();

[Header("Notify these agents")]
public List<TTLReceiverAgent> agents = new();
public bool autoFindAgentIfEmpty = true;

[Header("ITI flag for observations")]
public ITIFlag itiFlag;
```

**Integration:**
```
Scene Hierarchy:
└── BridgeManager (GameObject)
    └── MultiEpisodeToAgentBridge
        ├── wallManagers[0] → EpisodeManagerSingleWall
        ├── wallManagers[1] → EpisodeManagerSingleWall
        ├── sequenceManagers[0] → SequenceTargetManager
        ├── agents[0] → TTLReceiverAgent (ML-Agents)
        └── itiFlag → ITIFlag
```

**Agent Interface (TTLReceiverAgent):**
```csharp
public class TTLReceiverAgent : Agent
{
    public void OnCorrect()
    {
        AddReward(1f);
        EndEpisode();
    }

    public void OnIncorrect()
    {
        AddReward(-1f);
        EndEpisode();
    }
}
```

### ITIFlag

**Purpose:** Provide ITI state as observation for ML-Agents

**Configuration:**
```csharp
public bool InITI { get; private set; } = false;

public void StartITI() { InITI = true; }
public void EndITI() { InITI = false; }
```

---

## Utility Components

### TargetKillOnPlayerDwell

**Purpose:** Destroy target when player remains inside trigger for configured dwell duration

**Usage:**
```csharp
// Automatically added by SimpleTargetSpawner:
var target = GameObject.CreatePrimitive(PrimitiveType.Cube);
var dwell = target.AddComponent<TargetKillOnPlayerDwell>();
dwell.dwellTime = 0.1f;

// On sustained player dwell → Destroy target
```

**Requirements:**
- Target has Collider (isTrigger=true)
- Player tagged "Player"

### TargetKillOnArea

**Purpose:** Destroy object when it enters a "TargetArea" trigger

**Usage:**
```csharp
// Added to MoveObject by FloorTargetsSpawner:
moveObj.AddComponent<TargetKillOnArea>();

// When MoveObject touches TargetArea → Destroy MoveObject
```

**Used For:**
- FloorTargetsSpawner: MoveObject reaches target zone
- SideTargetsSpawner: Floor objects reach wall zones

### TargetKillOnDistance

**Purpose:** Destroy object if it travels certain distance

**Configuration:**
```csharp
public float maxDistance = 10f;  // 0 = disabled
```

**Usage:**
```csharp
// Added to MoveObject by spawners:
var distKill = moveObj.AddComponent<TargetKillOnDistance>();
distKill.maxDistance = 15f;
```

### ColorByDistance

Change object color based on distance to target

**Configuration:**
```csharp
public Transform target;  // What to measure distance from (default: Camera.main)
public float minDistance = 0f;
public float maxDistance = 10f;
public Color closeColor = Color.green;
public Color farColor = Color.red;
```

**Usage:**
```csharp
// Added by FloorTargetsSpawner when enableDistanceColor=true:
var colorByDist = moveObj.AddComponent<ColorByDistance>();
colorByDist.minDistance = 0f;
colorByDist.maxDistance = 10f;
colorByDist.closeColor = Color.green;
colorByDist.farColor = Color.red;
colorByDist.target = Camera.main.transform;
```

### ColorByRotation

**Purpose:** Change object color based on Y-axis rotation

**Configuration:**
```csharp
public Transform target;  // Whose rotation to measure
public float minRotationY = 0f;
public float maxRotationY = 360f;
public Color minRotationColor = Color.white;
public Color maxRotationColor = Color.black;
public bool useLocalRotation = true;
```

**Usage:**
```csharp
// Added by FloorTargetsSpawner when enableRotationColor=true:
var colorByRot = moveObj.AddComponent<ColorByRotation>();
colorByRot.minRotationY = 0f;
colorByRot.maxRotationY = 360f;
colorByRot.target = Camera.main.transform;
```


### JitteryMovement

**Purpose:** Add small random forces to Rigidbody for unpredictable movement

**Configuration:**
```csharp
public bool enabledJitter = true;
public float weightingFactor = 1f;    // Strength
public float frequencyHz = 2f;        // How often to apply force
public float baseAngleDeg = 8f;       // Direction change angle
```

**Usage:**
```csharp
// Added by FloorTargetsSpawner when enableJitter=true:
var jitter = moveObj.AddComponent<JitteryMovement>();
jitter.weightingFactor = 1f;
jitter.frequencyHz = 2f;
jitter.baseAngleDeg = 8f;
```

### ContainmentInBoxVolume

Keep object inside a BoxCollider volume
---

## See Also

- **[Architecture Overview](Architecture.md)** - System design
- **[Episode Management](EpisodeManagement.md)** - Episode lifecycle
- **[Spawner Reference](Spawners.md)** - Spawner components
