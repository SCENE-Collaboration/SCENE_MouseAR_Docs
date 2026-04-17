# Populating the Pipeline

## Prerequisites

Before running any population script:

1. **Database credentials** — ensure `dj_pipeline/datajoint.json` contains valid credentials (see [Connections](Connections.md))
2. **Environment variables** — `RAW_DATA_PATH`, `VIDEO_PATH`, `DLC_DATA_PATH` must point to the correct data directories (see [Connections](Connections.md))
3. **base_schemas sessions** — `SessionDataset` links datasets to sessions in `base_schemas.exp.Session`. Sessions for the relevant mice and dates must already exist there before `SessionDataset.populate()` will succeed
4. **DLC models** — for `DlcLiveData.populate()`, at least one `DlcModel` entry must exist. See [Manual Population](#manual-population) below

---

## Standard Population

Run `dj_pipeline/populate.py` to populate all tables in dependency order:

```bash
cd dj_pipeline
python populate.py
```

This executes the following steps:

### Step 1 — Register datasets

```python
Dataset.populate_from_files()
```

Scans `RAW_DATA_PATH` for `UnityData_*.json` files and creates a `Dataset` entry for each new session found. Parses the `dataset_id` from the filename (format: `<subject>_<YYYYMMDD>_<HHMMSS>`).

### Step 2 — Link to sessions

```python
SessionDataset.populate(suppress_errors=True, reserve_jobs=True)
```

For each `Dataset`, finds the matching `base_schemas.exp.Session` by matching mouse name and date, then assigning by position (first dataset of the day → first session attempt of that day, etc.).

### Step 3 — Import behavioral data

```python
UnitySession.populate(suppress_errors=True, reserve_jobs=True)
```

Reads the `UnityData_<dataset_id>.json` file and populates the master table and all part tables:
`UnityData`, `UnityAgentBehavior`, `DlcData`, `TouchData`, `ScreenTTLData`, `TeensyData`, `UnityMessage`, `UnityRuntimeParams`.

### Step 4 — Extract trial info

```python
TrialInfo.populate(suppress_errors=True, reserve_jobs=True)
```

Computes trial boundaries from episode/step/reward arrays in `UnitySession`. Uses TTLInput observations to identify ITI and initiation periods.

### Step 5 — Import video metadata

```python
VideoRecording.populate(suppress_errors=True, reserve_jobs=True)
```

Finds `UnityData_<dataset_id>*.mp4` files in `VIDEO_PATH`, reads frame count / resolution / duration via OpenCV, and optionally imports `*_timestamps.json` for precise frame timestamps.

### Step 6 — Compute TTL sync quality

```python
ScreenSync.populate(suppress_errors=True, reserve_jobs=True)
```

Decodes the lux sensor (BH1750) recordings from `TeensyData` to detect TTL barcode bursts and computes synchronization statistics against the sent TTL counters.

### Step 7 — Import DLC pose data

```python
DlcLiveData.populate(suppress_errors=True, reserve_jobs=True)
```

Reads `*_dlcproc.pkl` (processor data) and `*_dlcproc_DLC.hdf5` (raw pose) files from `DLC_DATA_PATH`. Automatically matches or creates a `DlcModel` entry based on bodyparts and network type.

### Step 8 — Synchronize video and behavior

```python
SynchronizedVideo.populate(suppress_errors=True, reserve_jobs=True)
```

Maps each game step timestamp to the nearest video frame index using binary search on `FrameTimestamps`.

### Step 9 — Sync DLC to video frame grid

```python
SyncedDlcLiveData.populate(suppress_errors=True, reserve_jobs=True)
```

Remaps all DLC pose arrays from the DLC processing frame grid to the full video frame grid using nearest-neighbour matching and linear interpolation for missing frames.

---

## Automated Population (Cron)

The pipeline can run automatically on a schedule using the cron script:

```bash
# Add a cron job (from within the Docker container)
cd dj_pipeline
make add-cron
```

This installs `cron_script.sh` as a cron job that:
1. Sets the required environment variables
2. Calls `python populate.py`
3. Calls `python post_populate.py` (sends summary email)

---

## Manual Population

### Inserting DLC Models

When a new DLC model file is available, insert it before running `DlcLiveData.populate()`:

```python
from dj_pipeline.schemas.mousear_dlc_live import DlcModel

model_id = DlcModel.insert_dlc_live_model_from_file(
    model_file="/path/to/model.pt",
    description="ResNet50 model trained on lab mice, 12 keypoints",
    model_name="mice_resnet50_v1",   # optional, defaults to filename
)
print(f"Inserted model with ID: {model_id}")
```

### Assigning Models to Legacy Data

For sessions that pre-date automatic model detection, use `manual_populate.py`:

```bash
cd dj_pipeline
python manual_populate.py
```

This applies heuristics based on video frame rate to assign the correct `model_id`:
- Frame rate < 40 fps → `model_id = 1`
- Frame rate > 40 fps (before 2026-02-04) → `model_id = 2`

### Manually Linking a Dataset to a Session

If the automatic positional matching in `SessionDataset.populate()` fails (e.g., mismatched session count), you can register manually:

```python
from dj_pipeline.schemas.mousear_dataset import SessionDataset

SessionDataset.register_dataset(
    session_key={"mouse_name": "Tick", "doe": "2026-02-10", "attempt": 1},
    dataset_key={"dataset_id": "Tick_20260210_141820"},
)
```

---

## Checking Population Status

```python
import datajoint as dj
from dj_pipeline.schemas.mousear_behavior import UnitySession, TrialInfo
from dj_pipeline.schemas.mousear_video import VideoRecording, SynchronizedVideo
from dj_pipeline.schemas.mousear_dlc_live import DlcLiveData, SyncedDlcLiveData
from dj_pipeline.schemas.mousear_screen_sync import ScreenSync

# Count populated entries
print(f"Sessions:          {len(UnitySession)}")
print(f"Trials:            {len(TrialInfo)}")
print(f"Videos:            {len(VideoRecording)}")
print(f"SyncedVideos:      {len(SynchronizedVideo)}")
print(f"ScreenSync:        {len(ScreenSync)}")
print(f"DlcLiveData:       {len(DlcLiveData)}")
print(f"SyncedDlcLiveData: {len(SyncedDlcLiveData)}")

# Check error jobs
UnitySession.progress()
```
