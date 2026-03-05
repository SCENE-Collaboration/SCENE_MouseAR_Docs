# Data Transfer GUI (`dj_pipeline/gui_transfer`)

## Overview

The Data Transfer GUI is a PyQt-based tool used to:

- collect session metadata from DataJoint-backed dropdown menus,
- attach raw files produced during a session,
- generate session summary outputs (`.npy` + `.json`),
- transfer files locally or to a remote host.

This module lives in `dj_pipeline/gui_transfer` and is launched from `main.py`.

---

## What this GUI covers

The interface has four main parts:

1. **Mouse**: mouse identity and static metadata.
2. **Experiment**: rig/task/session metadata (including notes and score sheets).
3. **Optogenetics**: opto selection metadata.
4. **Transfer**: file attachment and transfer destinations.

The submit step validates required fields and required file types before transfer.

---

## Launch

From repository root:

```bash
python dj_pipeline/gui_transfer/main.py
```

You can prefill fields from CLI arguments:

```bash
python dj_pipeline/gui_transfer/main.py \
  --mouse-name Wolverine \
  --dataset-id Wolverine_20260116_144944 \
  --deltaweight 7.9 \
  --task AR_visual_discrimination \
  --rig 12 \
  --anesthesia awake \
  --body-condition BodyCondition1 \
  --license GE1 \
  --session-notes "good session"
```

Supported prefill options include:

- `--mouse-name`
- `--dataset-name`
- `--dataset-id`
- `--deltaweight` (float)
- `--task`, `--rig`, `--anesthesia` / `--anasthesia`
- `--body-condition`
- `--opto`
- `--license` / `--licence`
- `--session-notes`
- `--housing-assay`
- `--general-assay`

---

## Initial context behavior

`main.build_initial_context()` merges CLI/context values into a dictionary passed to GUI modules.

### Prefill mapping highlights

- `deltaweight` → experiment `weight_percentage` (`QDoubleSpinBox`, float)
- `task` → `Task`
- `rig` → `Rig`
- `anesthesia` / `anasthesia` → `Anesthesia`
- `license` / `licence` → `MouseLicensing`
- `body_condition` → `MouseScoreSheet_BodyCondition`
- `general_assay` → `MouseScoreSheet_GeneralAssay`
- `housing_assay` → `MouseScoreSheet_HousingAssesment`
- `session_notes` → notes field
- `opto` → `opto_name`

Matching for dropdown values is case-insensitive and supports partial matches.

---

## Dataset-based auto file discovery

If `dataset_name` or `dataset_id` is provided in initial context, the transfer module performs auto-discovery per file type:

- Unity JSON (`unity_json_path`)
- DLC pkl/pickle (`dlc_live_pkl_path`)
- DLC hdf5/h5 (`dlc_live_hdf5_path`)
- videos (`video_paths`)

Search behavior:

1. normalize dataset hint,
2. search each datatype folder (`config.get_path(key)`),
3. fallback to `raw_data_src`,
4. filter by filename containing dataset hint and matching expected pattern.

If some expected file types are still missing, the GUI displays a warning listing missing and found categories.

---

## Video transfer modes

Two modes are available:

1. **Raw video transfer** (default): transfer selected videos.
2. **Video-info-only mode**: enable checkbox
   `Extract video infos only (.npy), do not transfer video files`

In video-info-only mode, the GUI extracts local metadata (`fps`, frame count, resolution, duration, optional timestamps) and writes:

- `{dataset_id}_videoinfos.npy`

Then raw video transfer entries are replaced by this summary file.

---

## How remote transfer works

Transfer is done in `utils/utils.py` via `transfer_files()`:

- If `ip == "localhost"`: files are copied locally (`shutil.copy`).
- Otherwise: files are sent using `scp` to `host@ip:<dst>`.

Per-file transfer entries contain:

- `src`: source directory
- `filename`: basename
- `dst`: destination directory (built from `remote_dst` + datatype subfolder)

Datatype destination folders:

- `video_paths` → `dlc_video`
- everything else (including outputs) → `data`

---

## Required configuration (`config/config.json`)

Minimal keys:

- connection:
  - `ip`
  - `host`
  - `remote_dst`
- menu and cache:
  - `remote_dropdown_menu`
  - `host_dropdown_menu`
  - `cache`
- local outputs:
  - `gui_output_folder`
  - `processed_path`
- discovery roots:
  - `raw_data_src`
  - `unity_json_path`
  - `dlc_live_pkl_path`
  - `dlc_live_hdf5_path`
  - `video_paths`

Example local-only setup:

```json
{
  "ip": "localhost",
  "host": "",
  "remote_dst": "/tmp/test_transfer",
  "remote_dropdown_menu": "dj_pipeline/gui_transfer/menu.npy",
  "host_dropdown_menu": "dj_pipeline/gui_transfer/menu.npy",
  "gui_output_folder": "dj_pipeline/gui_transfer/out_files",
  "cache": "default",
  "raw_data_src": "/data/raw",
  "unity_json_path": "/data/raw",
  "dlc_live_pkl_path": "/data/dlc_video_raw",
  "dlc_live_hdf5_path": "/data/dlc_video_raw",
  "video_paths": "/data/dlc_video_raw",
  "processed_path": "/data/processed_rig"
}
```

---

## Troubleshooting

- **No dropdown menu found at startup**:
  verify `remote_dropdown_menu` / `host_dropdown_menu` paths and file existence.
- **Remote copy fails**:
  verify SSH connectivity and write permissions to `remote_dst`.
- **Dataset auto-discovery misses files**:
  verify datatype folder paths and dataset naming consistency.
- **Missing fields during submit**:
  required GUI metadata and each transfer datatype must be present.
