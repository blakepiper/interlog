# InterLog metrics reference

This document defines every metric InterLog reports, how it is computed, what it
is comparable to, and where it breaks down. It is meant to be checkable by a
reviewer: each metric points at the code that produces it
([`analyzer.py`](../src/interlog/analyzer.py)).

**Design stance.** These metrics are deliberately *descriptive* — event counts,
rates, timing, and a small set of movement/keyboard measures with an established
basis in the HCI literature. They are **not** validated indices of any latent
construct (e.g. "frustration", "struggle", "cognitive load"), and they are
deliberately **not** combined into a single composite score. Use them as
observations, not diagnoses.

## Comparability: read this first

Two kinds of measures are reported, and they have different comparability rules.

| Kind | Examples | Comparable across machines? |
|------|----------|------------------------------|
| **Dimensionless / time-based** | path efficiency, rates per minute, pauses, inter-key interval, correction rate | Yes |
| **Raw pixel** | mouse distance, pointer speed, scroll distance | Only within one capture environment |

Raw pixel measures scale with the display's **device-pixel ratio** and, for
distance/speed, with how the motion was sampled. Path efficiency is built to be
free of both (see below). Every session records its environment under
`provenance` and `capture_region.dpi_scale` in `metadata.json`; check those
before comparing pixel measures from two sessions.

## Counts and rates

| Metric | Definition |
|--------|------------|
| `total_events` | All logged events, including mouse moves. |
| `total_interactions` | All events **except** `mouse_move`. |
| `total_clicks` / `total_scrolls` / `total_keypresses` / `total_drags` | Per-type counts. |
| `clicks_per_minute`, `actions_per_minute`, `keypresses_per_minute` | Count ÷ session minutes. `actions` excludes mouse moves. |

Session duration is `max(timestamp) − min(timestamp)` over all events.

## Timing

| Metric | Definition | Notes |
|--------|------------|-------|
| `average_pause_seconds`, `median_pause_seconds`, `longest_pause_seconds` | Stats over gaps between consecutive events. | Median is robust to a few long idles; prefer it over the mean. |
| `idle_time_seconds` | Sum of inter-event gaps longer than `IDLE_THRESHOLD_S` (2.0 s). | Threshold is a convention, not a measured boundary. |
| `active_time_seconds` | `duration − idle_time`. | |
| `long_pauses` | Count of gaps longer than `LONG_PAUSE_THRESHOLD_S` (2.0 s). | |
| `time_to_first_interaction_seconds` | Time from session start to the first non-move event. | Sensitive to when logging started relative to the task. |

## Pointer movement

| Metric | Definition | Comparability |
|--------|------------|---------------|
| `total_mouse_distance_px` | Summed Euclidean distance between consecutive `mouse_move` samples. | Pixel + sampling dependent. |
| `mean_pointer_speed_px_s` | Distance ÷ time, counting only continuous motion (gaps ≤ 1 s). | Pixel + sampling dependent. |
| `mean_path_efficiency` | See below. | **Cross-machine comparable.** |

### Path efficiency (the one metric built for comparison)

For each click→click segment, efficiency is the straight-line distance between
the two clicks divided by the actual path length the pointer travelled:

```
efficiency = straight_line_distance / actual_path_length      (0, 1]
```

`1.0` is a perfectly direct move; lower means a more roundabout path. This is a
standard pointer-quality measure (MacKenzie, Kauppinen & Silfverberg, *Accuracy
measures for evaluating computer pointing devices*, CHI 2001). The reported value
is the mean over all qualifying segments.

Two design choices make it comparable across machines:

1. **Dimensionless ratio** — the device-pixel ratio cancels, so it does not
   depend on display scaling.
2. **Fixed-rate resampling** — actual path length is measured on the trajectory
   resampled to a fixed `EFFICIENCY_RESAMPLE_HZ` (30 Hz), not the machine's
   native mouse-sampling rate. A fast mouse (many samples) and a slow one (few
   samples) recording the *same* motion yield the same length. This is verified
   by `test_path_efficiency_is_sampling_rate_invariant`.

**Limitations.** Segments shorter than `MIN_EFFICIENCY_SEGMENT_PX` (40 px) are
skipped (jitter dominates). Segments with no sampled intervening movement are
skipped. The only residual assumption is that the native sampling rate is ≥ 30 Hz
(true of essentially all mice). Returns `null` when nothing qualifies.

### Movement accuracy measures (MacKenzie CHI 2001)

The same click→click movements feed the rest of the accuracy-measure family from
MacKenzie, Kauppinen & Silfverberg. For each movement the straight line from the
start click to the end click is the **task axis**; the pointer path is resampled
to the fixed `EFFICIENCY_RESAMPLE_HZ` (so the *counts* below don't inflate with
the native sampling rate — verified by
`test_accuracy_counts_are_sampling_rate_invariant`), then each point is split
into distance *along* the axis and signed perpendicular distance *from* it. Each
metric is the mean over all qualifying movements.

| Metric | Symbol | Definition | Comparability |
|--------|--------|------------|---------------|
| `movement_offset_px` | MO | Mean **signed** perpendicular deviation — a consistent bias to one side of the ideal line. | Pixel (within environment). |
| `movement_error_px` | ME | Mean **absolute** perpendicular deviation. | Pixel (within environment). |
| `movement_variability_px` | MV | SD of perpendicular deviation. | Pixel (within environment). |
| `task_axis_crossings` | TAC | Times the path crosses from one side of the axis to the other. | Dimensionless count. |
| `movement_direction_changes` | MDC | Reversals **along** the axis (backtracking toward the start). | Dimensionless count. |
| `orthogonal_direction_changes` | ODC | Reversals **across** the axis (side-to-side correction). | Dimensionless count. |

A clean, direct movement has MO/ME/MV ≈ 0 and all three counts at 0; overshoot
and corrective submovements raise MDC/ODC (cf. the optimized-submovement model,
Meyer et al. 1988). All return `null` when no movement qualifies.

**Omitted: target re-entries (TRE).** The seventh measure in the paper requires a
defined target *width*, which free-form interaction logs do not carry — the same
reason InterLog does not report Fitts' law throughput. It is left out rather than
faked.

## Coordination and input rhythm

| Metric | Definition | Notes |
|--------|------------|-------|
| `modality_switches`, `modality_switches_per_minute` | Transitions between mouse (click/scroll/drag) and keyboard (key press) actions. | The KLM "homing" operator (Card, Moran & Newell 1980). Mouse moves and releases are ignored. |
| `scroll_reversals` | Times the scroll direction flips (sign change of `dy`). | A searching / re-reading signal. |
| `pre_click_dwell_seconds` | Mean time the pointer lingered within `PRE_CLICK_RADIUS_PX` (8 px) of a click before committing, capped at `PRE_CLICK_MAX_S` (2 s). | A descriptive settling / hesitation signal. `null` when no click had a sampled approach. |
| `interkey_interval_sd_seconds`, `interkey_interval_cv` | SD and coefficient of variation (SD ÷ mean) of inter-key intervals. | Typing rhythm / planning pauses. CV is dimensionless and **cross-person comparable**; both survive privacy mode (timing only). |

## Spatial spread of clicks

A scalar companion to the heatmap — *where* on screen interaction happened.

| Metric | Definition | Comparability |
|--------|------------|---------------|
| `click_spread_px` | RMS distance of clicks from their centroid. | Pixel (within environment). |
| `click_bbox_width_px`, `click_bbox_height_px` | Bounding-box extent of clicks. | Pixel (within environment). |

All return `null` with fewer than two clicks.

## Keyboard

| Metric | Definition | Privacy mode |
|--------|------------|--------------|
| `mean_interkey_interval_seconds` | Mean time between consecutive key presses. | Available (timing needs no key identity). |
| `typing_chars_per_minute` | Single-character keypresses ÷ session minutes. | `null` — key identity is redacted. |
| `backspaces` | Count of Backspace/Delete presses. | `null`. |
| `correction_rate` | `backspaces / total_keypresses`. | `null`. |

In privacy mode only that keys were pressed is logged, not which — so any metric
needing key identity is reported as `null` rather than guessed.

## Interaction signals (descriptive flags, not a diagnosis)

| Metric | Definition |
|--------|------------|
| `double_clicks` | Consecutive click pairs within `DOUBLE_CLICK_WINDOW_S` (0.3 s) and `DOUBLE_CLICK_DISTANCE_PX` (10 px). Each pair counted once. |
| `rage_clicks_detected` | Bursts of **3+** clicks within 1.0 s and 50 px. Each burst counted once. A UX-analytics signal for an unresponsive target, not a verified emotional state. |

## Event ↔ video synchronization

When a screen recording is captured, events and video share one **monotonic**
clock, so alignment is drift-free. The mapping (see
[`sync.py`](../src/interlog/sync.py)) is:

```
offset     = mono_start − video_first_frame_time     # written as video_start_offset
video_time = event_time + offset
```

Both `mono_start` and `video_first_frame_time` are readings of
`time.monotonic()`, so the offset arithmetic is **exact** (the
`test_event_offset_recovers_video_time` round-trip checks this).

### Error budget

The residual alignment error is physical, not arithmetic:

- **Frame quantization** — a recording only presents a new frame every `1/fps`
  seconds, so an event can fall up to **half a frame** from the nearest captured
  frame: `0.5/fps` (~33 ms at 15 fps, ~17 ms at 30 fps). Recorded per session as
  `sync_frame_quantization_seconds`.
- **First-frame detection latency** — `video_first_frame_time` is taken when
  ffmpeg *reports* its first frame over the progress pipe, which can lag the true
  first frame by a small, systematic amount. The viewer exposes a **manual nudge**
  control to absorb this residual.

Record at a higher `--fps` to tighten the quantization floor.
