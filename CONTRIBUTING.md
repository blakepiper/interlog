# Contributing to InterLog

Thank you for your interest in improving InterLog! This project exists to help UX researchers, and contributions are very welcome.

## Ways to Contribute

### Bug Reports
Found a bug? Please [open an issue](https://github.com/yourusername/interlog/issues) with:
- Your operating system and Python version
- Steps to reproduce
- Expected vs actual behavior
- Any error messages

### Feature Requests
Have an idea? [Start a discussion](https://github.com/yourusername/interlog/discussions) to talk through:
- The use case
- How it would help UX researchers
- Whether it fits the "simple and free" philosophy

### Documentation
- Fix typos or unclear instructions
- Add examples or use cases
- Translate documentation (future)

### Code Contributions
See below for development setup and guidelines.

## Development Setup

```bash
# Clone the repo
git clone https://github.com/yourusername/interlog.git
cd interlog

# Install dependencies
pip install -r requirements.txt

# Run a test capture
python interlog.py --name test_session

# Analyze the output
python analyzer.py test_session_events.csv
```

## Code Style

- **Keep it simple**: This is for researchers, not developers
- **Document everything**: Clear docstrings and comments
- **No external dependencies** unless absolutely necessary (we only use `pynput`)
- **Cross-platform**: Test on Windows/Mac/Linux if possible
- **Privacy-first**: Never add telemetry or network features

## Pull Request Process

1. **Fork the repository**
2. **Create a branch**: `git checkout -b feature/your-feature-name`
3. **Make your changes**
4. **Test thoroughly** on your platform
5. **Update documentation** (README, QUICKSTART if needed)
6. **Submit PR** with clear description of changes

## Project Philosophy

InterLog is designed to be:
- **Free and open-source** - No paywalls, no accounts, no cloud
- **Simple** - Researchers should be able to use it in 2 minutes
- **Privacy-focused** - All data stays local
- **Minimal dependencies** - Easy to install and maintain
- **Cross-platform** - Works on Windows, Mac, Linux

When adding features, ask: "Does this help UX researchers without adding complexity?"

## Roadmap Ideas (Future)

If you're looking for ideas to contribute:

### High Priority
- [ ] Better error handling and user-friendly error messages
- [ ] Executable binaries (PyInstaller) for non-Python users
- [ ] Multi-monitor coordinate handling
- [ ] More robust CSV writing (handle crashes gracefully)

### Medium Priority
- [ ] HTML/JS viewer for syncing video with interaction data
- [ ] Heatmap generation from mouse movement data
- [ ] Export to additional formats (JSON, Parquet)
- [ ] PyPI package for `pip install interlog`

### Low Priority
- [ ] Real-time dashboard during recording
- [ ] Plugin system for custom analyzers
- [ ] Integration with common screen recorders

## Testing

Currently no automated tests (contributions welcome!). Manual testing checklist:

- [ ] Basic capture works (mouse, keyboard, scroll)
- [ ] Privacy mode correctly redacts keys
- [ ] Analyzer produces correct statistics
- [ ] Files are created in correct locations
- [ ] Help text is accurate (`python interlog.py --help`)

## Questions?

- Open an issue for bugs
- Start a discussion for features or questions
- Check existing issues/discussions first

## Code of Conduct

Be kind, constructive, and remember we're all here to help UX researchers. No jerks.

---

Thank you for helping make UX research more accessible!
