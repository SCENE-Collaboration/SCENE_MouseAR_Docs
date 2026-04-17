# Schema - mousear_dlc_live

**Module**: `dj_pipeline/schemas/mousear_dlc_live.py`

Stores DeepLabCutLive! pose estimation data recorded during sessions and synchronizes it to the video frame grid.

---

## BodyPart

**Type**: `dj.Lookup`

Defines the keypoints tracked by the DLC model.

| Field | Type | Description |
|-------|------|-------------|
| `bodypart_name` | varchar(64) PK | Name of the body part |
| `description` | varchar(256) | Description |

**Tracked keypoints**: `nose`, `left_eye`, `right_eye`, `left_ear`, `right_ear`, `left_ear_tip`, `right_ear_tip`, `left_hip`, `right_hip`, `tail_base`, `tail3`, `tail_end`

---

## DlcModel

**Type**: `dj.Manual`

Registry of DLC models used for pose estimation. Must be populated before `DlcLiveData` can be imported.

| Field | Type | Description |
|-------|------|-------------|
| `model_id` | int32 PK | Unique model identifier |
| `model_name` | varchar(128) | Human-readable model name |
| `net_type` | varchar(64) | Neural network backbone (e.g., `resnet50`) |
| `detector` | varchar(64) | Detector used |
| `engine` | varchar(64) | DLC engine (`pytorch`, `tensorflow`) |
| `config` | json | Full model configuration |
| `bodyparts` | blob | List of tracked bodypart names |
| `description` | varchar(512) | Description of the model |

### Method: `insert_dlc_live_model_from_file(model_file, description, model_name)`

Loads a PyTorch `.pt`/`.pth` model file, extracts metadata, and inserts a new `DlcModel` entry:

```python
from dj_pipeline.schemas.mousear_dlc_live import DlcModel

model_id = DlcModel.insert_dlc_live_model_from_file(
    model_file="/path/to/snapshot-200000.pt",
    description="ResNet50, 12 keypoints, trained 2025-12",
    model_name="mice_resnet50_v2",
)
print(f"Inserted model_id={model_id}")
```

---

## DlcLiveData

**Type**: `dj.Imported`  **Depends on**: `Dataset`, `VideoRecording`, `DlcModel`

Imports raw DLC output files for a session.

| Field | Type | Description |
|-------|------|-------------|
| `dataset_id` | FK → Dataset | Session identifier |
| `video_id` | FK → VideoRecording | Associated camera |
| `model_id` | FK → DlcModel | Model used for inference |
| `processor_file` | varchar(256) | Name of the `*_dlcproc.pkl` file |
| `pose_estimate_file` | varchar(256) | Name of the `*_dlcproc_DLC.hdf5` file (if available) |

### Model Auto-Detection

If `model_id` is not specified at population time, the pipeline attempts to match an existing `DlcModel` by comparing bodyparts, `net_type`, and `detector`. If no match is found, a new model entry is created automatically from the processor file metadata.

To specify a model explicitly:

```python
DlcLiveData.populate(
    make_kwargs={"model_id": 2},
    suppress_errors=True
)
```

### DlcLiveData.ProcessorData

Processed head tracking output from the DLC processor (One Euro filtered).

| Field | Type | Description |
|-------|------|-------------|
| `head_xy` | blob | Head coordinates `(N_frames, 2)` — x, y |
| `time_stamp` | blob | Processor output timestamps in seconds |
| `frame_time` | blob | Video frame timestamps in seconds |
| `use_perf_counter` | bool | Whether perf_counter was used for timing |
| `use_filter` | bool | Whether the One Euro filter was applied |
| `filter_params` | json | Filter parameters (cutoff frequency, beta, etc.) |

### DlcLiveData.PoseData

Raw per-keypoint pose estimates. One row per `(session, bodypart)`.

| Field | Type | Description |
|-------|------|-------------|
| `bodypart_name` | FK → BodyPart | Keypoint name |
| `x` | blob | X-coordinates per frame |
| `y` | blob | Y-coordinates per frame |
| `likelihood` | blob | Detection likelihood per frame |

### DlcLiveData.PoseTimestamps

Timestamps for the DLC-processed frames (may be a subset of all video frames if frames were skipped).

| Field | Type | Description |
|-------|------|-------------|
| `frame_timestamp` | blob | Timestamps of DLC-processed frames |
| `pose_timestamp` | blob | Timestamps of pose estimate outputs |

---

## SyncedDlcLiveData

**Type**: `dj.Computed`  **Depends on**: `DlcLiveData`

Remaps DLC pose arrays from the DLC processing frame grid (which may have gaps due to dropped frames) to the full video frame grid. Missing frames are filled via linear interpolation.

| Field | Type | Description |
|-------|------|-------------|
| `nr_of_missing_frames` | int32 | Number of video frames with no nearby DLC estimate |

A frame is considered "missing" if the nearest DLC timestamp is more than half a frame period away.

```{note}
If more than 50% of frames are missing, a warning is logged — the interpolated pose data may be unreliable.
```

### SyncedDlcLiveData.PoseData

Synchronized pose per keypoint, aligned to the full video frame grid.

| Field | Type | Description |
|-------|------|-------------|
| `bodypart_name` | FK → BodyPart | Keypoint name |
| `x` | blob | X-coordinates, one value per video frame |
| `y` | blob | Y-coordinates, one value per video frame |
| `likelihood` | blob | Likelihoods, one value per video frame |

### SyncedDlcLiveData.ProcessorData

Synchronized head tracking, aligned to the full video frame grid.

| Field | Type | Description |
|-------|------|-------------|
| `head_xy` | blob | Head coordinates `(N_video_frames, 2)` |

### Method: `get_video_clip(key, steps, ...)`

Like `SynchronizedVideo.get_video_clip`, but with keypoints overlaid by default:

```python
from dj_pipeline.schemas.mousear_dlc_live import SyncedDlcLiveData

clip = SyncedDlcLiveData.get_video_clip(
    key={"dataset_id": "Tick_20260210_141820"},
    steps=(1200, 1600),
    show_keypoints=True,
    show_processor=True,
    keypoints_subset=["nose", "left_ear", "right_ear"],
    p_cutoff=0.6,
    keypoint_colormap="hot",
)
```

### Method: `get_trial_video(key, trial_id, ...)`

Extract a trial clip with pose overlay using `TrialInfo` boundaries:

```python
clip = SyncedDlcLiveData.get_trial_video(
    key={"dataset_id": "Tick_20260210_141820"},
    trial_id=5,
    include_init=False,
    include_iti=True,
    output_path="/tmp/trial5.mp4",
)
```
