# Contributing

## Development loop

From the plugin directory:

```bash
python -m pytest -q
python -m pip wheel . --no-deps -w /tmp/turn-closure-audit-dist
```

## Release checklist

Before publishing:

- confirm tests pass
- inspect the built wheel and verify `plugin.yaml` + release docs shipped
- remove `__pycache__/`, `.pytest_cache/`, `build/`, `dist/`, and `*.egg-info`
- ensure no backup files or local instance artifacts remain in the tree
- keep README/DESIGN honest about current heuristics and limitations

## Safety rule

Do not weaken preview redaction or broaden write detection semantics without adding or updating tests.
