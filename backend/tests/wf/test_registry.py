from __future__ import annotations

import pytest

from backend.app.wf import registry
from backend.app.wf.interfaces import ComponentSpec
from backend.tests.wf import harness_stubs  # noqa: F401 registers t_* components

STUBS = "backend.tests.wf.harness_stubs"


def test_resolves_registered_names_with_params() -> None:
    d = registry.resolve("decider", ComponentSpec(ref="t_const", params={"weights": {"A": 1.0}}))
    assert d.weights == {"A": 1.0}
    assert registry.resolve("execution", ComponentSpec(ref="t_drift", params={"threshold": 0.1})).threshold == 0.1


def test_resolves_module_class_without_registration() -> None:
    d = registry.resolve("decider", ComponentSpec(ref=f"{STUBS}:ConstDecider", params={"weights": {}}))
    assert type(d).__name__ == "ConstDecider"


def test_known_lists_registered_names() -> None:
    assert {"t_const", "t_stateful"} <= set(registry.known("decider"))
    assert "t_drift" in registry.known("execution")


def test_unknown_name_error_lists_known_names() -> None:
    with pytest.raises(registry.RegistryError, match="t_const"):
        registry.resolve("decider", ComponentSpec(ref="nope"))


def test_rejects_non_conforming_class_and_bad_refs() -> None:
    with pytest.raises(registry.RegistryError, match="protocol"):
        registry.resolve("decider", ComponentSpec(ref=f"{STUBS}:NotAComponent"))
    with pytest.raises(registry.RegistryError, match="no attribute"):
        registry.resolve("decider", ComponentSpec(ref=f"{STUBS}:Missing"))
    with pytest.raises(registry.RegistryError, match="cannot import"):
        registry.resolve("decider", ComponentSpec(ref="no.such.module:X"))
    with pytest.raises(registry.RegistryError, match="bad component ref"):
        registry.resolve("decider", ComponentSpec(ref="pkg:"))


def test_wrong_kind_instance_rejected_and_bad_params_reported() -> None:
    with pytest.raises(registry.RegistryError, match="protocol"):
        registry.resolve("execution", ComponentSpec(ref=f"{STUBS}:ConstDecider", params={"weights": {}}))
    with pytest.raises(registry.RegistryError, match="cannot build"):
        registry.resolve("decider", ComponentSpec(ref="t_const", params={"bogus": 1}))


def test_duplicate_registration_with_different_factory_is_refused() -> None:
    with pytest.raises(registry.RegistryError, match="already registered"):
        registry.register_decider("t_const")(lambda **kw: None)
