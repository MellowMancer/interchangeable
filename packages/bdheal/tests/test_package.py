"""The package skeleton itself: it imports standalone and it names a real version.

`__version__` is the manifest's version source (`[tool.hatch.version]`), so a value the
packaging tools would reject is a broken wheel, not a cosmetic slip.
"""

import re

import bdheal

PEP_440_PUBLIC_VERSION = re.compile(
    r"^([1-9][0-9]*!)?(0|[1-9][0-9]*)(\.(0|[1-9][0-9]*))*"
    r"((a|b|rc)(0|[1-9][0-9]*))?(\.post(0|[1-9][0-9]*))?(\.dev(0|[1-9][0-9]*))?$"
)


def test_version_is_a_pep_440_release() -> None:
    """The version hatchling reads from `__init__.py` is one the packaging tools accept."""
    assert PEP_440_PUBLIC_VERSION.match(bdheal.__version__), bdheal.__version__
