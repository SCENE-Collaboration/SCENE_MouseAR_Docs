# Spawner System Reference

## Overview

Spawners are responsible for creating and placing game objects (players, targets, walls) in the Unity scene. They implement the `IEpisodeSpawner` interface to provide a consistent API for episode managers, while internally handling spatial layout, collision avoidance, and physics configuration.

For a high-level lifecycle/control-flow view of how managers call spawners during episodes, see the **Managers ↔ Spawners Interaction Overview** section in [Episode Management](EpisodeManagement.md).

## IEpisodeSpawner Interface

All spawners must implement this interface (directly or via adapter):

```csharp
public interface IEpisodeSpawner
{
    void ClearAll();         // Remove all spawned objects
    void SpawnAll();         // Create player + targets
    int TargetsAlive();      // Count remaining targets
    GameObject GetPlayer();  // Get player instance (or null)
}
```

## Adapter Pattern

Most spawners use a two-component architecture:

**Implementation Component** → Contains spawning logic
**Adapter Component** → Implements `IEpisodeSpawner` interface

**Benefits:**
- Clean separation of concerns
- Reusable spawning logic without interface dependencies
- Easy to add new episode manager types

---

## FloorTargetsSpawner

### Purpose

Spawns vertical target areas on the floor and a movable physics object. Designed for 3D navigation tasks where the agent must push/chase an object into target zones.


### Components

```
GameObject
├── FloorTargetsSpawner (implementation)
├── FloorTargetsSpawnerAdapter (IEpisodeSpawner)
└── FloorTargetsSpawnerEnvParams (optional, ML-Agents params)
```

### Configuration

#### Prefabs
```csharp
public GameObject moveObjectPrefab;   // Rigidbody + Collider (the object to push)
public GameObject targetAreaPrefab;   // BoxCollider (isTrigger), tag "TargetArea"
```

#### Spatial Layout
```csharp
[Range(1, 3)] public int numTargetAreas = 2;  // 1-3 vertical zones

// Target area placement
public float targetX = -8f;           // World X line (fixed)
public float areaCenterY = 0.5f;      // Height (world Y)
public float areaHeightY = 1.0f;      // Height span (meters)
public float areaThicknessX = 0.12f;  // Thickness along X (meters)
public float areaWidthZ = 1.2f;       // Width along Z (meters)

// Z band & spacing
public float zMin = -6f;
public float zMax = 6f;
public float minGapZ = 0.5f;          // Min distance between areas
public float jitterZ = 0.35f;         // Random Z offset
public bool snapZToIntegers = true;   // Snap to integer Z coords
```

#### MoveObject Configuration
```csharp
// Spawn position
public float moveObjectX = 0f;
public float moveObjectY = 0.5f;
public bool randomizeStartZ = true;
public float moveObjectZ = 0f;        // Used if randomizeStartZ=false
public float objectMinDistanceFromAreasZ = 1.5f;  // Safety margin

// Physics
public float moveObjectScale = 1.0f;  // Uniform scale (X,Z)
public float moveObjectMass = 1.0f;   // Rigidbody mass (kg)
public float moveObjectDrag = 0.0f;   // Linear drag
public float moveObjectAngularDrag = 0.05f;  // Angular drag

// Destruction
public float moveObjectMaxDistance = 0f;  // Max travel distance (0 = infinite)
public bool spawnTarget = true;       // Enable/disable target spawning
```

#### Visual Feedback (Optional)
```csharp
// Distance-based color
public bool enableDistanceColor = false;
public Transform distanceColorTarget;  // Target to measure from (default: Camera.main)
public float distanceColorMin = 0f;    // Distance for close color
public float distanceColorMax = 10f;   // Distance for far color
public Color closeColor = Color.green;
public Color farColor = Color.red;

// Rotation-based color
public bool enableRotationColor = false;
public Transform rotationColorTarget;  // Target to measure from
public float rotationColorMin = 0f;    // Y rotation (degrees) for min color
public float rotationColorMax = 360f;  // Y rotation (degrees) for max color
public Color minRotationColor = Color.white;
public Color maxRotationColor = Color.black;
public bool useLocalRotation = true;   // Local vs world rotation
```

#### Object Jitter (Optional)
```csharp
public bool enableJitter = false;
public float jitterWeightingFactor = 1f;  // Jitter strength
public float jitterFrequency = 2f;        // Jitter Hz
public float jitterBaseAngleDeg = 8f;     // Direction change angle
```

#### Lock Until Action (Optional)
```csharp
public bool enableMoveByAction = false;  // Start kinematic, unlock on agent action
```

### Spawning Algorithm

**Target Areas:**
1. Compute N non-overlapping Z centers in [zMin, zMax]
2. Snap to integers if enabled
3. Add random jitter (±jitterZ)
4. Resolve overlaps (iterative repulsion)
5. Create BoxCollider trigger volumes at (targetX, areaCenterY, zc)
6. Scale to world size: (areaThicknessX, areaHeightY, areaWidthZ)

**MoveObject:**
1. Choose Z position:
   - If `randomizeStartZ=true`: Random Z far from target areas
   - Else: Use `moveObjectZ`
2. Create at (moveObjectX, moveObjectY, Z)
3. Add/configure components:
   - `Rigidbody` (mass, drag, angularDrag)
   - `TargetKillOnArea` (destroys on target collision)
   - `TargetKillOnDistance` (destroys if travels > maxDistance)
   - `ColorByDistance` (if enableDistanceColor)
   - `ColorByRotation` (if enableRotationColor)
   - `JitteryMovement` (if enableJitter)
4. Scale uniformly: (scale, 1, scale)
5. Parent to neutralParent (if set)

### Adapter: FloorTargetsSpawnerAdapter

```csharp
public class FloorTargetsSpawnerAdapter : MonoBehaviour, IEpisodeSpawner
{
    public FloorTargetsSpawner spawner;

    public void ClearAll() => spawner?.ClearAll();
    public void SpawnAll() => spawner?.SpawnAll();

    // Count objects with TargetKillOnArea component (the MoveObject)
    public int TargetsAlive()
    {
        var killables = spawner.GetComponentsInChildren<TargetKillOnArea>(true);
        int alive = 0;
        foreach (var k in killables)
            if (k && k.gameObject && k.gameObject.activeInHierarchy)
                alive++;
        return alive;
    }

    public GameObject GetPlayer() => null;  // No player spawned by this spawner
}
```

**Success Condition:** `TargetsAlive() == 0` (MoveObject destroyed by TargetKillOnArea)

### EnvParams: FloorTargetsSpawnerEnvParams

**Supported Parameters:**

| Key Pattern | Type | Purpose |
|-------------|------|---------|
| `<prefix>.enabled` | bool | Enable/disable spawner |
| `<prefix>.num_target_areas` | int | Number of target zones (1-3) |
| `<prefix>.target_x` | float | Target X position |
| `<prefix>.area_center_y` | float | Target Y center |
| `<prefix>.area_height_y` | float | Target height |
| `<prefix>.area_thickness_x` | float | Target thickness |
| `<prefix>.area_width_z` | float | Target width |
| `<prefix>.z_min` | float | Min Z coordinate |
| `<prefix>.z_max` | float | Max Z coordinate |
| `<prefix>.min_gap_z` | float | Min gap between targets |
| `<prefix>.jitter_z` | float | Random Z jitter |
| `<prefix>.target_scale_multiplier` | float | Scale multiplier for targets (X,Z only) |
| `<prefix>.snap_z_to_integers` | bool | Snap Z to integers |
| `<prefix>.move_object_x/y/z` | float | MoveObject position |
| `<prefix>.randomize_start_z` | bool | Random MoveObject Z |
| `<prefix>.object_min_distance_z` | float | Min distance from targets |
| `<prefix>.move_object_scale` | float | MoveObject scale |
| `<prefix>.move_object_mass` | float | Rigidbody mass |
| `<prefix>.move_object_drag` | float | Linear drag |
| `<prefix>.move_object_angular_drag` | float | Angular drag |
| `<prefix>.move_object_max_distance` | float | Max travel distance |
| `<prefix>.spawn_target` | bool | Enable target spawning |
| `<prefix>.enable_jitter` | bool | Enable jitter |
| `<prefix>.jitter_base_angle_deg` | float | Jitter angle |
| `<prefix>.jitter_weighting_factor` | float | Jitter strength |
| `<prefix>.jitter_frequency` | float | Jitter Hz |
| `<prefix>.enable_distance_color` | bool | Enable distance coloring |
| `<prefix>.distance_color_min/max` | float | Distance color range |
| `<prefix>.enable_rotation_color` | bool | Enable rotation coloring |
| `<prefix>.rotation_color_min/max` | float | Rotation color range |
| `<prefix>.use_local_rotation` | bool | Local rotation coloring |
| `<prefix>.enable_move_by_action` | bool | Lock until action |

### Integration Example

```
Scene Hierarchy:
└── FloorSpawner (GameObject)
    ├── FloorTargetsSpawner
    ├── FloorTargetsSpawnerAdapter
    └── FloorTargetsSpawnerEnvParams (optional)

EpisodeManagerSingleWall:
└── spawnerComponents[0] → FloorTargetsSpawnerAdapter
```

---

## SimpleTargetSpawner

### Purpose

Spawns a single target (cube) at a specified position for initialization phases. Player must reach and dwell on target to complete. Supports invisible triggers, polka dot patterns, and completion tracking.

**Typical Use:** Init phase in `EpisodeManagerSingleWall` where player must reach a "home" position before main episode begins.

### Components

```
GameObject
├── SimpleTargetSpawner (implementation)
├── SimpleTargetSpawnerAdapter (optional, IEpisodeSpawner)
└── SimpleTargetSpawnerEnvParams (optional, ML-Agents params)
```

**Notes:**
- `SimpleTargetSpawner` itself does **not** implement `IEpisodeSpawner`.
- For init phase in `EpisodeManagerSingleWall`, use `initSpawner` reference directly.
- If you want to use it in `spawnerComponents`, add `SimpleTargetSpawnerAdapter`.

### Configuration

#### Target Properties
```csharp
[Header("Target Properties")]
public Vector3 targetPosition = new Vector3(0f, 0.5f, 5f);  // World position
public Vector3 targetSize = new Vector3(1f, 1f, 1f);        // World scale
public string targetLayer = "Invisible";                    // Layer name
public float dwellTime = 0.1f;                              // Dwell time (seconds)
```

#### Polka Dot Pattern (Optional)
```csharp
[Header("Polka Dot Pattern")]
public bool usePolkaDotPattern = true;       // Enable shader
public Color dotColor = Color.white;         // Dot color
public Color backgroundColor = Color.black;   // Background color
[Range(0.01f, 0.5f)]
public float dotSize = 0.4f;                 // Dot radius
[Range(0.1f, 2.0f)]
public float dotSpacing = 0.1f;              // Spacing between dots
```

#### Parent (Optional)
```csharp
[Header("Optional Parent")]
public Transform neutralParent;  // Parent transform for spawned target
```

### Spawning Algorithm

**Target Creation:**
1. Clear any existing target
2. Create cube primitive at `targetPosition` with `targetSize` scale
3. Set layer to `targetLayer` (e.g., "Invisible", "BottomView")
4. Configure collider as trigger
5. Tag as "Target"
6. Add `TargetKillOnPlayerDwell` component with `dwellTime`
7. If `usePolkaDotPattern=true`: Apply polka dot shader material
8. Set parent if `neutralParent` is assigned
9. Reset `_completedByPlayer` flag to false

**Polka Dot Shader:**
- Shader: `Custom/PolkaDotPattern`
- Creates circular dots in a repeating grid pattern
- Properties: dot color, background color, dot size, spacing
- Applied via dynamically created Material

### Completion Tracking

```csharp
private bool _completedByPlayer = false;

public bool IsCompletedByPlayer() => _completedByPlayer;

private void OnTargetDestroyed()
{
    _completedByPlayer = true;
}
```

**Flow:**
1. `SpawnAll()` resets `_completedByPlayer = false`
2. `TargetKillOnPlayerDwell` detects player entry and starts dwell timer
3. After `dwellTime` seconds, `TargetKillOnPlayerDwell` invokes `onDestroy` callback
4. Callback sets `_completedByPlayer = true`
5. `TargetKillOnPlayerDwell` destroys GameObject
6. `EpisodeManagerSingleWall.TickInit()` checks `IsCompletedByPlayer()` each frame
7. When true, fires `OnInitPhaseComplete` and transitions to Running state

### Public API

```csharp
public void SpawnAll();                  // Create target
public void ClearAll();                  // Destroy target
public GameObject GetTarget();           // Get target GameObject (can be null)
public bool IsCompletedByPlayer();       // True if player destroyed target
public bool IsTargetAlive();             // True if target exists and active
```

### Integration Example

```
Scene Hierarchy:
└── InitPlatform (GameObject)
    └── SimpleTargetSpawner
        - targetPosition: (-2, 0, -4)
        - targetSize: (4, 0.1, 4)
        - targetLayer: "BottomView"
        - dwellTime: 0.2
        - usePolkaDotPattern: true
        - dotColor: white
        - backgroundColor: black

EpisodeManagerSingleWall:
└── initSpawner → SimpleTargetSpawner
└── enableInitPhase: true

MultiEpisodeToAgentBridge:
└── initPhaseFlag → InitPhaseFlag component
```

### Adapter: SimpleTargetSpawnerAdapter

Use this adapter when `SimpleTargetSpawner` should participate as a standard episode spawner:

```csharp
[RequireComponent(typeof(SimpleTargetSpawner))]
public class SimpleTargetSpawnerAdapter : MonoBehaviour, IEpisodeSpawner
{
    public SimpleTargetSpawner spawner;
    public void ClearAll() => spawner?.ClearAll();
    public void SpawnAll() => spawner?.SpawnAll();
    public int TargetsAlive() => spawner != null && spawner.IsTargetAlive() ? 1 : 0;
    public GameObject GetPlayer() => null;
}
```

### EnvParams: SimpleTargetSpawnerEnvParams

`SimpleTargetSpawnerEnvParams` reads parameters on `Academy` reset and applies them to the init target.

| Key Pattern | Type | Purpose |
|-------------|------|---------|
| `<prefix>.enabled` | bool | Enable/disable spawner |
| `<prefix>.position_x/y/z` | float | Target world position |
| `<prefix>.size_x/y/z` | float | Target world scale |
| `<prefix>.visible` | bool | Layer switch: `BottomView` vs `Invisible` |
| `<prefix>.dwell_time` | float | Required dwell duration |

Example prefix: `simpleTarget`.

---

## GridTargetsSpawner

### Purpose

Spawns an N×N grid of targets and optional walls between tiles. Used by `SequenceTargetManager` for sequential navigation tasks with hazards.


### Components

```
GameObject
├── GridTargetsSpawner (implementation + interface)
├── GridTargetsSpawnerEnvParams (optional)
```

**Note:** GridTargetsSpawner directly implements IEpisodeSpawner (no adapter needed).

### Configuration

#### Prefabs
```csharp
public GameObject targetPrefab;  // Must have StatefulTarget + trigger collider
public GameObject wallPrefab;    // Must have StatefulWall + trigger BoxCollider(size 1,1,1)
```

#### Grid Layout
```csharp
[Range(2, 5)] public int gridSize = 3;    // N in N×N (2-5)
public float cellSize = 0.3f;             // Base cell size
public float gap = 0.05f;                 // Extra spacing between cells
public float yLevel = 1.5f;               // Local Y for target centers
public Vector3 targetWorldScale = new(0.2f, 1f, 0.2f);  // Target size
```

#### Wall Configuration
```csharp
public float wallThickness = 0.3f;        // Wall narrow dimension (meters)
public float wallHeight = 1.0f;           // Wall height (meters)
[Range(0f, 10f)] public float wallLengthInsetFrac = 6f;  // Trim fraction from ends
```

### Spawning Algorithm

**Targets (N×N grid):**
1. Compute grid layout in local space
2. Center at origin: `pitch = cellSize + gap`
3. For each (row, col):
   - Position: `topLeft + (col*pitch, 0, -row*pitch)`
   - Instantiate targetPrefab as child
   - Set world scale to targetWorldScale
   - Add/configure StatefulTarget component
   - Name: "Target_1" to "Target_N²"
4. Set layer to "BottomView" (or default)

**Walls (between tiles):**
1. For each horizontal gap (N-1 per row, N rows):
   - Create wall segment spanning cell width
   - Trim ends by `wallLengthInsetFrac`
   - Scale: (length, wallHeight, wallThickness)
   - Position between tiles
2. For each vertical gap (N-1 per col, N cols):
   - Create wall segment spanning cell height
   - Trim ends by `wallLengthInsetFrac`
   - Scale: (wallThickness, wallHeight, length)
   - Position between tiles
3. Add/configure StatefulWall component
4. Name: "Wall_A", "Wall_B", ... (letter labels)

### Interface Implementation

```csharp
public List<StatefulTarget> SpawnGrid()
{
    ClearAll();
    // ... create targets and walls ...
    return _targets;
}

// IEpisodeSpawner methods
public void ClearAll()
{
    // Destroy all children
    for (int i = transform.childCount - 1; i >= 0; i--)
        DestroyImmediate(transform.GetChild(i).gameObject);
    _targets.Clear();
    _walls.Clear();
}

public void SpawnAll() => SpawnGrid();

public int TargetsAlive()
{
    int count = 0;
    foreach (var t in _targets)
        if (t && t.gameObject.activeInHierarchy)
            count++;
    return count;
}

public GameObject GetPlayer() => null;  // No player spawned
```

### EnvParams: GridTargetsSpawnerEnvParams

**Supported Parameters:**

| Key Pattern | Type | Purpose |
|-------------|------|---------|
| `<prefix>.enabled` | bool | Enable/disable spawner |
| `<prefix>.grid_size` | int | N in N×N (2-5) |
| `<prefix>.cell_size` | float | Base cell size |
| `<prefix>.gap` | float | Extra spacing |
| `<prefix>.y_level` | float | Local Y position |
| `<prefix>.target_scale_x/y/z` | float | Target world scale |
| `<prefix>.wall_thickness` | float | Wall narrow dimension |
| `<prefix>.wall_height` | float | Wall height |
| `<prefix>.wall_length_inset_frac` | float | Wall trim fraction |


### Integration with SequenceTargetManager

```
SequenceTargetManager:
├── spawner: GridTargetsSpawner
└── score: EpisodeScore

// At StartEpisode():
_targets = spawner.SpawnGrid();      // Get all targets
_walls = spawner.Walls.ToList();     // Get all walls

// Build sequence from targets
_targetRun = BuildTargetSequence(...);  // Select subset in order

// Activate hazard walls
foreach (int wi in _hazardWalls)
    _walls[wi].GetComponent<StatefulWall>().SetActive();
```

---

## ScreenSpawnerFromObject

### Purpose

Spawns targets on a virtual wall surface (2D projection). Used for touchscreen-style tasks where the agent interacts with a flat surface.


### Components

```
GameObject (with OrthoScreenFromObject)
├── ScreenSpawnerFromObject (implementation)
├── ScreenSpawnerAdapter (IEpisodeSpawner)
└── ScreenSpawnerEnvParams (optional)
```

**Required:** `OrthoScreenFromObject` component (defines wall geometry)

### Configuration

#### Prefabs
```csharp
public GameObject playerPrefab;        // Tagged "Player"
public GameObject[] targetPrefabs;     // Array of target variants
```

#### Counts & Placement
```csharp
public int numTargets = 10;

[Range(0f, 1f)] public float minYFraction = 0f;  // 0=bottom
[Range(0f, 1f)] public float maxYFraction = 1f;  // 1=top

public float faceOffset = -0.1f;  // Offset from wall surface
```

#### Non-Overlap
```csharp
public int maxPlacementAttemptsPerTarget = 40;
public float separationPadding = 0.02f;  // Extra spacing (meters)
```

### Spawning Algorithm

**Player:**
1. Measure planar half-extents (2D bounding box on wall)
2. Sample random position fully inside screen bounds [minY, maxY]
3. Orient: `LookRotation(screen.DirUp, screen.DirNormal)`
4. Offset by `faceOffset` along normal
5. Attach to transform, assign layer
6. Configure `PlayerAgent3DOnScreen` with screen reference

**Targets (non-overlapping circles):**
1. For each target (i = 0 to numTargets-1):
   - Choose random prefab from `targetPrefabs[]`
   - Measure planar half-extents → radius
   - Attempt placement (max attempts):
     - Sample random position in [minY, maxY] band
     - Check no overlap with existing targets (circle test)
     - Check no overlap with player
     - If valid: Place and add to list
   - Orient: `LookRotation(screen.DirUp, screen.DirNormal)`
   - Offset by `faceOffset`
2. Ensure trigger colliders, "Target" tag
3. Optionally add `TargetKillOnPlayerDwell` component

### Adapter: ScreenSpawnerAdapter

```csharp
public class ScreenSpawnerAdapter : MonoBehaviour, IEpisodeSpawner
{
    public ScreenSpawnerFromObject spawner;

    public void ClearAll() => spawner?.ClearAll();
    public void SpawnAll() => spawner?.SpawnAll();

    public int TargetsAlive()
    {
        if (!spawner) return 0;
        int count = 0;
        foreach (var t in spawner.spawnedTargets)
            if (t && t.activeInHierarchy)
                count++;
        return count;
    }

    public GameObject GetPlayer() => spawner?.playerInstance;
}
```

### EnvParams: ScreenSpawnerEnvParams

**Supported Parameters:**

| Key Pattern | Type | Purpose |
|-------------|------|---------|
| `<prefix>.enabled` | bool | Enable/disable |
| `<prefix>.num_targets` | int | Target count |
| `<prefix>.face_offset` | float | Wall offset |
| `<prefix>.min_y_fraction` | float | Min Y (0-1) |
| `<prefix>.max_y_fraction` | float | Max Y (0-1) |
| `<prefix>.max_attempts_per_target` | int | Placement attempts |
| `<prefix>.separation_padding` | float | Extra spacing |


### Integration Example

```
Wall (GameObject with OrthoScreenFromObject)
├── ScreenSpawnerFromObject
├── ScreenSpawnerAdapter
└── ScreenSpawnerEnvParams

EpisodeManagerSingleWall:
└── spawnerComponents[0] → ScreenSpawnerAdapter
```

---

## SideTargetsSpawnerFromObject

### Purpose

Spawns target objects in floor area and target areas on side walls. Combines 3D floor navigation with wall-projected targets.

### Use Cases

- Multi-surface interaction tasks
- Combined floor + wall navigation
- Complex spatial tasks
- Mixed 2D/3D training

### Components

```
GameObject (with OrthoScreenFromObject)
├── SideTargetsSpawnerFromObject (implementation)
├── SideTargetsSpawnerAdapter (IEpisodeSpawner)
└── SideTargetsSpawnerEnvParams (optional)
```

### Configuration

#### Prefabs
```csharp
public GameObject playerPrefab;        // Player (floor)
public GameObject targetObjectPrefab;  // Target objects (floor)
public GameObject targetAreaPrefab;    // Target areas (walls)
```

#### Counts
```csharp
[Range(1, 4)] public int numTargetObjects = 1;  // Floor objects
[Range(1, 2)] public int numTargetAreas = 2;    // Wall areas (1=random side, 2=both)
```

#### Scaling
```csharp
public Vector3 areaScale = Vector3.one;        // Target area scale (X,Y,Z)
public Vector3 objectAreaScale = Vector3.one;  // Object scale (X,Y,Z)
```

#### Placement
```csharp
[Range(0f, 1f)] public float yFraction = 0.5f;  // Y level on wall
public float sideInset = 0.2f;                  // Border margin
public float areaSideoffset = 1f;               // Area inset from side
public float areaHeight = 0.5f;                 // Area height
public float faceOffset = -0.02f;               // Wall offset
```

#### Non-Overlap
```csharp
public int maxAttemptsPerTarget = 40;
public float separationPadding = 0.02f;
```

#### Destruction
```csharp
public float moveObjectMaxDistance = 0;  // Max travel distance (0=infinite)
```

### Spawning Algorithm

**Target Areas (left/right walls):**
1. Determine which sides:
   - `numTargetAreas=2`: Both left and right
   - `numTargetAreas=1`: Random side
2. For each side:
   - Position at `yFraction` height on wall
   - Inset from border by `areaSideoffset`
   - Scale: (areaScale.x, areaHeight, areaScale.z)
   - Orient flush with wall
   - Add trigger collider, "TargetArea" tag

**Player:**
1. Sample position at `yFraction` height, avoiding areas
2. Orient flush with wall
3. Configure `PlayerAgent3DOnScreen`

**Target Objects (floor, non-overlapping):**
1. For i = 0 to numTargetObjects-1:
   - Measure half-extents
   - Attempt placement:
     - Sample at `yFraction` height
     - Avoid player (circle overlap test)
     - Avoid existing objects
     - Keep away from side areas (`sideInset`)
   - Scale by `objectAreaScale`
   - Add `TargetKillOnArea` (destroyed on wall area collision)
   - Add `TargetKillOnDistance` (if maxDistance > 0)

### Adapter: SideTargetsSpawnerAdapter

```csharp
public class SideTargetsSpawnerAdapter : MonoBehaviour, IEpisodeSpawner
{
    public SideTargetsSpawnerFromObject spawner;

    public void ClearAll() => spawner?.ClearAll();
    public void SpawnAll() => spawner?.SpawnAll();

    public int TargetsAlive()
    {
        if (!spawner) return 0;
        int count = 0;
        foreach (var t in spawner.targetObjects)
            if (t && t.activeInHierarchy)
                count++;
        return count;
    }

    public GameObject GetPlayer() => spawner?.playerInstance;
}
```

**Success Condition:** All target objects destroyed (reach wall areas)

### EnvParams: SideTargetsSpawnerEnvParams

**Supported Parameters:**

| Key Pattern | Type | Purpose |
|-------------|------|---------|
| `<prefix>.enabled` | bool | Enable/disable |
| `<prefix>.num_target_objects` | int | Floor objects (1-4) |
| `<prefix>.num_target_areas` | int | Wall areas (1-2) |
| `<prefix>.area_scale_x/y/z` | float | Area scale |
| `<prefix>.object_scale_x/y/z` | float | Object scale |
| `<prefix>.y_fraction` | float | Y level (0-1) |
| `<prefix>.side_inset` | float | Border margin |
| `<prefix>.area_sideoffset` | float | Area inset |
| `<prefix>.area_height` | float | Area height |
| `<prefix>.face_offset` | float | Wall offset |
| `<prefix>.max_attempts` | int | Placement attempts |
| `<prefix>.separation_padding` | float | Extra spacing |
| `<prefix>.move_object_max_distance` | float | Max travel |

---

## See Also

- **[Architecture Overview](Architecture.md)** - System design
- **[Episode Management](EpisodeManagement.md)** - Manager lifecycle
- **[Parameter System](ParameterSystem.md)** - Env params and KV control
- **[Agent System](Agents.md)** - TTL observations and phase flags
