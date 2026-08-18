"""The only place this package starts an operating-system process."""

import subprocess

from bdheal.ports import ProcessResult


class SubprocessRunner:
    """Runs argv with `subprocess.run`. No shell, ever (G3).

    A non-zero exit is returned, not raised: the caller reads `bdata`'s JSON on stderr
    to build a typed error, which a `CalledProcessError` would throw away.
    """

    def __call__(self, argv: list[str], timeout_s: int) -> ProcessResult:
        """Run `argv` to completion, or raise `subprocess.TimeoutExpired`."""
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        return ProcessResult(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
