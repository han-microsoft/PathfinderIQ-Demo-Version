"""Regression tests for backend imports when OpenTelemetry is unavailable."""

from __future__ import annotations

import builtins
import importlib
import sys


def test_backend_imports_survive_missing_opentelemetry(monkeypatch):
    """Observability and auth modules must import in noop mode without OTel installed."""
    module_names = [
        "app.observability._metrics",
        "app.observability._tracing",
        "app.observability",
        "app.auth",
    ]
    original_import = builtins.__import__

    def _raising_import(name, globals=None, locals=None, fromlist=(), level=0):
        """Simulate an environment where OpenTelemetry packages are absent."""
        if name.startswith("opentelemetry"):
            raise ModuleNotFoundError(name)
        return original_import(name, globals, locals, fromlist, level)

    for module_name in module_names:
        sys.modules.pop(module_name, None)

    monkeypatch.setattr(builtins, "__import__", _raising_import)

    observability = importlib.import_module("app.observability")
    auth = importlib.import_module("app.auth")

    tracer = observability.get_tracer("tests")
    meter = observability.get_meter("tests")

    assert tracer.start_as_current_span("test") is not None
    assert meter.create_counter("counter") is not None
    assert auth.StatusCode.ERROR == "ERROR"


def test_logging_configuration_survives_missing_pythonjsonlogger(monkeypatch):
    """Logging bootstrap must fall back to stdlib formatting when JSON logger is absent."""
    original_import = builtins.__import__

    def _raising_import(name, globals=None, locals=None, fromlist=(), level=0):
        """Simulate an environment where python-json-logger is absent."""
        if name.startswith("pythonjsonlogger"):
            raise ModuleNotFoundError(name)
        return original_import(name, globals, locals, fromlist, level)

    sys.modules.pop("app.observability._logging", None)
    monkeypatch.setattr(builtins, "__import__", _raising_import)

    logging_module = importlib.import_module("app.observability._logging")
    logging_module.configure_json_logging()

    assert logging_module.logging.getLogger().handlers