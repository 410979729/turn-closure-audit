# turn-closure-audit design

## Goal

`turn-closure-audit` exists to answer one narrow but important question after every session:

> Did this turn already write the relevant knowledge down, and if not, should it remain visible for later review?

The plugin is intentionally conservative. It does **not** attempt to automate full memory governance. Instead, it creates a small audit trail that makes missing sedimentation visible.

## Runtime shape

The plugin is split into small public modules while keeping Hermes' required root `__init__.py` entrypoint:

- `runtime.py` owns hook registration, session state, and final record assembly
- `events.py` owns retention-write detection for tool calls
- `paths.py` owns profile-safe output paths and session-id filename hardening
- `redaction.py` owns preview normalization and best-effort secret masking
- `classification.py` owns explainable candidate heuristics
- `storage.py` owns file locking and all audit/daily-note/review-candidate writes
- `commands.py` owns `/turn-closure` output formatting
- `clock.py` owns timezone-aware timestamp helpers
- `turn_closure_audit.py` provides a package-compatible import shim for wheel installs

The plugin is loaded by Hermes from the plugin directory and registers three hooks:

1. `post_tool_call`
2. `post_llm_call`
3. `on_session_end`

It also exposes one command:

- `/turn-closure`

## Data flow

### 1. Tool-phase observation

On each `post_tool_call`, the plugin inspects whether the tool invocation represents a successful retention write.

Recognized write classes:

- `memory` mutations
- `hindsight_retain`
- `skill_manage` mutations
- retention-safe `write_file`
- retention-safe `patch`

File writes only count when the destination resolves under a retention-oriented path such as `knowledge/`, `memory/`, or `memories/`.

### 2. LLM-phase preview capture

On `post_llm_call`, the plugin stores small normalized previews of:

- user message
- assistant response
- model name
- platform

These previews are redacted before persistence to reduce the chance of leaking raw secrets into audit artifacts.

### 3. Session-end judgment

On `on_session_end`, the plugin drains per-session state and writes a final record containing:

- whether the turn completed or was interrupted
- whether retention writes were observed
- whether the turn should remain reviewable as a candidate
- why the plugin made that judgment
- where automatic sink records were written

## Output artifacts

### Audit log

Append-only JSONL:

- `$HERMES_HOME/turn.closure.audit/turns.jsonl`

### Latest snapshot

Per-session overwrite file:

- `$HERMES_HOME/turn.closure.audit/latest/<sanitized-session-id>--<sha1>.json`

The filename is normalized and suffixed with a short digest derived from the raw session id so path traversal and hostile filename characters cannot escape the `latest/` directory.

### Daily note sink

Human-readable markdown:

- `$HERMES_HOME/memory/<YYYY-MM-DD>.md`

### Review candidate sink

Structured JSONL for later triage:

- `$HERMES_HOME/knowledge/review/turn-closure-candidates-<YYYY-MM-DD>.jsonl`

## Deduping strategy

The plugin constructs a stable `record_id` from:

- normalized session key
- turn open timestamp
- judgment timestamp

Sink writers check for prior presence of that record before appending.

Daily-note entries use an HTML sentinel comment for dedupe.
Review-candidate entries dedupe by `record_id` search in the target file.

## Redaction model

The plugin redacts common secret-like patterns from previews before persistence.

Covered shapes include:

- `api_key`, `token`, `secret`, `password`, `cookie`, `session`, `Authorization`
- `Bearer ...` and `Basic ...`
- Chinese secret labels such as `暗号`

This layer is intentionally simple and runtime-local. It is a guardrail, not a formal DLP system.

## Concurrency model

The plugin uses:

- an in-process thread lock for session state
- a re-entrant file lock plus `fcntl.flock()` for append/update operations

This keeps concurrent writes from corrupting the audit outputs when multiple events arrive close together.

## Classification model

When no retention write is observed, the plugin uses lightweight heuristics to decide whether a turn is a candidate for later review.

Current candidate buckets:

- `user-preference-or-boundary`
- `governance-or-knowledge`
- `task-outcome-or-diagnostic`
- `interrupted-turn`
- `already-written`
- `routine`

The classification is intentionally explainable rather than model-heavy.

## Non-goals

This plugin does not try to be:

- a long-term memory provider
- a semantic search system
- a transcript archive
- an automatic approval engine for memory promotion

## Release posture

For open-source release, the repository should always satisfy these baseline conditions:

- release docs exist and describe the real behavior honestly
- tests pass from the plugin directory
- wheel packaging includes non-Python plugin assets such as `plugin.yaml`
- generated caches / backups are cleaned before publishing

## Known limitations

- candidate heuristics are substring-based and intentionally simple
- redaction is best-effort and should not be the only secret boundary
