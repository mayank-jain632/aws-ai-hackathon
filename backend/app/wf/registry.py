"""Component registry: names or ``package.module:ClassName`` -> checked instances (hub D22)."""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any, Literal

from backend.app.wf.interfaces import ComponentSpec, Decider, Evaluator, ExecutionPolicy

Kind = Literal["decider", "execution", "evaluator"]
PROTOCOLS: dict[str, type] = {"decider": Decider, "execution": ExecutionPolicy, "evaluator": Evaluator}
_REGISTRY: dict[str, dict[str, Callable[..., Any]]] = {k: {} for k in PROTOCOLS}


class RegistryError(ValueError):
    pass


def _register(kind: Kind, name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def deco(factory: Callable[..., Any]) -> Callable[..., Any]:
        existing = _REGISTRY[kind].get(name)
        if existing is not None and existing is not factory:
            raise RegistryError(f"{kind} {name!r} is already registered")
        _REGISTRY[kind][name] = factory
        return factory

    return deco


def register_decider(name: str):
    return _register("decider", name)


def register_execution(name: str):
    return _register("execution", name)


def register_evaluator(name: str):
    return _register("evaluator", name)


def known(kind: Kind) -> list[str]:
    _check_kind(kind)
    return sorted(_REGISTRY[kind])


def _check_kind(kind: str) -> None:
    if kind not in PROTOCOLS:
        raise RegistryError(f"unknown component kind {kind!r}; expected one of {sorted(PROTOCOLS)}")


def _import_ref(ref: str) -> Callable[..., Any]:
    module, _, attr = ref.partition(":")
    if not module or not attr:
        raise RegistryError(f"bad component ref {ref!r}; use 'package.module:ClassName'")
    try:
        return getattr(importlib.import_module(module), attr)
    except ImportError as exc:
        raise RegistryError(f"cannot import module {module!r} for ref {ref!r}: {exc}") from exc
    except AttributeError as exc:
        raise RegistryError(f"module {module!r} has no attribute {attr!r}") from exc


def _factory(kind: Kind, ref: str) -> Callable[..., Any]:
    if ":" in ref:
        return _import_ref(ref)
    try:
        return _REGISTRY[kind][ref]
    except KeyError:
        raise RegistryError(
            f"unknown {kind} {ref!r}; registered: {known(kind) or 'none'} "
            "(or use 'package.module:ClassName')"
        ) from None


def resolve(kind: Kind, spec: ComponentSpec) -> Any:
    """Build the component named by ``spec`` and check it against the kind's Protocol."""
    _check_kind(kind)
    factory = _factory(kind, spec.ref)
    try:
        instance = factory(**spec.params)
    except TypeError as exc:
        raise RegistryError(f"cannot build {kind} {spec.ref!r} with params {spec.params}: {exc}") from exc
    if not isinstance(instance, PROTOCOLS[kind]):
        raise RegistryError(
            f"{kind} {spec.ref!r} produced {type(instance).__name__}, which does not satisfy "
            f"the {PROTOCOLS[kind].__name__} protocol"
        )
    return instance
