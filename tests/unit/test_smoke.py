"""Smoke test — verifies kris package imports successfully."""

import kris


def test_package_imports():
    assert kris.__doc__ is not None
