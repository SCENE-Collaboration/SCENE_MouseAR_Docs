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

---

## TeensyBarcodes

**Type**: `dj.Computed`  **Depends on**: `UnitySession` (requires `TeensyStream` with `stream_family='barcodettl'`, `TeensyData`, and `UnityData`)

Decodes the 32-bit rolling barcode sequence emitted by the Teensy `barcodes.ino` firmware over a dedicated `BarcodeTTL` stream. This signal is shared with electrophysiology recording systems and serves as the cross-system temporal anchor: each decoded barcode maps to a host timestamp, a device microsecond timestamp, and (where available) an aligned game step — enabling post-hoc alignment of ephys spike times to behavioral events.

| Field | Type | Description |
|-------|------|-------------|
| `dataset_id` | FK → UnitySession | Session identifier |
| `nr_barcodes_detected` | int32 | Total number of successfully decoded barcodes |
| `nr_missed_barcodes` | int64 | Estimated count of barcodes missing from the sequence (plausible forward gaps only; corrupt/out-of-order detections are excluded) |
| `ids_monotonic` | bool | `True` iff every consecutive `decoded_id` increases by exactly 1; `False` signals corrupt or misdecoded barcodes |
| `aligned` | bool | `True` iff `task_start_time_ref` was available and `t_task`/`game_step` are populated in part rows |
| `sample_rate_hz` | float32 | Inferred packet sampling rate (Hz), derived from median `t_dev_us` inter-packet interval |

Per-barcode detections live in the `TeensyBarcodes.Barcode` part table:

| Field | Type | Description |
|-------|------|-------------|
| `dataset_id` | FK → TeensyBarcodes | Session identifier |
| `barcode_idx` | int32 | 0-based detection order within the stream |
| `decoded_id` | int64 | 32-bit barcode value (0 – 2³²−1) |
| `stream_idx` | int32 | Sample index in the barcode stream where the barcode starts |
| `t_host` | float64 | Host clock timestamp at detection (same timebase as `task_start_time_ref`) |
| `t_dev_us` | float64 | Device microsecond timestamp at detection |
| `t_task` | float64 | Detection time relative to task start (same timebase as `step_time`); `NULL` if `task_start_time_ref` is `NULL` |
| `game_step` | int32 | Nearest aligned game step; `NULL` if outside the session step-time range or unaligned |

### Population Logic

1. Reads the single `barcodettl` `TeensyStream` row for the session; warns and uses the first if multiple are present.
2. Aligns the barcode signal with shared per-packet clocks (`t_host`, `t_dev_us`) from `TeensyData`, truncating to the shortest array if lengths mismatch.
3. Infers `sample_rate_hz` from the median inter-packet interval in `t_dev_us`.
4. Calls `decode_barcodes(values, sample_rate_hz)` to extract barcode events.
5. Maps each detection to a `game_step` via nearest-neighbour lookup into `UnityData.step_time`, offset by `task_start_time_ref`.
6. Counts missed barcodes using plausible forward gaps only (`diffs > 0` and `≤ max_possible_gap`), where `max_possible_gap` is derived from `BARCODE_INTERVAL_S = 5.0 s`. Corrupt or out-of-order IDs are counted separately and flagged via `ids_monotonic=False` rather than inflating `nr_missed_barcodes`.

### Interpreting Results

| Metric | Good value | Concern |
|--------|-----------|---------|
| `ids_monotonic` | `True` | `False` indicates misdecoded or corrupt barcode IDs |
| `nr_missed_barcodes` | 0–2 | Large values suggest recording gaps or barcode generator resets mid-session |
| `aligned` | `True` | `False` means `task_start_time_ref` was missing (legacy sessions); `t_task` and `game_step` will be `NULL` |
