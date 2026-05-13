# Schema - mousear_screen_sync

**Module**: `dj_pipeline/schemas/mousear_screen_sync.py`

Validates temporal synchronization between the Unity game's software TTL signals and the hardware Teensy recordings. This is a quality-control table — it does not modify any data, but provides metrics that confirm whether hardware and software clocks are aligned.

---

## ScreenSync

**Type**: `dj.Computed`  **Depends on**: `UnitySession` (requires `ScreenTTLData` and normalized `TeensyStream` rows)

| Field | Type | Description |
|-------|------|-------------|
| `dataset_id` | FK → UnitySession | Session identifier |
| `nr_barcodes_send` | int32 | Number of TTL barcodes sent by Unity (from `ScreenTTLData.ttl_counters`) |

Per-screen metrics live in the `ScreenSync.Screen` part table:

| Field | Type | Description |
|-------|------|-------------|
| `dataset_id` | FK → ScreenSync | Session identifier |
| `screen_id` | int16 | Screen index taken from `TeensyStream.stream_id` |
| `raw_key` | varchar(255) | Original Teensy stream key used to derive this matching row |
| `nr_barcodes_detected` | int32 | Number of barcodes detected from that screen's analog stream |
| `fraction_barcodes_matched` | float32 | Fraction of sent barcodes matched to a detected barcode |
| `median_lag` | float32 | Median temporal lag between sent and detected barcodes (milliseconds) |

`ScreenSync` reads normalized rows from `UnitySession.TeensyStream` and inserts one `Screen` row per selected stream. `SCREEN_SYNC_SOURCE=lux` selects `stream_family='lux'`, which carries per-stream `timestamps_us`. `SCREEN_SYNC_SOURCE=photodiode` selects `stream_family='photodiode'`, which is packet-aligned and uses the shared packet clock source recorded in `packet_time_source`. `screen_id=1` corresponds to the unsuffixed stream and higher IDs follow the normalized stream ID.

### Synchronization Mechanism

The screen displays brief TTL barcode patterns (sequences of bright/dark frames) at regular intervals. These are:

1. **Sent** — Unity generates an 8-bit barcode and records its timestamp in `ScreenTTLData`
2. **Detected** — The Teensy reads the BH1750 lux sensor at high frequency; the `decode_session_analog_dj()` utility decodes the lux trace to identify barcode bursts
3. **Matched** — Detected barcodes are compared to sent barcodes; timing offset is measured

### Interpreting Results

| Metric | Good value | Concern |
|--------|-----------|---------|
| `fraction_barcodes_matched` | ≥ 0.95 | < 0.8 suggests missed barcodes or sensor issues |
| `median_lag` | 10–80 ms | Large lag may indicate display latency or sensor polling issues |
| `nr_barcodes_detected` ≈ `nr_barcodes_send` | Equal | Large difference suggests detection failures |

### Querying Sync Quality

```python
from dj_pipeline.schemas.mousear_screen_sync import ScreenSync
import datajoint as dj

# Per-screen rows with poor sync quality
poor_sync = (
    ScreenSync.Screen & "fraction_barcodes_matched < 0.9"
).fetch(as_dict=True)

# Summary statistics across all screens
stats = dj.U().aggr(
    ScreenSync.Screen,
    mean_match="AVG(fraction_barcodes_matched)",
    mean_lag="AVG(median_lag)",
).fetch1()
print(stats)
```
