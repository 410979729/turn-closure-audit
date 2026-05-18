# Changelog

All notable changes to `turn-closure-audit` will be documented in this file.

## [Unreleased]

## [1.1.0] - 2026-05-18

### Added
- Added `candidate_schema.py` with `CandidateRecord` / `CandidateEvent`, contract final sinks, terminal statuses, required `candidate_content`, deterministic content/sink/classification IDs, and legacy `recommended_sink` / `candidate_status` serialization aliases.
- Added `candidate_ledger.py` as the append-only source-of-truth candidate event ledger under `turn.closure.audit/candidates/events/<day>.jsonl`, with replay/materialization, idempotent creation, terminal transition no-ops, and pending/overdue reports.
- Added `receipts.py` and `promotion.py` for normalized receipts, dry-run promotion buckets, conflict/sensitive/temporary/equivalent-memory handling, and explicit opt-in promotion through injected writers only.
- Added `distillation.py` as a no-write semantic candidate extraction interface that supports deterministic fake model clients without hardcoding or switching models.
- Added tests for candidate schema validation/roundtrip, ledger transitions/reporting, promotion idempotency/receipts, distillation, and authoritative ledger event emission from compatibility review writes.

### Changed
- Review-candidate JSONL remains backward-compatible but now includes `candidate_id`, `candidate_status`, `final_sink`, `recommended_sink`, `risk`, `confidence`, `candidate_content`, and `receipt`; authoritative `candidate.created` events are written to the candidate ledger.
- `/turn-closure` now exposes `pending`, `report`, and dry-run `promote` surfaces in addition to recent/path inspection.
- Updated release gate and design docs to include candidate governance, receipts, no-hidden-write promotion, and distillation modules.

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
