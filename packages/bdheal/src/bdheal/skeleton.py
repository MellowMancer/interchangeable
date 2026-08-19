"""The structural fingerprint of a page: the tag and class tree, every word stripped out.

Text changes daily and structure does not, so hashing the skeleton separates "the page
said something new" from "the page was rebuilt". Pure and deterministic — the same HTML
gives the same digest in any process, which is what makes it a golden-test subject.
"""

import hashlib

from selectolax.parser import HTMLParser, Node

# selectolax names text, comment and undefined nodes with these pseudo-tags.
NON_ELEMENT_TAGS = frozenset({"-text", "_comment", "-undef"})


def skeleton(html: str) -> str:
    """The normalised tag and class tree of `html`, with text and other attributes dropped."""
    return _render(HTMLParser(html).root)


def skeleton_hash(html: str) -> str:
    """Stable hex digest of `skeleton(html)`. A text-only edit leaves it unchanged."""
    return hashlib.sha256(skeleton(html).encode("utf-8")).hexdigest()


def _render(node: Node) -> str:
    """One element as `tag.class(children)`; nesting and sibling order carry through."""
    children = (child for child in node.iter() if child.tag not in NON_ELEMENT_TAGS)
    return f"{node.tag}{_classes(node)}({''.join(_render(child) for child in children)})"


def _classes(node: Node) -> str:
    """The element's classes, sorted because CSS treats them as a set, not a sequence."""
    return "".join(f".{name}" for name in sorted((node.attributes.get("class") or "").split()))
