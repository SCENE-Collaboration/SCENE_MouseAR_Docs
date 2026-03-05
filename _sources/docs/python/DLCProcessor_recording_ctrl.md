# Recording Control Documentation

## Overview

The DLC processor classes (`BaseProcessor_socket` and `MyProcessor_socket`) now support remote recording control from clients. This allows you to:

- Set session names
- Start/stop recording (with automatic data queue clearing)
- Trigger saves from the client
- Control when data is logged without restarting the processor

## Architecture

### Processor Side

**Recording Flag**: Processors only append data to storage queues when `self.recording = True`

**Session Name**: Auto-generates filename based on session name: `{session_name}_dlc_processor_data.pkl`

**Control Messages**: Processors listen for dict messages with `"cmd"` field on the same connection used for data broadcasting

### Client Side

**DLCClient** can now send control commands to the processor using:
- High-level methods: `set_session_name()`, `start_recording()`, `stop_recording()`, `trigger_save()`
- Low-level: `send_command(cmd, **kwargs)`

## Usage

### Basic Workflow

```python
from mouse_ar.ctrl.dlc_client import DLCClient

# Connect to processor
client = DLCClient(address=("localhost", 6000))
client.start()

# Set session name (affects save filename)
client.set_session_name("experiment_001")

# Start recording (clears data queues on processor)
client.start_recording()

# ... processor collects data while you receive ...
for _ in range(100):
    data = client.read()
    # Use data...

# Stop recording
client.stop_recording()

# Trigger save on processor
client.trigger_save()
# Saves to: "experiment_001_dlc_processor_data.pkl"

client.close()
```

### Multiple Sessions

```python
client = DLCClient(address=("localhost", 6000))
client.start()

# Session 1
client.set_session_name("trial_001")
client.start_recording()
time.sleep(10)  # Collect data
client.stop_recording()
client.trigger_save()  # Saves trial_001_dlc_processor_data.pkl

# Session 2 (reuses same processor)
client.set_session_name("trial_002")
client.start_recording()  # Clears queues
time.sleep(10)
client.stop_recording()
client.trigger_save()  # Saves trial_002_dlc_processor_data.pkl

client.close()
```

### Custom Save Filenames

```python
# Use default filename (based on session name)
client.trigger_save()

# Or specify custom filename
client.trigger_save(filename="custom_data.pkl")
```

## Control Commands

### Available Commands

| Command | Parameters | Description |
|---------|-----------|-------------|
| `set_session_name` | `session_name: str` | Sets session name and updates filename |
| `start_recording` | None | Enables recording flag, clears all data queues |
| `stop_recording` | None | Disables recording flag |
| `save` | `filename: str` (optional) | Triggers save to file |
| `set_filter` | `use_filter: bool` | Enable/disable filtering (MyProcessor_socket only) |
| `set_filter_params` | `filter_kwargs: dict` | Update filter parameters (MyProcessor_socket only) |

### Command Format

Commands are sent as dictionaries:

```python
{"cmd": "set_session_name", "session_name": "my_session"}
{"cmd": "start_recording"}
{"cmd": "stop_recording"}
{"cmd": "save", "filename": "optional.pkl"}
{"cmd": "set_filter", "use_filter": True}
{"cmd": "set_filter_params", "filter_kwargs": {"min_cutoff": 0.5, "beta": 0.01}}
```

## DLCClient API

### High-Level Methods

```python
client.set_session_name(session_name: str)
    """Set the session name on the processor."""

client.start_recording()
    """Start recording on the processor (clears existing data)."""

client.stop_recording()
    """Stop recording on the processor."""

client.trigger_save(filename: str = None)
    """Trigger the processor to save its data."""

client.set_filter(use_filter: bool)
    """Enable or disable filtering on the processor."""

client.set_filter_params(min_cutoff: float = None, beta: float = None, d_cutoff: float = None)
    """Update One-Euro filter parameters on the processor."""
```

### Low-Level Method

```python
client.send_command(cmd: str, **kwargs)
    """
    Send a control command to the processor.

    Args:
        cmd: Command name
        **kwargs: Additional command parameters

    Example:
        client.send_command("set_session_name", session_name="test")
    """
```

## Processor Implementation Details

### Recording Flag (Thread-Safe)

The recording flag uses `threading.Event()` for thread-safe operation:

```python
# In __init__:
self._recording = Event()  # Thread-safe flag

# Property wrapper for simple interface:
@property
def recording(self):
    return self._recording.is_set()
```

**Why Event instead of bool?**
- **Thread-safe**: Atomic set/clear operations
- **No race conditions**: Safe access from main thread (processing) and RX threads (commands)
- **Python best practice**: Recommended pattern for inter-thread signaling

Data is only stored when `self.recording = True`:

```python
def process(self, pose, **kwargs):
    # ... processing ...

    # Only store if recording (thread-safe check)
    if self.recording:  # Calls self._recording.is_set()
        self.time_stamp.append(curr_time)
        self.center_x.append(x)
        # ... etc

    # Always broadcast (regardless of recording state)
    self.broadcast(payload)

    return pose
```

### Data Queue Clearing

When `start_recording` is received:
1. Sets `self._recording.set()` (thread-safe)
2. Calls `_clear_data_queues()` which clears all deques
3. Resets `self.curr_step = 0`

When `stop_recording` is received:
1. Calls `self._recording.clear()` (thread-safe)

Subclasses can override `_clear_data_queues()` to clear additional queues:

```python
def _clear_data_queues(self):
    """Clear all data storage queues including pose-specific ones."""
    super()._clear_data_queues()  # Clear base class queues
    self.center_x.clear()
    self.center_y.clear()
    # ... clear your custom queues
```

### Session Name Property

```python
@property
def session_name(self):
    return self._session_name

@session_name.setter
def session_name(self, name):
    self._session_name = name
    self.filename = f"{name}_dlc_processor_data.pkl"
```

## Benefits

1. **No Processor Restart**: Change sessions without restarting DLCLive
2. **Clean Data**: Each session starts with cleared queues
3. **Automatic Naming**: Filename derived from session name
4. **Remote Control**: Client controls recording, not processor
5. **Flexible**: Can broadcast continuously but only record when needed

## Example Use Cases

### Behavioral Experiment

```python
client = DLCClient(address=("localhost", 6000))
client.start()

for trial_num in range(10):
    # Set up trial
    client.set_session_name(f"mouse_A_trial_{trial_num:03d}")

    # Wait for trial start signal
    wait_for_trial_start()

    # Start recording
    client.start_recording()

    # Run trial
    run_trial(client)

    # Stop and save
    client.stop_recording()
    client.trigger_save()

    # ITI
    time.sleep(5)

client.close()
```

### Real-time Monitoring + Selective Recording

```python
client = DLCClient(address=("localhost", 6000))
client.start()

# Monitor continuously
while monitoring:
    data = client.read()
    display_on_screen(data)

    # User decides to record interesting behavior
    if user_presses_record_button():
        client.set_session_name(f"recording_{timestamp}")
        client.start_recording()

    if user_presses_stop_button():
        client.stop_recording()
        client.trigger_save()

client.close()
```
