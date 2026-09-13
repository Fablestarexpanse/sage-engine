"""Dependency license report and policy (scripts/license_report.py)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "license_report.py"


@pytest.fixture(scope="module")
def lic():
    spec = importlib.util.spec_from_file_location("license_report", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["license_report"] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("MIT", "permissive"),
        ("Apache-2.0 OR MIT", "permissive"),
        ("MIT AND GPL-3.0", "strong"),
        ("(MIT OR GPL-2.0-only)", "permissive"),
        ("(MIT OR Apache-2.0) AND MPL-2.0", "weak"),
        ("LGPL-2.1+", "weak"),
        ("MIT/X11", "permissive"),
        ("Apache Software License", "permissive"),
        ("EPL-2.0", "weak"),
        ("Apache-2.0 WITH LLVM-exception", "permissive"),
        ("GPL-2.0 WITH Classpath-exception-2.0", "weak"),
        ("AGPL-3.0-or-later", "strong"),
        ("Some Custom Terms", "unknown"),
        ("", "unknown"),
        (None, "unknown"),
    ],
)
def test_classify_expressions(lic, expression, expected):
    assert lic.classify(expression) == expected


class _FakeMeta:
    def __init__(self, fields: dict[str, str], classifiers: list[str]):
        self._fields = fields
        self._classifiers = classifiers

    def get(self, key, default=None):
        return self._fields.get(key, default)

    def get_all(self, key, default=None):
        return self._classifiers if key == "Classifier" else default


def test_python_metadata_prefers_expression_then_classifiers(lic):
    expr = _FakeMeta({"License-Expression": "BSD-3-Clause", "License": "MIT"}, [])
    assert lic.python_license(expr) == "BSD-3-Clause"
    short = _FakeMeta({"License": "Apache 2.0"}, [])
    assert lic.python_license(short) == "Apache 2.0"
    full_text = _FakeMeta(
        {"License": "Permission is hereby granted... " * 20},
        ["License :: OSI Approved :: MIT License"],
    )
    assert lic.python_license(full_text) == "MIT License"
    nothing = _FakeMeta({}, [])
    assert lic.python_license(nothing) is None


def test_npm_lock_collects_dev_flags(lic, tmp_path):
    lock = tmp_path / "app" / "package-lock.json"
    lock.parent.mkdir()
    lock.write_text(
        json.dumps(
            {
                "lockfileVersion": 3,
                "packages": {
                    "": {"name": "app", "license": "SEE LICENSE IN ../x"},
                    "node_modules/react": {"license": "MIT"},
                    "node_modules/vite": {"license": "MIT", "dev": True},
                    "node_modules/a/node_modules/b": {"license": "ISC"},
                },
            }
        ),
        encoding="utf-8",
    )
    deps = lic.collect_npm(lock)
    by_name = {d.name: d for d in deps}
    assert set(by_name) == {"react", "vite", "b"}
    assert by_name["vite"].dev is True
    assert by_name["react"].dev is False
    assert by_name["b"].source == "app"


def test_policy_fails_strong_and_unknown_unless_allowlisted(lic):
    deps = [
        lic.Dependency("npm", "ok", "1", "MIT", False, "app"),
        lic.Dependency("npm", "copyleft", "1", "GPL-3.0", False, "app"),
        lic.Dependency("python", "mystery", "1", None, False, "requirements.lock"),
        lic.Dependency("npm", "devtool", "1", "GPL-3.0", True, "app"),
        lic.Dependency("npm", "weakling", "1", "MPL-2.0", False, "app"),
    ]
    violations = lic.policy_violations(deps, allow=set())
    assert sorted(d.name for d in violations) == ["copyleft", "mystery"]
    allowed = lic.policy_violations(deps, allow={("npm", "copyleft"), ("python", "mystery")})
    assert allowed == []
