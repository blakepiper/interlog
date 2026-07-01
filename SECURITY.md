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
  responsibility. To reduce casual exposure on shared machines, InterLog restricts
  session folders (`700`) and the files inside (`600`) to the owner on POSIX as
  they are written — best-effort defense-in-depth, not encryption.
- **Privacy mode redacts *which* key, not *when*.** `--privacy` drops key identity
  but leaves inter-key timing in `events.csv`. Keystroke timing alone is a known
  side channel for inferring password length and structure, so timing intervals
  captured during a password-entry window remain sensitive even under privacy mode.
- **`record --screen` shells out to `ffmpeg`.** Capture/remux arguments are
  built internally, not from untrusted input.
- **Session names are validated.** `record --name` rejects path separators and
  `..` segments so a name cannot write outside the chosen output directory.
- **The HTML viewer loads the recording locally in the browser** and uploads
  nothing.
