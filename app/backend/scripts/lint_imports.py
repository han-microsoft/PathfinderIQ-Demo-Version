#!/usr/bin/env python3
"""Import hierarchy lint — enforces the layered dependency rule.

Usage:
    python3 scripts/lint_imports.py           # Check all, exit 1 on violations
    python3 scripts/lint_imports.py --fix     # Not implemented yet — just reports

Rules enforced:
    1. tools/ must NOT import from app.services or app.routers
    2. tools/ must NOT import from agents/
    3. foundation/ must NOT import from app.* (except app.foundation.*)
    4. services/ must NOT import from app.routers
    5. agents/ must NOT import from app.routers

These rules prevent the cross-layer dependency violations that make the
codebase fragile to change. Violations are reported with file:line detail.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# ── Rules ────────────────────────────────────────────────────────────────────
# Each rule:  (glob pattern for files to check, forbidden import regex, description)

RULES = [
    # Rule 1: tools/ must not import from app.services or app.routers
    (
        "tools/**/*.py",
        re.compile(r"^\s*from\s+app\.(?:services|routers)[\s.]", re.MULTILINE),
        "tools/ must not import from app.services or app.routers",
    ),
    # Rule 2: tools/ must not import from agents/ (except delegation tool)
    (
        "tools/**/*.py",
        re.compile(r"^\s*from\s+agents[\s.]|^\s*import\s+agents[\s.]", re.MULTILINE),
        "tools/ must not import from agents/",
    ),
    # Rule 3: foundation/ must not import from app.* (except app.foundation.*)
    (
        "app/foundation/**/*.py",
        re.compile(r"^\s*from\s+app\.(?!foundation[\s.])[\w.]+", re.MULTILINE),
        "foundation/ must not import from app.* (except app.foundation.*)",
    ),
    # Rule 4: services/ must not import from app.routers
    (
        "app/services/**/*.py",
        re.compile(r"^\s*from\s+app\.routers[\s.]", re.MULTILINE),
        "services/ must not import from app.routers",
    ),
    # Rule 5: agents/ must not import from app.routers
    (
        "agents/**/*.py",
        re.compile(r"^\s*from\s+app\.routers[\s.]", re.MULTILINE),
        "agents/ must not import from app.routers",
    ),
]

# ── Accepted exceptions ──────────────────────────────────────────────────────
# Files that are allowed to violate specific rules. Each entry maps a file
# suffix (matched against the end of the filepath) to a set of rule
# descriptions that are suppressed for that file.
#
# Why: tools/delegation/__init__.py imports from agents (AgentRegistry) because
# the delegation tool builds and runs specialist agents by design.

EXCEPTIONS: dict[str, set[str]] = {
    "tools/delegation/__init__.py": {
        "tools/ must not import from agents/",
    },
}


def lint_file(filepath: Path, pattern: re.Pattern, description: str) -> list[str]:
    """Check a single file for import violations.

    Skips comments and lines inside docstrings (triple-quote blocks).

    Args:
        filepath: Path to the Python file to check.
        pattern: Compiled regex matching forbidden imports.
        description: Human-readable rule description for error messages.

    Returns:
        List of violation strings (empty if clean).
    """
    violations = []
    try:
        text = filepath.read_text(encoding="utf-8")
    except Exception:
        return []  # Skip unreadable files

    in_docstring = False
    for i, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip()
        # Track docstring boundaries (triple quotes)
        triple_count = stripped.count('"""') + stripped.count("'''")
        if triple_count >= 2:
            # Opens and closes on the same line — skip this line
            continue
        if triple_count == 1:
            in_docstring = not in_docstring
            continue
        if in_docstring:
            continue
        # Skip comments
        if stripped.startswith("#"):
            continue
        if pattern.match(line):
            violations.append(f"  {filepath}:{i}  {stripped.strip()}")
    return violations


def main() -> int:
    """Run all lint rules and report violations.

    Returns:
        0 if clean, 1 if violations found.
    """
    backend_root = Path(__file__).resolve().parents[1]

    total_violations = 0
    for glob_pattern, regex, description in RULES:
        files = sorted(backend_root.glob(glob_pattern))
        # Exclude __pycache__ and .venv
        files = [
            f for f in files
            if "__pycache__" not in str(f) and ".venv" not in str(f)
        ]
        rule_violations: list[str] = []
        for filepath in files:
            # Check if this file has an exception for this rule
            rel = str(filepath.relative_to(backend_root))
            excepted_rules = EXCEPTIONS.get(rel, set())
            if description in excepted_rules:
                continue
            rule_violations.extend(lint_file(filepath, regex, description))

        if rule_violations:
            print(f"\n❌ RULE: {description}")
            for v in rule_violations:
                print(v)
            total_violations += len(rule_violations)

    if total_violations:
        print(f"\n{total_violations} import hierarchy violation(s) found.")
        return 1
    else:
        print("✓ Import hierarchy clean — no violations.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
