# Infrastructure (Docker & MySQL)

## Overview

The pipeline runs against a MySQL 8.0 database hosted in Docker. A second container provides the Python application environment (Jupyter, population scripts, IPython shell).

Both services are defined in `dj_pipeline/docker-compose.yml` and managed via the `dj_pipeline/Makefile`.

---

## Services

### MySQL Database (`db`)

- **Image**: `mysql:8.0`
- **Container name**: `mouse_hockey_db`
- **Port**: `3307` (mapped from internal 3307)
- **Data volume**: `${DATABASE_MOUNT}/mysql` → `/var/lib/mysql`
- **Character set**: `utf8mb4`

The root password is set via `MYSQL_ROOT_PASSWORD` in `dj_pipeline/.env`.

### Application Container (`client`)

- **Base image**: `deeplabcut/deeplabcut:3.0.0-core-cuda12.4-cudnn9`
- **Built from**: `dj_pipeline/Dockerfile`
- **Port**: `8891` → `8888` (Jupyter)
- **Volumes**:
  - `./` → `/dj_pipeline` (pipeline code)
  - `${DATABASE_MOUNT}/shared` → `/shared`
  - `${DATA_MOUNT}` → `/data/hockey_test` (raw data)
- **Environment**: reads from `.env`; sets `RAW_DATA_PATH`, `VIDEO_PATH`, `DLC_DATA_PATH`, `TAG`

---

## Makefile Targets

From `dj_pipeline/`:

| Target | Description |
|--------|-------------|
| `make up_all` | Start all Docker services (db + client) |
| `make build_all` | Build and start all services |
| `make down_all` | Stop all services |
| `make client` | Open an IPython shell in the app container |
| `make bash` | Open a bash shell in the app container |
| `make notebook` | Start Jupyter notebook (port 8891) |
| `make mysql` | Connect to MySQL via CLI |
| `make add-cron` | Install automated population cron job |

---

## Environment File (`.env`)

The `dj_pipeline/.env` file configures both Docker and pipeline behaviour:

```bash
DJ_LAB=mathis-lab
GUI=False
EMAIL=False
MYSQL_ROOT_PASSWORD=<mysql_root_password>
DATABASE_MOUNT=/mnt/md0/mouse_hockey/database
DATA_MOUNT=/mnt/md0/mouse_hockey/input_data
SCHEMA_TAG=test
EMAIL_ADDRESS_LIST=email_addresses.ini
```

---

## Quick Start

1. Clone the repository
   - `git clone git@github.com:SCENE-Collaboration/SCENE_MouseAR.git`
   - `cd SCENE_MouseAR/dj_pipeline`

2. Edit database credentials (`host`, `port`, `user`, `password`)
   - `vi datajoint.json`

3. Set variables in `.env`:
   - `MYSQL_ROOT_PASSWORD`
   - `DATABASE_MOUNT` to the path where database infrastructure file will be stored (`${DATABASE_MOUNT}/mysql` and `${DATABASE_MOUNT}/shared`)
   - `DATA_MOUNT` to the input data path

4. Build and start services
   - `make build_all`
   - `make up_all`

5. Enter the app container and source the environment variables
   - `make bash`
   - `source .env`

6. Run the pipeline
   - python populate.py

7. Inspect logs
   The log of the pipeline run appears under the `logs` directory
