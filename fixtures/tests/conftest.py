"""Gating for the checks that reach the network. The default run is offline."""

import os

import pytest

PAGES_URL = "BDHEAL_PAGES_URL"


def pytest_runtest_setup(item: pytest.Item) -> None:
    """Skip the deployed-site checks unless a published base URL says where to look."""
    if "pages" in item.keywords and not os.environ.get(PAGES_URL):
        pytest.skip(f"set {PAGES_URL}=https://<owner>.github.io/<repo> to read the deployed site")
