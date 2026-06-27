# Changelog

All notable changes to InterLog are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
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

## [0.1.0] — 2026-06-26

Initial public release: local interaction logging (mouse/keyboard with monotonic
timestamps), cross-platform screen capture (Windows, macOS, Linux X11/Wayland),
descriptive analysis (`analyze`, `analyze --batch`), click/movement heatmaps,
a synced HTML viewer (`view`, `view --serve`), and self-contained HTML reports
(`report`). Honest, descriptive metrics — no invented composite scores.

[Unreleased]: https://github.com/blakepiper/interlog/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/blakepiper/interlog/releases/tag/v0.1.0
