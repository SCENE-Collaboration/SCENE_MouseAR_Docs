# Overview

This repository is a work-in-progress for SCENE - mice affordance tasks using Augmented Reality(AR) in Unity.
The code and task design is based on the previous development in the Mathis Lab - https://github.com/SCENE-Collaboration/FreelyMovingVR4Mice.

## Organization
* `mouse_ar/` - the main python module for the mice AR tasks.
* `touchscreen/` - code for the touchscreen interface.
* `UnityAR/` - Unity project files for the AR environment.
* `rl/` - Gymnasium wrappers: RL training, replay of recorded sessions and what-if replays. See the [user guide](docs/RL/GYMNASIUM_WRAPPERS.md).
* `tests/` - unit tests for the codebase.
* `docs/` - documentation files.
* `dj_pipeline/` - DataJoint pipeline for data management and transfer, including a GUI for data transfer.


## Installation
Clone the repository:
```bash
git clone <repository-url>
```
plain installation:
```bash
pip install -e .
```

to be able to build docs:
```bash
pip install -e .[docs]
```
Development Setup
```bash
pip install -e .[dev,docs]
```
## Documentation
Documentation can be found at [SCENE_MouseAR_Docs](https://scene-collaboration.github.io/SCENE_MouseAR_Docs/).

To locally build the documentation, run:

```bash
jupyter-book build .
```
Then open the generated HTML files in `_build/html/` with your web browser.

Suggested reading flow:

1. [System Overview](docs/python/Overview.md)
2. [Unity Framework Overview](docs/Unity/Overview.md)
3. [Touchscreen Overview](docs/touchscreen/Overview.md)
4. [Python GUIs](docs/python/GUIs.md)
5. [Data Transfer GUI](docs/python/DataTransferGUI.md)
6. [Task Controllers](docs/python/Tasks.md)


## Code Formatting & Linting

* Formatted code makes your life and those who use/review your code easier. Standardized formatting with tools like `black` and `isort` (see the provided `.pre-commit-config.yaml`).
* [Pre-commit hooks](https://pre-commit.com/) to automate checks before pushing code! Follow their quick Guide to do this, but in short:

(1) install it in your dev env
```bash
pip install pre-commit
```
(2) install the git hooks:
```bash
pre-commit install
```
(3) Just run it on your code BEFORE you git push:
```bash
pre-commit run --all-files
```


## Replay Integration Tests

The RL wrappers and replay are documented in [docs/RL/GYMNASIUM_WRAPPERS.md](docs/RL/GYMNASIUM_WRAPPERS.md).

Unity-backed replay integration tests live under [tests/rl](tests/rl) and are marked `integration`.
They are manual-first and skip cleanly unless a local Unity build is available.

Required environment variable:

```bash
export SCENE_UNITY_ENV_PATH=/absolute/path/to/MouseAR.x86_64
```

Optional environment variables:

```bash
export SCENE_REPLAY_DATA_PATH=data/UnityData_TestMouse_20260306_135117.json
export SCENE_REPLAY_TRIAL_ID=1
export SCENE_UNITY_BASE_PORT=5604
export SCENE_UNITY_WORKER_ID=11
```

Run the manual Unity-backed replay integration suite with the touchscreen env:

```bash
conda run -n touchscreen python -m pytest tests/rl/test_hockey_replay_integration.py -q
```

Run the replay-wrapper unit suite without Unity:

```bash
conda run -n touchscreen python -m pytest tests/rl/ -q
```


## Acknowledgement

Some items in this repo are adapted from [DeepLabCut](https://github.com/DeepLabCut/DeepLabCut), [CEBRA](https://cebra.ai/), [FreelyMovingVR4Mice](https://github.com/SCENE-Collaboration/FreelyMovingVR4Mice) and the [Mathis Lab of Adaptive Intelligence](https://github.com/orgs/AdaptiveMotorControlLab). It is under an Apache 2.0 License.
