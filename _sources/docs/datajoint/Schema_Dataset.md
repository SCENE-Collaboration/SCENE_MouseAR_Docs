# Schema - mousear_dataset

**Module**: `dj_pipeline/schemas/mousear_dataset.py`

This schema is the entry point for the pipeline. It registers experimental datasets and links them to the institutional session registry provided by `base_schemas`.

---

## ExperimentType

**Type**: `dj.Lookup`

Defines the category of experiment.

| Field | Type | Description |
|-------|------|-------------|
| `experiment_type` | varchar(64) PK | Unique name of the experiment type |
| `description` | varchar(256) | Description of the experiment type |

**Contents**: `"Behavioral"`, `"Ephys"`

---

## Dataset

**Type**: `dj.Manual`

Core registry of experimental sessions. Each entry corresponds to one `UnityData_*.json` file.

| Field | Type | Description |
|-------|------|-------------|
| `dataset_id` | varchar(64) PK | Unique session identifier, e.g. `"Tick_20260210_141820"` |
| `session_date` | datetime | Date and time of the session, parsed from `dataset_id` |
| `notes` | varchar(256) | Optional notes about the session |

### Method: `populate_from_files()`

Scans `RAW_DATA_PATH` for `UnityData_*.json` files and inserts new entries:

```python
from dj_pipeline.schemas.mousear_dataset import Dataset

Dataset.populate_from_files()
```

The `dataset_id` is the filename stem with `UnityData_` stripped. The `session_date` is parsed from the `<YYYYMMDD>_<HHMMSS>` portion of the name.

---

## SessionDataset

**Type**: `dj.Computed`

Links each `Dataset` to an entry in `base_schemas.exp.Session`. This enables joining the pipeline data with the institutional subject and session registry.

| Field | Type | Description |
|-------|------|-------------|
| `dataset_id` | FK → Dataset | Session dataset identifier |
| `mouse_name` | FK → Session | Subject identifier (from base_schemas) |
| `doe` | FK → Session | Date of experiment |
| `attempt` | FK → Session | Session attempt number |

### Matching Logic (`find_session_for_dataset`)

Datasets and sessions are matched **positionally within a day**:

1. All datasets for the same mouse on the same day are sorted by recording time
2. All `base_schemas` sessions for that mouse on that day are sorted by `attempt`
3. The i-th dataset is assigned to the i-th session

If fewer sessions than datasets exist for a day, the extra datasets are left unlinked (warning logged).

### Method: `register_dataset(session_key, dataset_key)`

Manually override the automatic matching for a specific dataset:

```python
from dj_pipeline.schemas.mousear_dataset import SessionDataset

SessionDataset.register_dataset(
    session_key={"mouse_name": "Tick", "doe": "2026-02-10", "attempt": 1},
    dataset_key={"dataset_id": "Tick_20260210_141820"},
)
```
