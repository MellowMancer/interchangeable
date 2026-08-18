"""The structural fingerprint of a page: the tag and class tree, every word stripped out.

Text changes daily and structure does not, so hashing the skeleton separates "the page
said something new" from "the page was rebuilt". Pure and deterministic — the same HTML
gives the same digest in any process, which is what makes it a golden-test subject.
"""


def skeleton(html: str) -> str:
    """The normalised tag and class tree of `html`, with text and other attributes dropped."""
    raise NotImplementedError


def skeleton_hash(html: str) -> str:
    """Stable hex digest of `skeleton(html)`. A text-only edit leaves it unchanged."""
    raise NotImplementedError
