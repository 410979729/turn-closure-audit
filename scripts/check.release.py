from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.1.0"
WHEEL_NAME = f"turn_closure_audit-{VERSION}-py3-none-any.whl"
REQUIRED_ROOT_FILES = [
    "README.md",
    "DESIGN.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "SECURITY.md",
    "plugin.yaml",
    "pyproject.toml",
]
REQUIRED_MODULES = [
    "__init__.py",
    "runtime.py",
    "paths.py",
    "redaction.py",
    "events.py",
    "classification.py",
    "storage.py",
    "commands.py",
    "candidate_schema.py",
    "candidate_ledger.py",
    "receipts.py",
    "promotion.py",
    "distillation.py",
    "clock.py",
]
REQUIRED_DOCS = ["docs/architecture.md", "docs/memory.stack.contract.md"]
GENERATED_NAMES = {"__pycache__", ".pytest_cache", ".ruff_cache", "build", "dist", "turn_closure_audit.egg-info"}
SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|token|password|passwd|authorization|bearer)\s*[:=]\s*(?!\$\{|public-test|\[REDACTED\])[A-Za-z0-9._~+/-]{12,}"),
]


def fail(msg: str, details=None):
    print(json.dumps({"ok": False, "error": msg, "details": details}, ensure_ascii=False, indent=2))
    raise SystemExit(1)


def run(cmd, **kwargs):
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, **kwargs)


def scan_generated():
    found = []
    for p in ROOT.rglob("*"):
        rel = p.relative_to(ROOT).as_posix()
        if any(part in GENERATED_NAMES or part.endswith(".egg-info") for part in p.relative_to(ROOT).parts):
            found.append(rel)
        elif p.suffix == ".pyc":
            found.append(rel)
    return sorted(set(found))


def scan_secrets():
    hits = []
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(ROOT).as_posix()
        if any(part in GENERATED_NAMES or part.startswith(".git") for part in p.relative_to(ROOT).parts):
            continue
        if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".whl"}:
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        for rx in SECRET_PATTERNS:
            for m in rx.finditer(text):
                hits.append({"file": rel, "match": m.group(0)[:120]})
    return hits


def main():
    missing = [f for f in REQUIRED_ROOT_FILES + REQUIRED_MODULES + REQUIRED_DOCS if not (ROOT / f).exists()]
    if missing:
        fail("missing required release files", missing)

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    plugin_yaml = (ROOT / "plugin.yaml").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    design = (ROOT / "DESIGN.md").read_text(encoding="utf-8")
    if f'version = "{VERSION}"' not in pyproject or f"version: {VERSION}" not in plugin_yaml:
        fail("version metadata mismatch", {"expected": VERSION})
    if "Development Status :: 5 - Production/Stable" not in pyproject:
        fail("pyproject classifier is not stable")
    if "main runtime implementation still lives in a single" in readme + design:
        fail("docs still claim monolithic runtime implementation")
    for module in REQUIRED_MODULES[1:]:
        if module not in readme + design:
            fail("docs do not mention extracted module", module)

    generated_before = scan_generated()
    if generated_before:
        fail("generated artifacts present before release check", generated_before[:50])
    secrets = scan_secrets()
    if secrets:
        fail("possible secret-like literals found", secrets)

    test = run([sys.executable, "-m", "pytest", "-q"], timeout=120)
    if test.returncode != 0:
        fail("pytest failed", {"stdout": test.stdout, "stderr": test.stderr})

    build = run([sys.executable, "-m", "build", "--wheel"], timeout=120)
    if build.returncode != 0:
        fail("wheel build failed", {"stdout": build.stdout, "stderr": build.stderr})

    wheel = ROOT / "dist" / WHEEL_NAME
    if not wheel.exists():
        fail("expected wheel missing", str(wheel))

    with zipfile.ZipFile(wheel) as zf:
        names = zf.namelist()
    def has_payload(expected: str) -> bool:
        return expected in names or any(name.endswith('/' + expected) for name in names)
    bad_wheel = [name for name in names if "__pycache__" in name or name.endswith(".pyc")]
    if bad_wheel:
        fail("wheel contains cache artifacts", bad_wheel)
    for expected in ["turn_closure_audit/__init__.py", "turn_closure_audit/runtime.py", "turn_closure_audit/candidate_schema.py", "turn_closure_audit/candidate_ledger.py", "turn_closure_audit/promotion.py", "turn_closure_audit/receipts.py", "turn_closure_audit/distillation.py", "plugin.yaml", "README.md", "DESIGN.md", "CHANGELOG.md", "SECURITY.md", "docs/architecture.md", "docs/memory.stack.contract.md"]:
        if not has_payload(expected):
            fail("wheel missing expected payload", expected)

    with tempfile.TemporaryDirectory() as td:
        install = run([sys.executable, "-m", "pip", "install", "--quiet", "--target", td, str(wheel)], timeout=120)
        if install.returncode != 0:
            fail("temp wheel install failed", {"stdout": install.stdout, "stderr": install.stderr})
        smoke = subprocess.run(
            [sys.executable, "-c", "import sys; sys.path.insert(0, r'%s'); import turn_closure_audit as t; print(hasattr(t, 'register'), hasattr(t, 'safe_session_filename'))" % td],
            text=True,
            capture_output=True,
            timeout=30,
        )
        if smoke.returncode != 0 or "True True" not in smoke.stdout:
            fail("temp import smoke failed", {"stdout": smoke.stdout, "stderr": smoke.stderr})

    # Leave the source tree review-clean after validation.
    for name in ["build", "dist", "turn_closure_audit.egg-info", ".pytest_cache"]:
        shutil.rmtree(ROOT / name, ignore_errors=True)
    for p in ROOT.rglob("__pycache__"):
        shutil.rmtree(p, ignore_errors=True)
    for p in ROOT.rglob("*.pyc"):
        p.unlink(missing_ok=True)

    print(json.dumps({"ok": True, "version": VERSION, "tests": test.stdout.strip(), "wheel": WHEEL_NAME}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
