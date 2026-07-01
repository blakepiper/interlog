# Changelog

All notable changes to InterLog are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security
- **Captured data is now owner-only on POSIX.** Session folders are created `700`
  and every written artifact (`events.csv`, `metadata.json`, `summary.*`,
  `intensity.csv`, `transcript.txt`, `text.json`, `heatmap.png`, `report.html`,
  the viewer HTML, and the screen recording) is set `600` as it is written, via a
  new best-effort `interlog.security.lock_down` helper (no-op on non-POSIX).
- **`record --name` rejects path traversal.** Names containing a path separator or
  a `..` segment are refused with a clear CLI error instead of writing outside the
  output directory.
- Documented the keystroke-timing side channel in privacy mode (timing intervals
  remain in `events.csv` and are sensitive for password-entry windows) and added
  an antivirus/EDR heads-up, in both `README.md` and `SECURITY.md`.

### Added
- **README visuals** — heatmap, cross-session comparison chart, HTML report
  screenshot, and an animated GIF of the synced viewer seeking the recording —
  plus a `pip`-free "Analyze in Python or R" snippet. Terminal/heatmap/chart
  images regenerate via `tools/capture_screenshots.py`; the report screenshot and
  viewer GIF have optional browser-based tools (`capture_html_screenshots.py`,
  `capture_viewer_gif.py`).
- **Structured `summary.json` export** — `interlog analyze --json` now writes a
  self-describing document (schema version, tool + session provenance,
  `capture_region`/`dpi_scale`, and native-typed metrics) instead of a bare stats
  dump, so results drop cleanly into pandas/R and carry the context needed to
  judge cross-session comparability. Documented in `docs/METRICS.md`.
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
- **Heatmap dependencies are no longer optional.** `matplotlib`, `numpy`, and
  `Pillow` are now core dependencies installed by `pip install .`, so
  `interlog heatmap` works out of the box. The `[heatmap]` extra is gone; `doctor`
  now treats missing heatmap deps as a broken install rather than an optional
  warning.
- **Redesigned the viewer and HTML report around a shared visual language.** Both
  use a clean system sans typography (no web fonts — the viewer stays fully
  offline) with tabular numerics for readouts, on a deep dark ground with a
  strictly semantic palette (mint = activity, red = rage/friction, amber =
  playhead cursor). The interaction timeline is the signature element in both — a
  filled intensity trace on a measurement graticule with a time ruler and glowing
  rage ticks. The viewer lays out the video and a timestamped **event log** side
  by side with the full-width trace below, and adds a live scanning cursor, a
  hover readout, and a header gauge cluster; the report leads with the trace as
  its hero and renders metrics as gauge cells. Idle animation was dropped — the
  viewer only redraws the cursor while the video is playing.
- **The viewer now carries InterLog branding** — a header wordmark and a footer
  attribution line, consistent with `report.html`.
- **Documentation is scoped to a clone-and-install repo, not a PyPI package.**
  Removed references to installing/releasing via PyPI (`pip install interlog`,
  `pip install ".[heatmap]"`); install is `git clone` + `pip install .`.
- The recorder now builds metadata via a testable `_build_metadata()` and reuses
  `interlog.sync.event_offset` for the alignment offset.
- `analyze` and `analyze --batch` rendering accept an injectable console
  (`print_summary(console=…)`, `render_batch_table`) so output is capturable.
- Session metadata loading is now a shared `read_session_metadata()` used by the
  viewer, report, and the JSON export.

### Fixed
- **Heatmap density cloud no longer renders blank for light sessions.** The
  movement density was Gaussian-blurred in 8-bit space, where a large `sigma`
  spread each sparse point below 1/255 and the whole field underflowed to zero —
  leaving only the white click dots with no color. The blur now runs in float
  (a small separable numpy Gaussian on a downscaled grid) and is normalized to
  the post-blur peak, so the colormap spans its full low→high range regardless of
  session density.
- The viewer now has a clear, prominent "Choose recording…" button in the
  no-video placeholder (with a "Change recording" control once loaded), instead of
  a small native file input tucked beside the sync-offset field, so loading a
  local recording in the browser is obvious.
- Rage-click detection now chains the distance check click-to-click instead of
  anchoring every click to the seed, so a burst that drifts across the screen
  (each click near the last, the last far from the first) still registers as one
  burst.
- The summary keyboard panel labelled a session with no typing as "privacy
  mode"; it now reads "none" and reserves "privacy mode" for redacted captures.
- `report` now HTML-escapes the session name and date, so a session named with
  `<`, `>`, or `&` no longer breaks the report markup.
- `doctor --live` no longer hangs indefinitely when input capture is blocked by
  OS permissions; it times out and reports the likely cause.
- `__version__` is read from installed package metadata, so it can't drift from
  `pyproject.toml`.
- `view --serve` releases its socket cleanly on Ctrl+C and no longer lets
  in-flight downloads outlive the server.
- `record --screen --monitor all` now errors on macOS/Linux (where it isn't
  supported) instead of silently capturing the primary display.

## [0.1.0] — 2026-06-26

Initial public release: local interaction logging (mouse/keyboard with monotonic
timestamps), cross-platform screen capture (Windows, macOS, Linux X11/Wayland),
descriptive analysis (`analyze`, `analyze --batch`), click/movement heatmaps,
a synced HTML viewer (`view`, `view --serve`), and self-contained HTML reports
(`report`). Honest, descriptive metrics — no invented composite scores.

[Unreleased]: https://github.com/blakepiper/interlog/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/blakepiper/interlog/releases/tag/v0.1.0
