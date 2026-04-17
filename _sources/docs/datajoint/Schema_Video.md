# Schema - mousear_video

**Module**: `dj_pipeline/schemas/mousear_video.py`

Manages video recording metadata and aligns video frames to behavioral game steps.

---

## VideoRecording

**Type**: `dj.Imported`  **Depends on**: `Dataset`

Stores metadata for each video file associated with a session. Supports multiple cameras per session (e.g., `cam0`, `cam1`).

| Field | Type | Description |
|-------|------|-------------|
| `dataset_id` | FK → Dataset | Session identifier |
| `video_id` | int32 PK | Camera index (parsed from `_cam<N>.mp4` suffix, 0 if absent) |
| `file_name` | varchar(256) | Video filename |
| `frame_rate` | float32 | Frames per second |
| `resolution_x` | int32 | Horizontal resolution in pixels |
| `resolution_y` | int32 | Vertical resolution in pixels |
| `video_duration` | float32 | Duration in seconds |
| `nr_frames` | int32 | Total number of frames |

### VideoRecording.FrameTimestamps

Precise timestamps for each frame, loaded from the companion `*.mp4_timestamps.json` file (for example, `video.mp4_timestamps.json`). Present only when the timestamp file was found alongside the video.

| Field | Type | Description |
|-------|------|-------------|
| `timestamp_file_name` | varchar(256) | Name of the timestamp file |
| `frame_timestamps` | blob | Array of frame timestamps in seconds (wall-clock / perf_counter) |
| `match_video_frames` | bool | Whether `len(frame_timestamps) == nr_frames` |

```{note}
`SynchronizedVideo` and `SyncedDlcLiveData` both require `FrameTimestamps` to exist. Sessions without a timestamp file will not populate downstream tables.
```

---

## SynchronizedVideo

**Type**: `dj.Computed`  **Depends on**: `VideoRecording`, `UnitySession`

Maps each behavioral game step to the nearest video frame index. Enables frame-accurate extraction of video clips for any time window defined in game steps.

| Field | Type | Description |
|-------|------|-------------|
| `dataset_id` | FK | Session identifier |
| `video_id` | FK | Camera identifier |
| `frame_steps` | blob | Array of length `N_steps`; `frame_steps[i]` is the video frame index for step `i` |

### Alignment Method

Step timestamps are converted to absolute wall-clock time:

```
abs_step_time = step_time + session_start_time
```

Each absolute step time is then matched to the nearest frame timestamp using binary search (`numpy.searchsorted`).

### Method: `get_frame_for_step(key, step)`

Returns the frame index for a given game step (or list of steps):

```python
from dj_pipeline.schemas.mousear_video import SynchronizedVideo

frame_idx = SynchronizedVideo.get_frame_for_step(
    key={"dataset_id": "Tick_20260210_141820", "video_id": 0},
    step=1500,
)
```

### Method: `get_video_clip(key, steps, ...)`

Extracts a video clip between two game steps as a numpy array or saves to a file:

```python
clip = SynchronizedVideo.get_video_clip(
    key={"dataset_id": "Tick_20260210_141820", "video_id": 0},
    steps=(1200, 1600),
    output_path="/tmp/trial_clip.mp4",   # omit to return array
    show_keypoints=True,                 # overlay DLC pose
    show_processor=True,                 # overlay head_xy
    p_cutoff=0.6,                        # min likelihood for keypoints
)
```

### Method: `get_trial_video(key, trial_id, ...)`

Convenience wrapper that fetches trial step boundaries from `TrialInfo` and calls `get_video_clip`:

```python
clip = SynchronizedVideo.get_trial_video(
    key={"dataset_id": "Tick_20260210_141820", "video_id": 0},
    trial_id=5,
    include_init=False,   # exclude initiation period
    include_iti=True,     # include post-trial ITI
    show_keypoints=True,
)
```
