# Touchscreen Module - Quick Reference

> **📘 [Complete Documentation → TouchscreenArchitecture.md](TouchscreenArchitecture.md)**

## Overview

Distributed multitouch input system for low-latency behavioral experiments. Captures touch events on Linux devices (Raspberry Pi), streams normalized coordinates to remote hosts via TCP.

---

## Quick Start

### Server (Raspberry Pi)
```bash
python -m touchscreen.touch_controller --mode vectorized --tx-mode rate --tx-hz 60
```

### Client (Host PC)
```python
from touchscreen.host_client import HostTouchClient

client = HostTouchClient(host="192.168.1.100", port=6001)
client.start()
client.sync_time(attempts=6)

while True:
    pkt = client.drain()
    if pkt and pkt.get("point"):
        x, y = pkt["point"]["x"], pkt["point"]["y"]
        print(f"Touch at ({x:.3f}, {y:.3f})")
```

### Visualization
```bash
python -m touchscreen.host_vis_gui
```

---

## Core Features

- **5-stage view pipeline**: Raw → Normalized → Filtered → Reduced → Vectorized
- **Transmission modes**: Event-driven, rate-based (60 Hz), or hybrid
- **Clock synchronization**: NTP-style offset + RTT estimation
- **Recording**: Async JSONL writer with gzip, non-blocking enqueue
- **Multi-client**: Broadcast to multiple hosts simultaneously
