# Security Policy

## Supported versions

InterLog is pre-1.0; security fixes land on the latest release and `main`.

| Version | Supported |
|---------|-----------|
| 0.1.x   | ✅        |
| < 0.1   | ❌        |

## Reporting a vulnerability

Please report security issues **privately** rather than opening a public issue:

- Use GitHub's [private vulnerability reporting](https://github.com/blakepiper/interlog/security/advisories/new), or
- Email the maintainer (see the address on the GitHub profile).

Include what you found, how to reproduce it, and the impact you foresee. Expect
an acknowledgement within a few days and a fix or mitigation plan once confirmed.

## Scope notes

InterLog runs **entirely locally** — it captures input events and (optionally) a
screen recording to disk, with no network calls, accounts, or telemetry.
Relevant considerations for reviewers:

- **Captured data is sensitive by nature.** Event logs and recordings live under
  the chosen output directory in plaintext; protecting them is the operator's
  responsibility. `--privacy` redacts key identities at capture time.
- **`record --screen` shells out to `ffmpeg`.** Capture/remux arguments are
  built internally, not from untrusted input.
- **The HTML viewer loads the recording locally in the browser** and uploads
  nothing.
