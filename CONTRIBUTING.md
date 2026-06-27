# Contributing to InterLog

Thank you for your interest in improving InterLog! This project exists to help HCI researchers, and contributions are very welcome.

> **License note:** InterLog is MIT-licensed (see [LICENSE](LICENSE)). By contributing you agree your contributions are licensed under the same terms. If you use InterLog in research, please cite it ([CITATION.cff](CITATION.cff)).

## Ways to Contribute

### Bug Reports
Found a bug? Please [open an issue](https://github.com/blakepiper/interlog/issues) with:
- Your operating system and Python version
- Steps to reproduce
- Expected vs actual behavior
- Any error messages

### Feature Requests
Have an idea? [Open an issue](https://github.com/blakepiper/interlog/issues) to discuss:
- The use case
- How it would help HCI researchers
- Whether it fits the "simple and local" philosophy

### Documentation
- Fix typos or unclear instructions
- Add examples or use cases

### Code Contributions
See below for development setup and guidelines.

## Development Setup

```bash
# Clone the repo
git clone https://github.com/blakepiper/interlog.git
cd interlog

# Install in editable mode with dev + heatmap dependencies
pip install -e ".[dev,heatmap]"

# Confirm the environment is healthy
interlog doctor

# Run a test capture
interlog record --name test_session

# Analyze the output
interlog analyze interlog-data/test_session
```

## Project Layout

```
src/interlog/
  cli.py               # Entry point: all subcommands
  recorder.py          # InteractionLogger — captures events to CSV
  demo.py              # Synthetic session generator behind `interlog demo`
  analyzer.py          # InteractionAnalyzer — statistics, intensity, sparkline, batch_analyze
  screen.py            # ScreenRecorder — ffmpeg screen capture (record --screen)
  viewer.py            # build_viewer() — generates the synced HTML timeline viewer
  viewer_template.html # Viewer UI (data injected at build time)
  serve.py             # Range-request HTTP server for view --serve
  heatmap.py           # build_heatmap() — mouse density PNG (optional deps)
  report.py            # build_report() — self-contained HTML report with embedded heatmap
  text_analysis.py     # Typed-text reconstruction and lexical stats
  sync.py              # Event<->video alignment formula + sync error budget
  doctor.py            # Environment + input-capture diagnostics
  branding.py          # ASCII banner
pyproject.toml         # Packaging + the `interlog` console script
docs/METRICS.md        # Definitions, formulas, and limitations of every metric
tools/
  capture_screenshots.py       # Regenerates the README terminal SVGs + heatmap/compare PNGs
  capture_html_screenshots.py  # Optional: report.html + viewer screenshots (needs a browser)
tests/
  test_interlog.py     # pytest suite (headless, no pynput/ffmpeg required)
```

## Code Style

- **Keep it simple**: This is for researchers, not developers
- **No unnecessary comments**: Well-named code is self-explanatory; only comment non-obvious *why*s
- **Minimal dependencies**: Core install needs only `pynput` and `rich`; heavy deps (`matplotlib`, `numpy`, `Pillow`) are optional extras
- **Cross-platform**: Test on Windows / Mac / Linux if possible
- **Local-only**: Never add telemetry or network features. Capture is global, so
  be conservative about what gets logged or written to disk by default.

## Running Tests

```bash
pytest
```

Tests are headless (no pynput or ffmpeg required) and run on all supported platforms via CI.

## Regenerating the README screenshots

The README images are crisp SVGs rendered from the real `analyze` / `--batch`
code paths over synthetic sessions — never hand-edited. After a change that
affects terminal output, regenerate them:

```bash
python tools/capture_screenshots.py   # banner.svg, analyze.svg, batch.svg, heatmap.png, compare.png
```

The HTML report and the synced viewer need a real browser to render, so their
screenshots live in a separate, optional tool:

```bash
pip install playwright && playwright install chromium
python tools/capture_html_screenshots.py   # writes docs/img/report.png, viewer.png
```

## Pull Request Process

1. **Fork the repository**
2. **Create a branch**: `git checkout -b feature/your-feature-name`
3. **Make your changes**
4. **Run the test suite**: `pytest`
5. **Update documentation** (README, QUICKSTART if needed)
6. **Submit PR** with a clear description of changes

## Project Philosophy

InterLog is designed to be:
- **Free and open-source** — No paywalls, no accounts, no cloud
- **Simple** — Researchers should be able to use it in 2 minutes
- **Privacy-focused** — All data stays local
- **Minimal dependencies** — Easy to install and maintain
- **Cross-platform** — Works on Windows, Mac, Linux

When adding features, ask: "Does this help HCI researchers without adding complexity?"

## Questions?

Open an issue — bugs, features, or general questions are all welcome.

## Code of Conduct

Be kind, constructive, and remember we're all here to help HCI researchers.

---

Thank you for helping make HCI research more accessible!
