"""Proof that what GitHub Pages serves is what this repository rendered.

A 200 from every URL says the site is up, not that it is the right site. Pages serves
through a CDN, so reading it within 30-60 seconds of a deploy returns the *previous*
markup — and a collector pointed at stale markup measures nothing while nothing downstream
says so. Comparing the served bytes against the committed ones is what rules that out.

`.nojekyll` is deliberately not fetched: its job is to stop the server from rewriting the
site, so the pages arriving unmodified is the evidence that it worked.

    BDHEAL_PAGES_URL=https://<owner>.github.io/<repo> \
      uv run --package bdheal pytest fixtures/tests -m pages
"""

from __future__ import annotations

import os
import urllib.request

import pytest

from test_golden import SITE

pytestmark = pytest.mark.pages

FETCH_TIMEOUT_S = 30

# Read off the rendered site rather than the manifest: the manifest describes benchmark
# cases, and the site also serves a navigation page that is not one. `.nojekyll` is the one
# exclusion — its job is to stop the server rewriting the site, so the rest of these
# arriving unmodified is the evidence that it worked.
SERVED = sorted(path.name for path in SITE.iterdir() if path.name != ".nojekyll")


@pytest.mark.parametrize("name", SERVED)
def test_served_file_matches_the_committed_one(name: str) -> None:
    """Byte-for-byte, so a CDN still holding the previous deploy fails here and not later."""
    assert _fetch(name) == (SITE / name).read_bytes()


def _fetch(name: str) -> bytes:
    """One file as the public site serves it."""
    base = os.environ["BDHEAL_PAGES_URL"].rstrip("/")
    with urllib.request.urlopen(f"{base}/{name}", timeout=FETCH_TIMEOUT_S) as response:
        return response.read()
