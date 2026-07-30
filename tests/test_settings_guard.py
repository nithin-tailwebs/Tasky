"""Proves the DJANGO_SECRET_KEY production guard in config/settings.py.

Settings are loaded once per process by Django's app registry, so the only
clean way to exercise "importing settings under different environments"
is a fresh subprocess per scenario — reload()-ing config.settings in-process
fights the already-initialised app registry and proves nothing.
"""

import os
import subprocess
import sys


def _import_settings(env_overrides: dict, unset: tuple = ()) -> subprocess.CompletedProcess:
    env = {**os.environ, **env_overrides}
    for key in unset:
        env.pop(key, None)
    return subprocess.run(
        [sys.executable, "-c", "import django; django.setup()"],
        env=env,
        capture_output=True,
        text=True,
    )


def test_missing_secret_key_with_debug_false_is_refused():
    """The production-misconfiguration case the guard exists for: no
    DJANGO_SECRET_KEY env var at all (not merely empty — os.environ.get()
    returns None only when the key is truly absent), and DEBUG off. Must
    not silently start up signing sessions with the committed dev-only
    fallback key."""
    result = _import_settings(
        {"DJANGO_SETTINGS_MODULE": "config.settings", "DJANGO_DEBUG": "0"},
        unset=("DJANGO_SECRET_KEY",),
    )

    assert result.returncode != 0
    assert "ImproperlyConfigured" in result.stderr
    assert "DJANGO_SECRET_KEY" in result.stderr


def test_importing_settings_in_the_test_environment_does_not_raise():
    """This repo's actual test environment (docker, DJANGO_DEBUG=1 from
    .env) must not trip the guard — this is what every other test in the
    suite already relies on implicitly by importing config.settings at
    all; this test just makes that assumption explicit and independently
    checkable."""
    result = _import_settings({"DJANGO_SETTINGS_MODULE": "config.settings"})

    assert result.returncode == 0, result.stderr
