# Overview

This repository is a work-in-progress for SCENE - mice affordance tasks using Augmented Reality(AR) in Unity.
The code and task design is based on the previous development in the Mathis Lab - https://github.com/SCENE-Collaboration/FreelyMovingVR4Mice.

## Organization
* `mouse_ar/` - the main python module for the mice AR tasks.
* `touchscreen/` - code for the touchscreen interface.
* `UnityAR/` - Unity project files for the AR environment.
* `rl/` - reinforcement learning related code.
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
As the repo is currently private its not possible to build a public documentation site. However, you can build the documentation locally using Jupyter Book.

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


## Acknowledgement

Some items in this repo are adapted from [DeepLabCut](https://github.com/DeepLabCut/DeepLabCut), [CEBRA](https://cebra.ai/), [FreelyMovingVR4Mice](https://github.com/SCENE-Collaboration/FreelyMovingVR4Mice) and the [Mathis Lab of Adaptive Intelligence](https://github.com/orgs/AdaptiveMotorControlLab). It is under an Apache 2.0 License.
