"""The architecture's own test: the dependency rule enforced, not merely written down.

Adding a module fails this suite until the layer map below says where it belongs. That
is deliberate — the map in ARCHITECTURE.md is a contract, and a contract nobody checks
drifts. The import allowlist doubles as the standing check for G2 and G4: a dependency
on the application, or a fifth runtime dependency, cannot arrive unnoticed.
"""

import ast
import re
import sys
import tomllib
from pathlib import Path

import pytest
from conftest import assert_names_no_problem_domain

PACKAGE = Path(__file__).resolve().parent.parent
SRC = PACKAGE / "src" / "bdheal"
MANIFEST = PACKAGE / "pyproject.toml"

ENTITIES, USE_CASES, ADAPTERS, DRIVERS = 0, 1, 2, 3

LAYER: dict[str, int] = {
    "models": ENTITIES,
    "vocabulary": ENTITIES,
    "errors": ENTITIES,
    "skeleton": ENTITIES,
    "bench.mutate": ENTITIES,
    "bench.metrics": ENTITIES,
    "ports": USE_CASES,
    "detect": USE_CASES,
    "diagnose": USE_CASES,
    "heal": USE_CASES,
    "verify": USE_CASES,
    "healer": USE_CASES,
    "bench.runner": USE_CASES,
    "studio": ADAPTERS,
    "store": ADAPTERS,
    "clock": DRIVERS,
    "process": DRIVERS,
    "__init__": DRIVERS,
    "bench.__init__": DRIVERS,
}

RUNTIME_DEPENDENCIES = frozenset({"lxml", "pydantic", "selectolax"})
DEV_DEPENDENCIES = frozenset({"pytest", "pytest-cov"})
ALLOWED_ROOTS = RUNTIME_DEPENDENCIES | set(sys.stdlib_module_names) | {"bdheal"}


def _key(path: Path) -> str:
    """The layer-map key for a source file: `bench/runner.py` becomes `bench.runner`."""
    return ".".join(path.relative_to(SRC).with_suffix("").parts)


def _modules() -> dict[str, ast.Module]:
    """Every shipped module, parsed."""
    return {_key(path): ast.parse(path.read_text()) for path in sorted(SRC.rglob("*.py"))}


def _imports(tree: ast.Module) -> set[str]:
    """Every module name the file imports, exactly as written."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _declared(requirements: list[str]) -> set[str]:
    """The bare distribution names from a list of PEP 508 requirement strings."""
    return {re.split(r"[^A-Za-z0-9._-]", requirement, maxsplit=1)[0] for requirement in requirements}


def _manifest() -> dict:
    """The package manifest, parsed."""
    return tomllib.loads(MANIFEST.read_text())


def _resolve(imported: str) -> str:
    """Map an imported `bdheal.*` name onto its layer-map key."""
    target = imported.removeprefix("bdheal").removeprefix(".")
    if not target:
        return "__init__"
    return target if target in LAYER else f"{target}.__init__"


def test_every_module_is_assigned_a_layer() -> None:
    """A module with no layer is a module nobody decided the shape of."""
    assert set(_modules()) == set(LAYER)


def test_dependencies_point_inward() -> None:
    """Outer layers may know about inner ones. Never the reverse."""
    for name, tree in _modules().items():
        for imported in _imports(tree):
            if not imported.startswith("bdheal"):
                continue
            target = _resolve(imported)
            assert target in LAYER, f"{name} imports unknown module {imported}"
            assert LAYER[target] <= LAYER[name], f"{name} reaches outward into {target}"


def test_no_dependency_outside_the_declared_runtime_set() -> None:
    """Runtime dependencies are exactly the ones declared in the manifest (G2, G4)."""
    for name, tree in _modules().items():
        for imported in _imports(tree):
            root = imported.split(".")[0]
            assert root in ALLOWED_ROOTS, f"{name} imports undeclared dependency {imported}"


def test_manifest_declares_exactly_the_runtime_dependencies() -> None:
    """G4: thin by contract. A further runtime dependency is argued for here or not at all."""
    assert _declared(_manifest()["project"]["dependencies"]) == RUNTIME_DEPENDENCIES


def test_manifest_declares_exactly_the_dev_dependencies() -> None:
    """G4: pytest and coverage only — no mock library, no HTTP recorder."""
    assert _declared(_manifest()["dependency-groups"]["dev"]) == DEV_DEPENDENCIES


def test_no_call_passes_shell() -> None:
    """argv is a list and there is no shell anywhere in the package (G3)."""
    for name, tree in _modules().items():
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                keywords = {keyword.arg for keyword in node.keywords}
                assert "shell" not in keywords, f"{name} passes a shell argument"


def _sources() -> dict[str, str]:
    """Every shipped module's text, keyed the same way as `_modules()`."""
    return {_key(path): path.read_text() for path in sorted(SRC.rglob("*.py"))}


@pytest.mark.parametrize("name", sorted(_sources()))
def test_no_module_names_the_problem_domain(name: str) -> None:
    """Corpus-agnostic by construction, enforced across the whole package.

    This lived in three feature test files with two different predicates, covering three
    of nineteen modules. One rule, every module, or the bar drifts wherever nobody looked.
    """
    assert_names_no_problem_domain(_sources()[name])


@pytest.mark.parametrize("name", sorted(_sources()))
def test_no_module_reads_the_environment(name: str) -> None:
    """G6: credentials reach `bdata` through the inherited environment, never this code.

    A module that reads the environment could copy a token into a prompt, a log line or a
    persisted heal event. This was asserted for `diagnose.py` alone; it is true of all of
    them, and the one that eventually breaks it will not be the one someone tested.

    Matches the *access*, not the word: `"environ"` is a substring of `"environment"`, so
    a docstring mentioning the inherited environment would fail with a misleading message.
    """
    source = _sources()[name]
    for reader in ("os.environ", "environ[", "environ.get", "getenv("):
        assert reader not in source, f"{name} reads the environment via {reader}"
