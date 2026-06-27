# Changelog

All notable changes to InterLog are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **`interlog demo`** — generates realistic synthetic sessions (events +
  metadata, flagged `"synthetic": true`) so newcomers can explore `analyze`,
  `view`, `report`, and `--batch` without recording. Reproducible by `--seed`;
  `--sessions N` produces a varied set for batch aggregation. The synthesis lives
  in `interlog.demo` and also backs the README screenshots.
- **README screenshots** — crisp SVGs of `analyze` and `analyze --batch`,
  rendered from the real code paths via `tools/capture_screenshots.py` (so they
  can't drift), plus Python-version and license badges.
- **Richer movement & input metrics** (all in `analyze`/`summary.csv`, documented
  in `docs/METRICS.md`):
  - MacKenzie CHI 2001 accuracy measures on click→click movements — movement
    offset (MO), error (ME), variability (MV), task-axis crossings (TAC), and
    direction changes along/across the axis (MDC/ODC). Computed on the fixed-rate
    resampled trajectory so the counts are sampling-rate invariant. (TRE is
    omitted — it needs a defined target width, like Fitts' throughput.)
  - `modality_switches` (+ per minute) — mouse↔keyboard transitions (KLM homing).
  - `scroll_reversals`, `pre_click_dwell_seconds`.
  - `interkey_interval_sd_seconds` and `interkey_interval_cv` (typing rhythm;
    survive privacy mode).
  - `click_spread_px` and click bounding-box extents (spatial dispersion).
  - Selected metrics surfaced in the terminal summary (`print_summary`).
- `interlog.sync` — a single, tested source of truth for the event↔video
  alignment formula (`offset = mono_start − video_first_frame_time`,
  `video_time = event_time + offset`), with a documented frame-quantization
  error budget (`0.5/fps`).
- Session **provenance** in `metadata.json`: tool version, OS/platform, and
  Python version, so a session can be interpreted and compared later.
- Video sync fields in `metadata.json`: `video_fps` and
  `sync_frame_quantization_seconds` (the per-capture alignment error budget).
- [`docs/METRICS.md`](docs/METRICS.md) — every metric's definition, formula,
  units, comparability, literature reference, and limitations, plus the sync
  model and error budget.
- `mypy` type checking in CI.

### Changed
- The recorder now builds metadata via a testable `_build_metadata()` and reuses
  `interlog.sync.event_offset` for the alignment offset.
- `analyze` and `analyze --batch` rendering accept an injectable console
  (`print_summary(console=…)`, `render_batch_table`) so output is capturable.

### Fixed
- The summary keyboard panel labelled a session with no typing as "privacy
  mode"; it now reads "none" and reserves "privacy mode" for redacted captures.

## [0.1.0] — 2026-06-26

Initial public release: local interaction logging (mouse/keyboard with monotonic
timestamps), cross-platform screen capture (Windows, macOS, Linux X11/Wayland),
descriptive analysis (`analyze`, `analyze --batch`), click/movement heatmaps,
a synced HTML viewer (`view`, `view --serve`), and self-contained HTML reports
(`report`). Honest, descriptive metrics — no invented composite scores.

[Unreleased]: https://github.com/blakepiper/interlog/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/blakepiper/interlog/releases/tag/v0.1.0
