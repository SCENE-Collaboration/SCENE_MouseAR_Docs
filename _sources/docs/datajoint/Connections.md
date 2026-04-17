# Database Connections

## datajoint.json

DataJoint reads connection credentials from `datajoint.json` in the working directory (typically `dj_pipeline/`). Copy and edit the template:

```json
{
  "database.host": "128.178.51.167",
  "database.port": 3307,
  "database.user": "your_username",
  "database.password": "your_password",
  "database.use_tls": false,
  "enable_filepath_management": true,
  "enable_adapted_types": true
}
```

| Field | Description |
|-------|-------------|
| `database.host` | IP or hostname of the MySQL server |
| `database.port` | Port (default DataJoint port is 3306; lab uses 3307) |
| `database.user` | Your database username |
| `database.password` | Your database password |
| `database.use_tls` | Whether to use TLS encryption for the connection |
| `enable_filepath_management` | Required for blob storage; keep `true` |
| `enable_adapted_types` | Required for custom DataJoint types; keep `true` |


## Environment Variables

The pipeline reads data paths from environment variables. Set these before running any population scripts.

| Variable | Required | Description |
|----------|----------|-------------|
| `RAW_DATA_PATH` | Yes | Directory containing `UnityData_*.json` behavioral files |
| `VIDEO_PATH` | Yes | Directory containing `UnityData_*.mp4` video files and timestamp JSONs |
| `DLC_DATA_PATH` | No | Directory containing DLC processor/pose files (defaults to `VIDEO_PATH` if unset) |
| `TAG` | Yes | Schema name prefix, e.g. `"test"` for a test database instance |

### Example

```bash
export RAW_DATA_PATH=/mnt/data/hockey_sessions
export VIDEO_PATH=/mnt/data/hockey_sessions
export DLC_DATA_PATH=/mnt/data/hockey_sessions
export TAG=test
```

Inside the Docker app container these are set via the `.env` file and `docker-compose.yml`. See [Infrastructure](Infrastructure.md) for details.

## Expected File Naming Conventions

The pipeline identifies sessions by matching filenames to the substring `dataset_id`, with the following format:

```
<subject_id>_<YYYYMMDD>_<HHMMSS>
```

| File type | Pattern |
|-----------|---------|
| Behavior JSON | `UnityData_<dataset_id>.json` |
| Video | `UnityData_<dataset_id>_cam<N>.mp4` |
| Video timestamps | `UnityData_<dataset_id>_cam<N>.mp4_timestamps.json` |
| DLC processor | `<dataset_id>*_dlcproc.pkl` |
| DLC pose | `<dataset_id>*_dlcproc_DLC.hdf5` |

## Verifying the connection to the database

```python
import datajoint as dj

# Check connection
dj.conn()

# List available schemas
dj.list_schemas()
```
