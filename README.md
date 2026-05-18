# turn-closure-audit

`turn-closure-audit` is a Hermes runtime plugin that records a **per-turn closure judgment** and writes a small, reviewable audit trail after each completed session.

It is designed for conservative knowledge governance:

- detect whether a turn already performed an explicit retention write
- classify unwritten but potentially important turns as review candidates
- append a redacted daily-note trail for later inspection
- keep an auditable latest-session snapshot and append-only JSONL log

## What it writes

Under the active Hermes profile:

- `$HERMES_HOME/turn.closure.audit/turns.jsonl`
- `$HERMES_HOME/turn.closure.audit/latest/<sanitized-session-id>--<sha1>.json`
- `$HERMES_HOME/turn.closure.audit/candidates/events/<YYYY-MM-DD>.jsonl`
- `$HERMES_HOME/memory/<YYYY-MM-DD>.md`
- `$HERMES_HOME/knowledge/review/turn-closure-candidates-<YYYY-MM-DD>.jsonl`

The append-only candidate event ledger is the authoritative candidate truth. Daily notes and review JSONL are compatibility/evidence surfaces only; writing there does **not** mean a candidate became durable memory. The latest snapshot filename is derived from the session id through a filename-safe mapping, so hostile session identifiers cannot escape the `latest/` directory.

## Installation assumption for Hermes users

This project is published for people who want to **download it and use it with Hermes**.

The intended install shape today is:

1. download or clone this plugin directory
2. place the unpacked directory at `$HERMES_HOME/plugins/turn-closure-audit/`
3. enable it in Hermes as a local runtime plugin

Important boundary:

- current Hermes plugin discovery expects an **unpacked plugin directory**
- a wheel build is useful for packaging/release verification, but it is **not** the primary install path for Hermes users yet
- do not read wheel build success as proof that Hermes can install or discover the plugin directly from the wheel alone

## Public module layout

- `turn_closure_audit.py` — package-compatible public import shim for wheel installs
- `runtime.py` — Hermes hook registration and per-session state orchestration
- `events.py` — write-event detection for memory, skill, and retention-file tools
- `paths.py` — profile-safe output paths plus hostile session-id filename sanitization
- `redaction.py` — preview normalization and best-effort secret redaction
- `classification.py` — explainable candidate classification heuristics
- `storage.py` — locked JSONL, latest snapshot, daily-note, and review-candidate writers
- `commands.py` — `/turn-closure` command formatting
- `candidate_schema.py` — structured candidate records/events, final sinks, terminal statuses, deterministic IDs, risk/confidence helpers
- `candidate_ledger.py` — append-only candidate event ledger, materialized views, transitions, pending/overdue reports
- `receipts.py` — normalized promotion / merge / rejection receipts
- `promotion.py` — dry-run and explicit opt-in promotion decision engine with injected writers only
- `distillation.py` — no-write semantic candidate extraction interface for injected/fake model clients
- `clock.py` — timezone-aware timestamps

## Hook model

The plugin registers three Hermes hooks:

- `post_tool_call`
- `post_llm_call`
- `on_session_end`

At runtime it watches tool calls for successful retention writes, captures redacted user/assistant previews, then produces a final turn judgment at session end.

## Retention writes it recognizes

Current write detection covers successful calls to:

- `memory`
- `hindsight_retain`
- `skill_manage`
- `write_file`
- `patch`

For file writes, only retention-oriented paths under `knowledge/`, `memory/`, or `memories/` are treated as true knowledge writes.

## Safety and redaction

The plugin deliberately stores **previews**, not full transcripts.

Built-in redaction heuristics mask common secret-like values before they are written into audit artifacts, including patterns such as:

- API keys / tokens / passwords / cookies
- `Authorization:` / `Bearer ...` / `Basic ...`
- Chinese secret-like labels such as `暗号`

This is a best-effort safety layer, not a substitute for upstream secret-handling discipline.

## Classification behavior

If no explicit retention write was observed, the plugin can still mark a turn as a candidate for later human review when it appears to contain:

- user preferences or boundaries
- governance / knowledge-management discussion
- substantive diagnostic or outcome-heavy work
- interrupted turns worth preserving for review

Candidate turns are appended to both the daily note and the structured review-candidate log.

## Command

The plugin registers:

```text
/turn-closure [recent|last|status] [N]
/turn-closure path
/turn-closure pending [N]
/turn-closure report
/turn-closure promote --dry-run [--candidate ID]
```

This gives a lightweight runtime view into recent judgments, pending candidates, overdue counts, and promotion dry-runs without opening raw files manually. Actual durable writes are disabled by default and require an explicit caller-provided writer/adapter.

## Candidate governance

Candidate records carry `candidate_content`, `classification`, `final_sink`, `risk`, `confidence`, status, evidence summary, and optional receipt. Allowed final sinks are `user`, `memory`, `project`, `ops`, `skill`, `knowledge`, `discard`, and `ask_user`; review JSONL, daily notes, and the candidate ledger are not final sinks.

Every candidate starts `pending` and should eventually become `promoted`, `merged`, `rejected_noise`, `rejected_temporary`, `rejected_sensitive`, `needs_user_confirmation`, or `expired`. Promotion dry-runs bucket candidates into `would_promote`, `needs_confirmation`, `suggest_skill`, `suggest_knowledge`, `would_reject`, `conflicts`, and `already_satisfied`. Low-risk user preferences may be recommended for promotion, but auto-promotion is opt-in only and hidden writes are intentionally not implemented. `scope-recall` is the recommended durable-memory companion when installed, but this plugin works standalone as audit and governance evidence.

## Test coverage

The included tests currently cover:

- preview redaction of secret-like values
- write-event extraction for retention-safe patch paths
- session-end audit + daily-note + review-candidate emission
- candidate schema/event roundtrip and validation
- append-only candidate ledger materialization, terminal transitions, and pending/overdue reports
- dry-run promotion buckets, idempotent opt-in promotion, receipts, and no hidden writes
- semantic distillation with deterministic fake model clients

## Packaging boundary

This directory is packaged so it can be published and reviewed like a normal open-source plugin repository.

Important boundary:

- Hermes runtime discovery still expects an unpacked plugin directory
- a successful wheel build is a packaging sanity check, not proof of direct wheel installation support in Hermes

## Current limitations

- candidate classification is intentionally heuristic and conservative
- this plugin records governance evidence; durable memory promotion requires terminal candidate events plus receipts
