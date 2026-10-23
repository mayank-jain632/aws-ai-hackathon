"""Adapters that plug existing and teammate components into the wf contracts (hub D22).

Importing this package registers every built-in component in `backend.app.wf.registry`
(when that module exists).
"""

from backend.app.wf.adapters import deciders, evaluators, executions  # noqa: F401
