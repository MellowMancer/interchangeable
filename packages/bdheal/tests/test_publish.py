"""Proof that `bdheal` installs for somebody who does not have this repository.

The package claims to be independently publishable, and the workspace lockfile cannot
support that claim: a lock pins one resolution for one application, whereas a library
has to resolve from its declared ranges on a machine that has never seen this checkout.
So the check is a clean room — build the artifacts, install the wheel into an empty
interpreter, and confirm the workspace is nowhere on that interpreter's `sys.path`.

It builds and downloads, so it is gated behind `BDHEAL_PUBLISH_CHECK=1` and never runs
in the isolation suite (G1).
"""

import json
import os
import subprocess
from pathlib import Path

import pytest

import bdheal

PACKAGE = Path(__file__).resolve().parent.parent
REPO_ROOT = PACKAGE.parent.parent
PYTHON_VERSION = "3.12"
STEP_TIMEOUT_S = 600

CLEAN_ROOM_PROBE = """
import json, pathlib, sys
import bdheal
print(json.dumps({
    "version": bdheal.__version__,
    "all": bdheal.__all__,
    "file": bdheal.__file__,
    "path": [str(pathlib.Path(entry or ".").resolve()) for entry in sys.path],
}))
"""

pytestmark = pytest.mark.publish


def _run(argv: list[str], cwd: Path | None = None) -> str:
    """Run one step of the clean-room build, failing the test with its output if it errors."""
    environment = {name: value for name, value in os.environ.items() if name != "VIRTUAL_ENV"}
    step = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=STEP_TIMEOUT_S,
        cwd=cwd,
        env=environment,
    )
    assert step.returncode == 0, f"{argv[0]} {argv[1]} failed:\n{step.stderr}"
    return step.stdout


def test_the_wheel_installs_into_an_interpreter_that_cannot_see_this_repo(tmp_path: Path) -> None:
    """Built and resolved from declared ranges alone, the package imports on its own."""
    _run(["uv", "build", str(PACKAGE), "--out-dir", str(tmp_path)])
    wheels = list(tmp_path.glob("bdheal-*.whl"))
    assert len(wheels) == 1, wheels
    assert len(list(tmp_path.glob("bdheal-*.tar.gz"))) == 1
    assert not (PACKAGE / "dist").exists(), "build artifacts must not land in the repo"

    clean_room = tmp_path / "clean-room"
    _run(["uv", "venv", "--python", PYTHON_VERSION, str(clean_room)])
    python = clean_room / "bin" / "python"
    _run(["uv", "pip", "install", "--python", str(python), str(wheels[0])])

    probe = json.loads(_run([str(python), "-c", CLEAN_ROOM_PROBE], cwd=tmp_path))
    assert probe["version"] == bdheal.__version__
    assert probe["all"] == bdheal.__all__
    assert Path(probe["file"]).is_relative_to(clean_room)
    assert not [entry for entry in probe["path"] if Path(entry).is_relative_to(REPO_ROOT)]
