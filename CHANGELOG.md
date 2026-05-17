# Changelog

All notable changes to `turn-closure-audit` will be documented in this file.

## [1.0.2] - 2026-05-17

### Changed
- Promoted the repository to public-quality release posture with stable package metadata.
- Split the runtime out of the prior single-file implementation into focused modules: `runtime.py`, `events.py`, `paths.py`, `redaction.py`, `classification.py`, `storage.py`, `commands.py`, and `clock.py`.
- Kept Hermes' unpacked plugin entrypoint while adding a cleaner package import surface for wheel smoke tests.

### Added
- Added `SECURITY.md` and made the release gate require it in both the source tree and wheel payload.
- Added `scripts/check.release.py` to enforce release docs, stable metadata, generated-artifact cleanup, tests, wheel payload inspection, and temp-install import smoke.

## [2.4.1] - 2026-05-12

### Added
- Added public release files: `README.md`, `DESIGN.md`, `LICENSE`, `pyproject.toml`, `.gitignore`, and docs.
- Added open-source release documentation for runtime shape, outputs, and safety boundaries.
- Added packaging metadata so wheel builds can be used as a release sanity check.

### Changed
- Tightened repository hygiene for public publication by removing backup files and generated caches from the plugin tree.
- Clarified the plugin's release boundary: packaged for review/publish, but Hermes still loads it from an unpacked plugin directory at runtime.
- Sanitized `session_id` before writing latest-session snapshot filenames so `latest/` writes cannot escape the audit directory.
- Switched packaging from a bare top-level module artifact to an importable `turn_closure_audit` package layout while keeping Hermes runtime loading on the unpacked plugin directory.
- Added regression coverage for sanitized latest snapshot filenames.

## [2.4.0] - 2026-05-11

### Added
- Introduced per-turn closure judgments with append-only audit logging.
- Added redacted daily-note and review-candidate auto-sinks.
- Added `/turn-closure` runtime inspection command.
- Added focused pytest coverage for redaction, write detection, and session-end output behavior.
