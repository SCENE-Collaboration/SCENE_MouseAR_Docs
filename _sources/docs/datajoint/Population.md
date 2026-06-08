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

Reads `*_dlcproc.pkl` (processor data) and `*_dlcproc_DLC.hdf5` (raw pose) files from `DLC_DATA_PATH`. It tries to match an existing `DlcModel` entry using metadata from the processor file.

In the current implementation, that matching uses `bodyparts` and `net_type` from the processor pickle. The code also compares the `detector` field, but the processor-metadata helper does not currently populate a detector value, so detector-aware matching is not available from this path yet.

Recommended workflow: insert each DLC model into `DlcModel` manually before running `DlcLiveData.populate()`. This keeps `model_id` values stable and makes it obvious which trained model produced each session. If no matching model exists, population raises an error by default rather than silently creating one.

Only use `make_kwargs={"init_from_file": True}` when you intentionally want the pipeline to create a fallback model entry from processor metadata, for example while backfilling older sessions.

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

The pipeline can run automatically via a cron job that wraps
`dj_pipeline/cron_script.sh`. The script:

1. `cd`s into `$DJ_PIPELINE_DIR` (read from the cron command env var).
2. Runs `docker compose up -d client` (no-op if already running).
3. Inside the container, runs `populate_base` (from `base_schemas`) against
   `$RAW_DATA_PATH/mice_metadata`.
4. Inside the container, runs `python populate.py`, which also calls
   `post_populate.py` and sends the summary email (see
   [Schema_SummaryEmail § Email Delivery](Schema_SummaryEmail.md#email-delivery)).

### Install the cron job (one-time, on the server)

Must be run on the **host**, not inside the Docker container — cron lives on
the host and the cron command itself talks to the host docker daemon.

```bash
ssh leonardo@mathis-server2
cd /mnt/md0/mouse_hockey/code/SCENE_MouseAR/dj_pipeline

# install the cron entry
make add-cron
```

`make add-cron` reads `DJ_PIPELINE_DIR` from `.env`, errors out clearly if
unset, creates `$DJ_PIPELINE_DIR/logs/`, and writes a crontab line:

```cron
0 2 * * * DJ_PIPELINE_DIR=/mnt/md0/.../dj_pipeline bash /mnt/md0/.../cron_script.sh >> /mnt/md0/.../logs/cron.log 2>&1
```

Schedule: **2 AM local time, daily.** To change the time, edit the `0 2 * * *`
prefix in `dj_pipeline/Makefile`'s `add-cron` target and re-run.

### Inspect, remove, or test the cron job

```bash
# View the currently installed crontab
crontab -l

# Remove all of the current user's cron entries
crontab -r

# Manual one-off test run (same env as cron, output goes to your terminal)
DJ_PIPELINE_DIR=/mnt/md0/.../dj_pipeline bash dj_pipeline/cron_script.sh

# Manual run that exercises the log redirect too
DJ_PIPELINE_DIR=/mnt/md0/.../dj_pipeline bash dj_pipeline/cron_script.sh \
    >> /mnt/md0/.../logs/cron.log 2>&1
tail -f /mnt/md0/.../logs/cron.log
```

### Logs

- `$DJ_PIPELINE_DIR/logs/cron.log` — shell-level log captured via
  `>> ... 2>&1`. Contains `docker compose` output and the populate steps'
  stdout/stderr. Append-only across runs.
- `$DJ_PIPELINE_DIR/logs/log_YYMMDD_HHMMSS.log` — Python-level log written
  by the `populate.py` logger, one file per invocation.

To keep `cron.log` from growing unbounded, configure logrotate (one-time):

```bash
sudo tee /etc/logrotate.d/mouse_hockey >/dev/null <<'EOF'
/mnt/md0/mouse_hockey/code/SCENE_MouseAR/dj_pipeline/logs/cron.log {
    weekly
    rotate 8
    compress
    missingok
    notifempty
}
EOF
sudo logrotate -d /etc/logrotate.d/mouse_hockey   # dry-run sanity check
```

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

This manual registration step should be treated as the normal path, not an optional cleanup step after population. Populate the model registry first, then run `DlcLiveData.populate()`, then `SyncedDlcLiveData.populate()`. That ordering is more reproducible than relying on inferred metadata from processor files.

If you still need the fallback path, run:

```python
DlcLiveData.populate(
    suppress_errors=True,
    reserve_jobs=True,
    make_kwargs={"init_from_file": True},
)
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
