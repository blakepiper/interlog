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
