# Security Policy

## Supported versions

Security fixes are applied to the current `1.x` release line. Older local development snapshots are not supported as public release lines.

## Reporting a vulnerability

Please report security issues privately through GitHub Security Advisories for this repository when available, or by opening a minimal GitHub issue that states you have a security report without publishing exploit details.

Do not include API keys, tokens, passwords, private Telegram chat IDs, local filesystem paths with secrets, or other credentials in public issues.

Useful report details:

- affected version or commit SHA
- installation mode (`$HERMES_HOME/plugins/turn-closure-audit`, editable install, or wheel smoke)
- whether the issue was observed in a live Hermes gateway or in standalone tests
- minimal reproduction steps with placeholder credentials only
- expected vs. actual behavior

## Scope

In scope:

- unintended leakage of sensitive turn content in audit records, snapshots, or review candidates
- unsafe filesystem writes or path traversal from externally influenced session IDs
- audit records written outside `$HERMES_HOME/turn.closure.audit`
- failure to redact obvious token/password/authorization patterns in stored previews
- release artifacts that accidentally include local caches, private paths, or secret-like literals

Out of scope:

- compromise caused by publishing real credentials in local config files
- vulnerabilities in upstream Hermes hooks, tool execution, or gateway authentication unless `turn-closure-audit` uses them unsafely
- incomplete semantic classification of what should become long-term memory; this plugin records audit evidence and conservative candidates, it does not make final governance decisions
- best-effort redaction gaps in arbitrary natural language unless they lead to a concrete leak path

## Security posture

`turn-closure-audit` stores append-only JSONL audit rows and small redacted snapshots under `$HERMES_HOME/turn.closure.audit`. It treats all user-, session-, and tool-derived identifiers as untrusted path input and sanitizes latest-snapshot filenames before writing. Review candidates are intentionally conservative: they are evidence for a later human/agent review step, not automatic long-term memory promotion.
