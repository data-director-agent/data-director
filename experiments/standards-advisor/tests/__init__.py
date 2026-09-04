"""Test package.

A package rather than loose modules so `from tests.fakes import ...` resolves the same way for
pytest and for mypy, and so two test modules cannot collide on a basename.
"""
