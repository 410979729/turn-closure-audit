# Architecture

## Core responsibilities

`turn-closure-audit` does four things:

1. observe turn-level write signals
2. capture redacted previews
3. write an auditable final judgment
4. keep candidate turns visible for later review

## Why this plugin exists

Without a closure audit, it is easy for an agent to finish a useful turn without actually writing durable knowledge anywhere. This plugin makes that gap inspectable.

## Module boundaries

The public source tree is intentionally split into focused modules while preserving Hermes' required unpacked plugin entrypoint:

- `__init__.py` — Hermes plugin entrypoint and public re-export surface
- `runtime.py` — hook registration, per-session state, final record assembly
- `events.py` — successful retention-write detection for `memory`, `hindsight_retain`, `skill_manage`, `write_file`, and `patch`
- `paths.py` — profile-safe output path construction plus filename-safe `session_id` handling
- `redaction.py` — preview normalization and best-effort secret-like value masking
- `classification.py` — conservative, explainable candidate heuristics
- `candidate_schema.py` — candidate/event dataclasses, final sinks, deterministic ids, compatibility aliases
- `candidate_ledger.py` — append-only source-of-truth candidate ledger, materialized views, transitions, reports
- `receipts.py` — normalized outcome receipts
- `promotion.py` — dry-run promotion workflow and explicit opt-in injected writes
- `distillation.py` — no-write semantic extraction interface
- `storage.py` — `fcntl`-locked JSONL, latest snapshot, daily-note, and review-candidate compatibility writers
- `commands.py` — `/turn-closure` command formatting
- `clock.py` — timezone-aware timestamp helpers
- `turn_closure_audit.py` — package-compatible import shim for wheel smoke/install checks

## Storage surfaces

- `turn.closure.audit/turns.jsonl` for append-only audit history
- `turn.closure.audit/latest/` for most recent per-session snapshots
- `turn.closure.audit/candidates/events/<day>.jsonl` for authoritative append-only candidate lifecycle events
- `memory/<day>.md` for readable daily sedimentation notes
- `knowledge/review/*.jsonl` for structured review compatibility output

Audit logs, daily notes, review JSONL, and candidate ledgers are evidence/governance surfaces. They are not durable final memory. A candidate is only closed when the candidate ledger contains a terminal event with a receipt or rejection/confirmation reason.

## Judgment philosophy

The plugin is intentionally conservative:

- observed retention writes win immediately
- interrupted turns remain reviewable
- preference/boundary/governance/outcome-heavy turns become candidates with final sinks (`user`, `memory`, `project`, `ops`, `skill`, `knowledge`, `discard`, or `ask_user`)
- ordinary turns remain logged but not promoted
- low-risk promotion is recommended only in dry-run unless an explicit opt-in writer is injected
- `scope-recall` can provide durable receipts when installed, but is an optional companion rather than a hard dependency

## Loader compatibility note

Hermes runtime discovery still loads this project as an unpacked plugin directory via root `__init__.py`. The wheel is verified for packaging hygiene and importability, but the documented Hermes install path remains cloning or copying the directory into `$HERMES_HOME/plugins/turn-closure-audit/`.
