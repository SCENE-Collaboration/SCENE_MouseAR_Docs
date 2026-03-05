# Python GUIs - User Guide

## Overview

The **mice_ar_tasks** package includes three GUI workflows to simplify experiment setup, hardware calibration, runtime control, and data transfer:

1. **UnityTaskGUI** - Configure and run Unity-based behavioral experiments with live monitoring
2. **TeensyControlGUI** - Hardware control, testing, and water delivery calibration
3. **Data Transfer GUI** - Session metadata entry, file attachment, and transfer to local/remote storage

These GUIs provide visual interfaces for workflows that would otherwise require command-line configuration and Python scripting.

---

## Table of Contents

- UnityTaskGUI
  - Features
  - Launch Instructions
  - Workflow
  - Interface Components
  - Profile System
  - Parameter Editing
  - Live Monitoring
  - Data Saving
  - Troubleshooting
- TeensyControlGUI
  - Features
  - Launch Instructions
  - Workflow
  - Connection Tab
  - WaterPort Tab
  - Calibration Procedure
  - Troubleshooting
- Data Transfer GUI
  - Features
  - Launch Instructions
  - Dataset-Based Auto Discovery
  - Remote Transfer Behavior
- Common Issues

---

## UnityTaskGUI

### UnityTaskGUI Features

The **UnityTaskGUI** (`unity_task_gui.py`) provides a complete interface for running Unity ML-Agents experiments with integrated hardware control:

✅ **Config Management**
- Load and validate `*.game.toml` configuration files
- Switch between profiles (e.g., Training, Testing, RL) with one click
- Auto-populate parameters from config files
- Override default values with profile-specific settings

✅ **Hardware Integration**
- Automatic serial port detection for Teensy microcontroller
- Support for "dummy" mode (no hardware required)
- Real-time Teensy communication status

✅ **Parameter Control**
- Edit Unity environment parameters (`env_params`) in real-time
- Modify key-value parameters (`env_kv_params`) during experiments
- Visual indicators show modified values (red) and profile overrides (blue)
- Send parameter updates to running Unity environment
- Reset to original file values with one click

✅ **Mouse Metadata**
- Record subject name and weight
- Auto-saved with experimental data

✅ **Live Monitoring**
- Real-time epoch/episode/step counters
- Reward tracking (per-trial and cumulative)
- Session duration timer
- Automatic data logging

✅ **Config Inspection**
- Read-only tabs for all config sections (game, teensy, dlc, touchscreen, etc.)
- Hierarchical display of nested configuration

---

### Launching UnityTaskGUI

**From command line:**

```bash
cd /path/to/mice_ar_tasks
python -m mouse_ar.gui.unity_task_gui
```

**From Python:**

```python
from mouse_ar.gui.unity_task_gui import main
main()
```

**Requirements:**
- PyQt6 (`pip install PyQt6`)
- All `mouse_ar` dependencies

---

### UnityTaskGUI Workflow

```
┌─────────────────────────────────────────────────────────────┐
│ 1. SETUP                                                    │
│    • Enter mouse name and weight (optional)                 │
│    • Select serial port for Teensy (or "dummy")             │
│    • Browse to *.game.toml config file                      │
│    • Click "Load Config"                                    │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. CONFIGURE (Optional)                                     │
│    • Select a profile (e.g., "Training", "RL")              │
│    • Edit parameters in the Parameters tab                  │
│    • Inspect config sections (game, teensy, dlc, etc.)      │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. RUN                                                      │
│    • Click "Start" to begin experiment                      │
│    • Monitor live statistics on Config & Status tab         │
│    • Adjust parameters during run (Parameters tab)          │
│    • Click "Send params (diff-only)" to apply changes       │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. STOP & SAVE                                              │
│    • Click "Stop" when complete                             │
│    • Data automatically saved as JSON                       │
│    • Click "Reset" to start new session                     │
└─────────────────────────────────────────────────────────────┘
```

---

### UnityTaskGUI Interface

#### **Config & Status Tab**

*Unity Task GUI main tab screenshot (image not bundled in this docs build).*

**Top Section - Experiment Setup:**

| Field | Description |
|-------|-------------|
| **Mouse Name** | Subject identifier (saved in JSON output) |
| **Weight (g)** | Subject weight in grams (saved in JSON output) |
| **Config** | Path to `*.game.toml` file |
| **Browse…** | File picker for config files (starts in `mouse_ar/tasks/configs/`) |
| **Profile** | Dropdown to select config profile (e.g., Training, Testing, RL) |
| **Serial Port** | Teensy USB port or "dummy" for testing |
| **Refresh** | Re-scan for available serial ports |

**Action Buttons:**

| Button | Function | Enabled When |
|--------|----------|--------------|
| **Load Config** | Parse config file and populate parameters | Config path valid |
| **Start** | Initialize Unity environment and begin experiment | Config loaded |
| **Stop** | End experiment and save data | Experiment running |
| **Reset** | Clear session and enable new experiment | After stop completes |

**Status Display:**

| Indicator | Shows |
|-----------|-------|
| **Epoch** | Current epoch number |
| **Episode** | Current episode within epoch |
| **Step** | Step count within current episode |
| **Last trial reward** | Reward received in most recent completed episode |
| **Total Rewards** | Cumulative reward across all episodes |
| **Duration** | Session runtime (HH:MM:SS) |

---

#### **Parameters Tab**

*Unity Task GUI parameters tab screenshot (image not bundled in this docs build).*

This tab displays all configurable parameters loaded from the TOML file:

**KV Params (String Parameters):**
- Displayed in two columns for better visibility
- Used for categorical settings, file paths, behavior names
- Examples: `game.difficulty_level`, `dlc.model_path`, `task.reward_type`

**Env Params (Float Parameters):**
- Single column display
- Numeric parameters for Unity environment
- Examples: `spawn_radius`, `target_distance`, `reward_magnitude`

**Color Coding:**

| Color | Meaning |
|-------|---------|
| **Black** | Value matches file (no modifications) |
| **Blue** | Profile override (differs from default profile) |
| **Red** | User modified (differs from original file value) |

**Parameter Actions:**

| Button | Function |
|--------|----------|
| **Reset to file values** | Restore all parameters to original file values |
| **Send params (diff-only)** | Send only changed parameters to running Unity environment |

**Usage Example:**

1. Start experiment with default parameters
2. Switch to Parameters tab
3. Modify `difficulty_level` from "0.5" to "0.8" (turns red)
4. Click "Send params (diff-only)"
5. Unity receives update without restarting

---

#### **Config Detail Tabs**

Read-only tabs display full configuration sections for reference:

- **Game** - Unity environment settings, build path, display config
- **Teensy** - Hardware serial port, baudrate, I/O pin mappings
- **DLC** - DeepLabCut server settings, filtering parameters
- **Touchscreen** - Touch input configuration
- **Touch** - Touch behavior parameters
- *(Additional tabs based on config file)*

These tabs help verify loaded settings without editing risks.

---

### Profile System

Profiles allow multiple parameter sets in one config file:

**Example `hockey.game.toml`:**

```toml
[meta]
name = "Hockey Task"

# Default profile
[game]
difficulty = 0.5
time_limit = 300.0

# Training profile (easy)
[profile.Training]
description = "Easy settings for initial training"

[profile.Training.game]
difficulty = 0.3
time_limit = 600.0

# RL profile (fast)
[profile.RL]
description = "Fast execution for reinforcement learning"

[profile.RL.game]
difficulty = 0.7
time_limit = 60.0
time_scale = 20.0
```

**Using Profiles in GUI:**

1. Load config file (loads default profile)
2. Select "Training" from Profile dropdown
   - Parameters tab shows `difficulty = 0.3` (blue if differs from default)
   - Description shown in status bar
3. Select "RL" from Profile dropdown
   - Parameters update to RL values
   - All tabs refresh with new settings

**Profile Parameter Color:**
- Blue text indicates "this value differs from default profile"
- Helps identify which parameters a profile modifies

---

### Parameter Editing

**Real-Time Parameter Updates:**

The GUI supports runtime parameter modification via Unity ML-Agents' `EnvironmentParametersChannel` and `KvChannel`:

**Process:**

```text
# 1. User edits parameter in GUI
difficulty: "0.5" → "0.8"  # Field turns red

# 2. User clicks "Send params (diff-only)"
# GUI calls: worker.enqueue_set_param("difficulty", "0.8")

# 3. Worker thread sends to Unity
task.set_runtime_param("difficulty", "0.8")

# 4. Unity C# receives update
float newDifficulty = float.Parse(
    Academy.Instance.EnvironmentParameters.GetWithDefault("difficulty", 0.5f)
);
```

**Best Practices:**

✅ **DO:**
- Edit parameters between episodes (during reset)
- Send small batches of related parameters
- Verify Unity logs parameter reception

❌ **DON'T:**
- Modify parameters mid-episode (behavior undefined)
- Send too many parameters at once (check Unity processing)
- Change behavior-critical parameters without testing

---

### Live Monitoring

**Status Updates:**

The GUI worker thread runs at ~5 Hz, updating displays with:

```python
# From UnityWorker.run():
info = self.task.get_info()
{
    "epoch": 0,
    "episode": 12,
    "step": 145,
    "last_reward": 1.0,
    "total_rewards": 8.0,
    "behavior_info": {...}
}
```

**Refresh Rate:**
- Status display: 5 Hz (200ms interval)
- Duration timer: 1 Hz (1s interval)
- Responsive to user interactions (non-blocking)

**Performance:**
- Minimal CPU overhead (~1-2%)
- Non-blocking worker thread
- Safe shutdown handling

---

### Data Saving

**Automatic Save on Stop:**

When you click **Stop**, the GUI automatically:

1. Signals worker thread to stop
2. Calls `task.stop()` to clean up Unity environment
3. Saves all logged data to JSON file
4. Enables **Reset** button

**Output File:**

```bash
# Format: UnityData_{MouseName}_{Timestamp}.json
UnityData_MusterMaus_20250930_101812.json
```

**Saved Data Structure:**

```text
{
  "params": {
    "subject_id": "MusterMaus",
    "mouse_weight_g": 25.5,
    "env_path": "Build/Hockey.exe",
    "config_file": "/path/to/hockey.game.toml",
    "profile": "Training",
    ...
  },

  "episode": [0, 0, 0, 1, 1, ...],
  "step": [0, 1, 2, 0, 1, ...],
  "step_time": [0.0, 0.016, 0.032, ...],

  "state": [{...}, {...}, ...],
  "action": [{...}, {...}, ...],
  "reward": [0.0, 0.0, 1.0, ...],

  "dlc_x": [0.5, 0.51, ...],
  "teensy_input_analog": [512, 515, ...],
  "runtime_params": [...],
  "kv_messages": [...]
}
```

See [Data Logging](Overview.md) for complete structure.

---

### UnityTaskGUI Troubleshooting

#### **"Failed to load config" error**

**Symptom:** Red error dialog after clicking "Load Config"

**Causes:**
1. Invalid TOML syntax
2. Missing required sections (`[game]`, `[unity]`)
3. Type mismatches (string vs float)

**Solution:**
```bash
# Validate TOML syntax
python -c "import tomli; tomli.load(open('path/to/config.toml', 'rb'))"

# Check required sections
grep -E '^\[game\]|\[unity\]' path/to/config.toml
```

---

#### **"Unity environment failed to start" error**

**Symptom:** Error dialog after clicking "Start"

**Causes:**
1. Unity build path incorrect
2. Port 5004 already in use
3. Missing Unity ML-Agents DLL

**Solution:**
```bash
# Check build exists
ls -lh Build/Hockey.x86_64  # Linux
ls -lh Build/Hockey.exe     # Windows

# Check port availability
lsof -i :5004  # Should be empty

# Test Unity build manually
./Build/Hockey.x86_64 --help
```

---

#### **Parameters not updating in Unity**

**Symptom:** Changed parameters don't affect Unity behavior

**Causes:**
1. Parameters sent mid-episode
2. Unity C# not reading from `EnvironmentParameters`
3. Parameter name mismatch

**Solution:**

**Python side:**
```python
# Verify parameter sent
task.set_runtime_param("difficulty", "0.8")
print(task.runtime_params)  # Should show update
```

**Unity C# side:**
```csharp
// In Agent.OnEpisodeBegin():
float difficulty = Academy.Instance.EnvironmentParameters
    .GetWithDefault("difficulty", 0.5f);
Debug.Log($"Received difficulty: {difficulty}");
```

---

#### **Serial port not detected**

**Symptom:** Dropdown shows only "dummy"

**Causes:**
1. Teensy not connected
2. USB permissions (Linux)
3. `pyserial` not installed

**Solution:**
```bash
# Check USB devices
lsusb | grep -i teensy

# Fix permissions (Linux)
sudo usermod -a -G dialout $USER
# Log out and back in

# Install pyserial
pip install pyserial
```

---

#### **GUI freezes when starting experiment**

**Symptom:** Window becomes unresponsive after "Start"

**Causes:**
1. Unity environment hangs during initialization
2. Worker thread exception
3. Teensy serial timeout

**Solution:**
```bash
# Check terminal for exceptions
python -m mouse_ar.gui.unity_task_gui

# Test Unity build separately
python -c "
from mouse_ar.tasks.unity_multibehavior_task import UnityMultibehaviorTask
task = UnityMultibehaviorTask(env='Build/Hockey.x86_64')
task.start()  # Should complete in <5s
task.stop()
"

# Test Teensy separately
python -m mouse_ar.gui.teensy_control_gui
```

---

## TeensyControlGUI

### TeensyControlGUI Features

The **TeensyControlGUI** (`teensy_control_gui.py`) provides hardware testing and calibration tools:

✅ **Teensy Control**
- Load configuration from `*.hw.toml` files
- Connect to Teensy via USB serial or dummy mode
- Start/stop real-time data reading
- Monitor incoming sensor data and TTL signals

✅ **Water Delivery**
- Manual water pulse control (ms precision)
- Drain mode toggle (continuous valve opening)
- Instant pulse testing

✅ **Calibration System**
- Multi-point calibration table
- Non-blocking calibration workflow (measure, record, next)
- Linear regression analysis with R² quality metric
- Predictive opening time calculator
- JSON export of calibration data

✅ **Live Monitoring**
- Real-time TTL signal display
- Incoming data rate tracking
- Configurable TTL source selection

---

### Launching TeensyControlGUI

**From command line:**

```bash
cd /path/to/mice_ar_tasks
python -m mouse_ar.gui.teensy_control_gui
```

**From Python:**

```python
from mouse_ar.gui.teensy_control_gui import main
main()
```

**Requirements:**
- PyQt6
- `pyserial` (for real hardware)
- Teensy microcontroller (or use "dummy" mode)

---

### TeensyControlGUI Workflow

```
┌─────────────────────────────────────────────────────────────┐
│ 1. SETUP                                                    │
│    • Load teensy.hw.toml config file                        │
│    • Select serial port (or "dummy" for testing)            │
│    • Click "Connect"                                        │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. TEST (Optional)                                          │
│    • Click "Start Reading" to monitor sensors               │
│    • Check TTL signal display                               │
│    • Test water pulse with manual duration                  │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. CALIBRATE                                                │
│    • Switch to WaterPort tab                                │
│    • Add calibration points (opening times)                 │
│    • Click "Run All" to start calibration                   │
│    • For each step:                                         │
│      - Water pulse delivered                                │
│      - Weigh collected water                                │
│      - Enter weight (mg) in table                           │
│      - Click "Next Step"                                    │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. SAVE                                                     │
│    • Click "Finish & Save JSON"                             │
│    • Review regression R² value                             │
│    • Use predicted opening time for desired water volume    │
└─────────────────────────────────────────────────────────────┘
```

---

### Connection Tab

*Teensy Control GUI connection tab screenshot (image not bundled in this docs build).*

**Configuration Loading:**

| Field | Description |
|-------|-------------|
| **Teensy config** | Path to `*.hw.toml` file with hardware settings |
| **Load Teensy Config** | Parse config and populate serial settings |

**Example `teensy.hw.toml`:**

```toml
[teensy]
serial_port = "/dev/ttyACM0"  # Auto-selected in GUI
baudrate = 115200
csv_expected = 5  # Number of comma-separated values

inputs = ["analog_0", "analog_1", "digital_0", "ttl_in", "sync"]

[teensy.outputs]
start = {command = "A"}
stop = {command = "Z"}
water = {command = "W", params = ["dur_ms"]}
TTL = {command = "S"}
sync = {command = "X"}
drain = {command = "D"}
```

**Serial Port Selection:**

| Control | Function |
|---------|----------|
| **Port dropdown** | Lists `ttyUSB*`, `ttyACM*`, `COM*`, and "dummy" |
| **Refresh** | Re-scan for connected devices |
| **Baud** | Serial baudrate (default: 115200) |
| **CSV fields** | Expected number of comma-separated input values |
| **Timeout (s)** | Serial read timeout |

**Connection Controls:**

| Button | Function | State |
|--------|----------|-------|
| **Connect** | Open serial connection to Teensy | Enabled when disconnected |
| **Disconnect** | Close serial connection | Enabled when connected |
| **Start Reading** | Begin polling Teensy inputs | Enabled when connected |
| **Stop Reading** | Stop polling inputs | Enabled when reading |

**Status Display:**

| Indicator | Shows |
|-----------|-------|
| **Status** | Connection state (connected/disconnected/reading) |
| **Incoming** | Data rate (+N per update, total count) |
| **TTL src** | Dropdown to select which input column to display |
| **TTL** | Current value of selected TTL input |

---

### WaterPort Tab

*Teensy Control GUI waterport tab screenshot (image not bundled in this docs build).*

**Water Control:**

| Control | Function |
|---------|----------|
| **Drain toggle** | Toggle continuous valve opening (green=ON, red=OFF) |
| **Duration (ms)** | Pulse duration for manual water delivery |
| **Send pulse** | Deliver single water pulse |

**Calibration Table:**

| Column | Description |
|--------|-------------|
| **Opening time (ms)** | Valve opening duration |
| **Measured weight (mg)** | Water weight collected (fill after delivery) |

**Table Actions:**

| Button | Function |
|--------|----------|
| **Add row** | Insert new calibration point (default 100ms) |
| **Delete selected** | Remove selected rows |
| **Run selected step** | Deliver water for selected row only |
| **Run All** | Start non-blocking calibration workflow |
| **Next Step** | Deliver next calibration point (after weighing previous) |
| **Finish & Save JSON** | Calculate regression and export calibration |

**Prediction:**

| Field | Description |
|-------|-------------|
| **Desired water (mg)** | Target water volume |
| **Predicted open time** | Calculated opening duration (after calibration) |

---

### Calibration Procedure

**Step-by-Step:**

#### **1. Prepare Calibration Points**

```
Click "Add row" multiple times to create test points:
┌──────────────┬────────────────┐
│ Opening (ms) │ Weight (mg)    │
├──────────────┼────────────────┤
│ 50           │                │
│ 100          │                │
│ 150          │                │
│ 200          │                │
│ 250          │                │
└──────────────┴────────────────┘
```

**Recommended points:** 5-10 values spanning expected range

---

#### **2. Start Calibration Workflow**

1. Place collection container under water port
2. Ensure scale is ready (0.001g precision recommended)
3. Click **"Run All"**
4. Status bar shows: "Calibration mode: press Next Step after weighing."

---

#### **3. Measure Each Point**

**For each calibration point:**

```
Loop:
1. Water pulse delivered (e.g., 50ms)
2. Remove container and weigh water
3. Enter measured weight in table
   ┌──────────────┬────────────────┐
   │ Opening (ms) │ Weight (mg)    │
   ├──────────────┼────────────────┤
   │ 50           │ 12.3          │  ← Enter here
   │ 100          │               │
   └──────────────┴────────────────┘
4. Click "Next Step"
5. Repeat for next point
```

**Tips:**
- Wipe container between measurements
- Tare scale before each measurement
- Wait for water to fully drain before weighing

---

#### **4. Finish and Save**

1. Click **"Finish & Save JSON"**
2. GUI computes linear regression:
   ```
   weight (mg) = slope × opening_time (ms) + intercept
   R² = quality metric (0.0-1.0)
   ```
3. Success dialog shows:
   - Number of calibration points
   - R² value (>0.95 is excellent)
   - Predicted opening time for desired water volume
4. JSON file saved: `water_calib_YYYYMMDD_HHMMSS.json`

---

**Example Calibration Output:**

```json
{
  "timestamp": 1696089123.456,
  "points": [
    {"open_ms": 50, "weight_g": 0.0123},
    {"open_ms": 100, "weight_g": 0.0254},
    {"open_ms": 150, "weight_g": 0.0381},
    {"open_ms": 200, "weight_g": 0.0508},
    {"open_ms": 250, "weight_g": 0.0635}
  ],
  "regression": {
    "slope": 0.000254,
    "intercept": 0.00005,
    "r_squared": 0.9987,
    "n_points": 5
  },
  "desired_mg": 10.0,
  "predicted_ms": 39
}
```

**Using Calibration Results:**

```python
# In your task configuration:
# To deliver 10mg water:
teensy.give_reward(39)  # Use predicted_ms from calibration
```

---

### TeensyControlGUI Troubleshooting

#### **Serial port permission denied (Linux)**

**Symptom:** "Permission denied" when connecting to `/dev/ttyACM0`

**Solution:**
```bash
# Add user to dialout group
sudo usermod -a -G dialout $USER

# Log out and back in, then verify
groups | grep dialout

# Alternative: temporary permission
sudo chmod 666 /dev/ttyACM0
```

---

#### **No data in "Incoming" display**

**Symptom:** "Incoming: +0 (total 0)" after "Start Reading"

**Causes:**
1. Teensy not sending data
2. Wrong CSV field count
3. Baudrate mismatch

**Solution:**

**Test serial manually:**
```bash
# Install screen
sudo apt install screen

# Connect to Teensy
screen /dev/ttyACM0 115200

# Type 'A' to start, should see CSV output:
512,513,0,1,12345
513,514,0,1,12346
...

# Exit: Ctrl+A, then K
```

**Adjust CSV field count:**
```
If you see 6 values but GUI expects 5:
- Increase "CSV fields" spinbox to 6
- Disconnect and reconnect
```

---

#### **"Degenerate data for regression" error**

**Symptom:** Error when clicking "Finish & Save JSON"

**Causes:**
1. All calibration points have same opening time
2. Fewer than 2 measured points
3. All weights are identical

**Solution:**
- Ensure at least 2 rows have both opening time AND measured weight
- Use different opening times for each point
- Verify weights are measured (not 0.0 for all)

---

#### **R² value very low (<0.90)**

**Symptom:** Calibration succeeds but R² < 0.90

**Causes:**
1. Inconsistent water delivery (valve issue)
2. Measurement errors (scale precision)
3. Evaporation between delivery and weighing

**Solution:**
- Check valve operation (listen for clicking sound)
- Use higher precision scale (±0.001g minimum)
- Measure quickly after delivery
- Increase number of calibration points (10+ recommended)
- Repeat outlier measurements

---

#### **Water not delivered during calibration**

**Symptom:** No water appears when "Next Step" clicked

**Causes:**
1. Solenoid valve not connected
2. Wrong Teensy output pin
3. Insufficient power to valve

**Solution:**

**Test valve directly:**
```python
from mouse_ar.ctrl.teensy_python import Teensy

teensy = Teensy(port="/dev/ttyACM0")
teensy.connect()
teensy.start()
teensy.give_reward(100)  # Should hear click and see water
teensy.stop()
teensy.disconnect()
```

**Check wiring:**
- Teensy GPIO → MOSFET gate
- MOSFET drain → Solenoid negative
- Solenoid positive → 12V power supply
- MOSFET source → Ground

---

## Data Transfer GUI

### Data Transfer GUI Features

The Data Transfer GUI (`dj_pipeline/gui_transfer`) supports end-of-session handoff:

- session metadata from DataJoint dropdown menus,
- file attachment for Unity/DLC/video artifacts,
- local or remote transfer,
- optional video metadata-only export.

Recent capabilities include dataset-based prefill and dataset-based file auto-discovery.

### Launching Data Transfer GUI

```bash
python dj_pipeline/gui_transfer/main.py
```

With optional context prefill:

```bash
python dj_pipeline/gui_transfer/main.py \
  --mouse-name TestMouse \
  --dataset-id TestMouse_20260116_144944 \
  --deltaweight 7.5 \
  --task AR_visual_discrimination \
  --opto none
```

### Dataset-Based Auto Discovery

If `dataset_name` or `dataset_id` is passed, the transfer panel searches each datatype folder for matching files:

- Unity JSON
- DLC pkl/pickle
- DLC hdf5/h5
- videos

If only a subset is found, the GUI warns and lists missing categories.

### Remote Transfer Behavior

- `ip == "localhost"` → local copy
- non-localhost IP → `scp` to `host@ip:<remote_dst>/<datatype_subfolder>`

For full setup and key-by-key configuration, see [DataTransferGUI.md](DataTransferGUI.md).

## Common Issues

### **PyQt6 import error**

**Symptom:** `ModuleNotFoundError: No module named 'PyQt6'`

**Solution:**
```bash
pip install PyQt6
```

---

### **Config file not found**

**Symptom:** Browse dialog opens in wrong directory

**Solution:**

**Set explicit path in code:**
```python
# In unity_task_gui.py, line ~450:
path, _ = QFileDialog.getOpenFileName(
    self, "Select *.game.toml",
    "/absolute/path/to/mice_ar_tasks/mouse_ar/tasks/configs",  # Absolute path
    "Game TOML (*.game.toml)"
)
```

---

### **GUI window too large for screen**

**Symptom:** GUI extends beyond screen edges

**Solution:**

**Resize window:**
```python
# In __init__ methods:
self.resize(800, 600)  # Reduce from 1100x800
```

**Enable scrolling:**
- All tabs use `QScrollArea` for long content
- Mouse wheel scrolls parameter lists

---

### **"UnityCommunicatorStoppedException" during run**

**Symptom:** Experiment stops unexpectedly with communicator exception

**Causes:**
1. Unity build crashed
2. Manual Unity window close
3. Network timeout

**Solution:**
- Check Unity build logs: `~/.config/unity3d/<Company>/<Product>/Player.log`
- Verify `timeout_wait=60` in `UnityEnvironment()` call
- Test Unity build stability before long experiments

---

## Advanced Usage

### **Custom GUI Extensions**

Both GUIs are designed for extension:

**Add custom control to UnityTaskGUI:**

```python
# In _build_config_tab():
custom_row = QHBoxLayout()
self.custom_button = QPushButton("Custom Action")
self.custom_button.clicked.connect(self.on_custom_action)
custom_row.addWidget(self.custom_button)
lay.addLayout(custom_row)

def on_custom_action(self):
    if self.task is not None:
        # Call custom task method
        self.task.custom_method()
```

**Add custom tab to TeensyControlGUI:**

```python
# In __init__():
self._build_tab_custom()

def _build_tab_custom(self):
    w = QWidget()
    self.tabs.addTab(w, "Custom")
    lay = QVBoxLayout(w)
    # Add custom widgets...
```

---

### **Automation**

**Launch GUI with pre-loaded config:**

```python
import sys
from PyQt6.QtWidgets import QApplication
from mouse_ar.gui.unity_task_gui import MainWindow

app = QApplication(sys.argv)
window = MainWindow()

# Auto-load config
window.config_path_edit.setText("/path/to/hockey.game.toml")
window.on_load_config()

# Auto-select profile
window.profile_combo.setCurrentText("Training")

window.show()
sys.exit(app.exec())
```

---

## Related Documentation

- [Overview](Overview.md) - System architecture and workflow
- [Tasks](Tasks.md) - UnityAgentTask and UnityMultibehaviorTask details
- [Teensy](Teensy.md) - Hardware control and serial protocol
- [Config System](ConfigSystem.md) - TOML configuration structure

---

**Version:** 1.0 (November 2025)
