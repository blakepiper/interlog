# InterLog Roadmap

Guiding principles (unchanged): local-only, private, minimal dependencies,
cross-platform, simple enough for a non-developer researcher. The strategic bet
is **value at scale** — analyzing longer and repeated HCI sessions — so features
that help *quantify, triage, compare, and publish* rank highest.

Effort tags: **S** (< half a day), **M** (1–2 days), **L** (3+ days).

---

## Shipped

- **Core CLI** — `record`, `analyze`, `view`, `doctor` (single `interlog` entry point).
- **Screen capture** — `record --screen` (ffmpeg), crash-resilient `.mkv`→`.mp4`,
  `--monitor {primary,all}`, capture geometry in metadata.
- **Synced viewer** — `interlog view` HTML timeline, rage-click markers, hot
  spots, click-to-seek, sync-offset nudge.
- **Contained data layout** — `interlog-data/<session>/` with clean filenames.
- **Metrics** — pointer (distance/speed/idle), timing (median pause, hesitations,
  time-to-first-action), click quality (rage/dead/double), keyboard dynamics
  (privacy-aware), and a composite struggle score.
- **Typed-text analysis** — `analyze` reconstructs a transcript + local lexical
  stats by default (`--no-text` to skip); privacy mode auto-disables it.
- **Correctness** — monotonic timestamps, periodic flush, input validation.
- **Quality** — pytest suite + GitHub Actions CI (3 OSes × 3 Pythons) + ruff.

---

## Tier 1 — Close the analysis loop (highest leverage)

### F1. `view --serve` with auto-loaded recording (M)
A tiny local `http.server` rooted at the session folder so the viewer's
`<video>` loads `recording.mp4` automatically (with HTTP range seeking) instead
of asking the user to pick the file. Removes the biggest friction in `view`.
*Files:* new `serve.py`, `cli._cmd_view`, `viewer_template.html`.

### F2. Click & movement heatmap overlay (L) — **the differentiator**
Render a heatmap + click markers over a representative video frame (grab one via
`ffmpeg -ss <t> -frames:v 1`). Turns raw x/y into insight. Uses the
`capture_region` already stored in metadata to map global coords → frame space.
*Files:* `screen.py` (frame grab), `viewer.py`, `viewer_template.html`.

### F3. Cross-session aggregation (M) — **value at scale**
`interlog analyze --batch interlog-data/` walks all sessions and emits
`aggregate.csv` (one row/session: duration, clicks/min, rage clicks, etc.) plus
mean/SD across sessions. The payoff for studies with many participants.
*Files:* `cli.py`, `analyzer.py`.

### F4. Publishable report (M) — **supports the citation goal**
`interlog report <session|--batch>` → a self-contained HTML (optionally PDF)
with the stats table, intensity timeline, and heatmap as figures, ready to drop
into a paper or share with a team. Figures also exportable as PNG/SVG.
*Files:* new `report.py`, reuse `analyzer`/`viewer` rendering.

---

## Tier 2 — Richer HCI analysis

### F5. Mouse-trajectory metrics ✅ (shipped)
Done: total path length, continuous-motion speed, idle vs. active time,
time-to-first-action, in `summary.csv` + console. *Remaining (later):* curvature
and submovement counts.

### F6. Keystroke dynamics ✅ (shipped)
Done: typing speed (chars/min), mean inter-key interval, backspace count and
correction rate; privacy-aware (timing only, identities reported as `None`).
*Remaining (later):* burst-vs-pause typing segmentation.

### F7. Task / segment definitions (M)
Let a session be split into labelled segments (tasks), via live hotkey markers
(F9) or post-hoc time ranges, then report **per-task** metrics and time-on-task.
The unit HCI researchers actually compare.
*Files:* `recorder.py` (marker events), `analyzer.py`, viewer.

### F8. Behavioral coding / annotations in the viewer (L)
Researchers add timestamped tags/notes while reviewing ("confusion", "error"),
exported to `codes.csv`. Core qualitative-analysis workflow; pairs with F7.
*Files:* `viewer_template.html`, small save endpoint (depends on F1's server).

### F25. Typed-text reconstruction & lexical analysis ✅ (shipped)
Done: `analyze` reconstructs the typed transcript and runs local,
dependency-free lexical analysis (word/char counts, top keywords). On by default
(`--no-text` to skip); privacy mode is the off switch (auto-skipped); writes
`transcript.txt` + `text.json`. *Deferred (local-only/no-deps ethos):* sentiment
(lexicon dep), LLM-based analysis (network dep), topic modeling (noisy on
keystroke soup; only viable across a large corpus).

### F9. Struggle taxonomy & score ✅ (shipped)
Done: dead clicks, double clicks, hesitations, and a composite per-minute
`struggle_score` for triage/ranking. *Remaining (later):* surface dead/struggle
markers in the viewer timeline, and calibrate the score weights on real data.

---

## Tier 3 — Capture & ergonomics

### F10. Live "mark moment" hotkey (M)
A global hotkey logs a `marker` event during recording (think-aloud flags);
markers appear as jump targets in the viewer. Foundation for F7.
*Files:* `recorder.py`, `viewer_template.html`.

### F11. Mouse-move throttling + privacy tiers (S–M)
`--move-hz N` / `--no-mouse-move` to tame huge CSVs; privacy tiers (redact keys
only → coarsen mouse coords → drop moves) for sensitive studies.
*Files:* `recorder.py`, `cli.py`.

### F12. Audio (think-aloud) capture (M)
`--audio [device]` muxes an ffmpeg audio input into the recording; `doctor`
lists devices per-OS. Optional webcam as a stretch.
*Files:* `screen.py`, `doctor.py`, `cli.py`.

### F13. Session management commands (S)
`interlog list` (name, date, duration, #events, analyzed?/video?),
`interlog info <session>`, `interlog open <session>`, `interlog rm/rename`.
*Files:* new `cli` subcommands reading `metadata.json`.

### F14. Config file / defaults (S)
`~/.config/interlog/config.toml` (or project-local) for data-dir, fps, privacy
defaults; overridable per invocation.
*Files:* `cli.py`, new `config.py`.

---

## Tier 4 — Research-grade & ethics

### F15. Anonymization & video redaction (M) — privacy-first edge
`interlog scrub <session>` to drop/round PII-prone fields and blur screen
regions in the recording (ffmpeg boxblur over rectangles). Strong for IRB and
sharing datasets.
*Files:* new `scrub.py`, `screen.py`.

### F16. Consent / ethics helper (S)
Optional consent notice shown before recording, with the acknowledgment logged
to metadata — small but meaningful for human-subjects work.
*Files:* `recorder.py`, `cli.py`.

### F17. Export formats & tidy schema (S–M)
`--format {csv,json,sqlite,parquet}` and a documented "tidy"/long CSV plus a
JSON Schema for the event format, so R/pandas pipelines are first-class. Heavy
deps (pyarrow) stay optional/lazy.
*Files:* `analyzer.py`, `recorder.py`, `docs/`.

### F18. Frame-perfect sync (M)
Replace best-effort auto-offset: back-calculate true video t=0 from ffmpeg
`out_time` in the progress stream (and/or an optional on-screen clapperboard at
start). Keep the manual nudge as a fallback.
*Files:* `screen.py`, `recorder.py`, `viewer.py`.

---

## Tier 5 — Distribution & platform

- **F19. Publish to PyPI (S)** — `pip install interlog`; release workflow + tagging.
- **F20. Standalone binaries (M)** — PyInstaller builds bundling/detecting ffmpeg, for non-Python users.
- **F21. Verify macOS/Linux screen capture (M)** — exercise `avfoundation`/`x11grab`, device discovery in `doctor`; document Wayland limits.
- **F22. Side-by-side comparison view (L)** — two sessions/conditions in one viewer for A/B analysis.
- **F23. Gaze/eyetracking import (L, stretch)** — overlay imported Tobii-style gaze CSV on the timeline/heatmap.
- **F24. Plugin analyzers (L, stretch)** — a hook so labs can drop in custom metrics.

---

## Suggested next sprint

Analysis depth is now largely in (F5, F6, F9, F25 shipped), so the clear next
priority is the **Tier-1 loop**: F1 (serve) → F2 (heatmap) → F3 (aggregation)
→ F4 (report). That sequence delivers the full "record → measure → see where it
matters → put it in a paper" experience, which is the product's reason to exist.

After that, **study workflow** — F10/F7 (mark-moment hotkey → per-task metrics)
and F8 (behavioral coding) — is the strongest follow-on.

Open question for the maintainer: prioritize the Tier-1 analysis loop (F1–F4)
or jump to study-workflow features (F7/F8/F10) next?
