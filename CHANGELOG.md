# Changelog

## 2.1.0 — 2026-11-24

- Added process-exclusive ownership for each persistent state directory.
- Added drift-corrected managed heartbeat with clean lifecycle controls.
- Added sender-scoped pseudonymous private-memory ledgers.
- Added explicit non-persistent private stimulus handling and digest-only output commits.
- Added hardened loopback-first HTTP service with token checks for remote binding, request limits, rate limiting, and safer response headers.
- Added startup integrity checks and corrupt snapshot quarantine.
- Preserved Ocha v1.10.30 operational self-model wording and calibrated 1 Hz homeostasis coefficients.
- Added a one-hour heartbeat-calibration regression test.
- Updated package metadata, configuration template, and API documentation.
- Added repository ignore rules for credentials/runtime state and a Python 3.10–3.13 GitHub Actions CI workflow.
