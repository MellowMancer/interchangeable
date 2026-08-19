"""The structural fingerprint, pinned to literal goldens.

Two halves, and the second is the load-bearing one. First: structure moves the digest —
a renamed class, a swapped tag, reordered siblings. Second: nothing else does. Text,
attribute values, whitespace, comments and attribute order all leave it exactly where it
was, because three of the nine benchmark mutation classes are text or attribute edits
that this detector is *supposed* to miss (resolved decision Q2). Widening the hash to
catch them would break `bench/mutate.py`'s declared expectations, not improve detection.

The golden digest is a literal so that a change in parser, platform or Python version
shows up here rather than as a silently different baseline in production.
"""

import hashlib

from bdheal.skeleton import skeleton, skeleton_hash

GOLDEN_HTML = """<!DOCTYPE html>
<html>
  <body>
    <div class="listing">
      <h2 class="title">Alpha listing</h2>
      <ul class="rows">
        <li class="row"><a class="link" href="/a">Alpha</a></li>
        <li class="row"><a class="link" href="/b">Beta</a></li>
      </ul>
    </div>
  </body>
</html>
"""
GOLDEN_SKELETON = "html(head()body(div.listing(h2.title()ul.rows(li.row(a.link())li.row(a.link())))))"
GOLDEN_HASH = "00fb71907ac61887f8f9a2a475ce32aa411aa5a5f46d7253f14e1e0f3d1e200b"

# Same tree, different words: the whole page's visible text replaced.
RETEXTED_HTML = """<!DOCTYPE html>
<html>
  <body>
    <div class="listing">
      <h2 class="title">Omega listing</h2>
      <ul class="rows">
        <li class="row"><a class="link" href="/a">Gamma</a></li>
        <li class="row"><a class="link" href="/b">Delta &mdash; revised</a></li>
      </ul>
    </div>
  </body>
</html>
"""
RENAMED_CLASS_HTML = GOLDEN_HTML.replace('class="row"', 'class="record"')

# Identical classes and identical text, so only the tag rebuild can move the digest.
TABLE_HTML = '<table class="rows"><tr class="row"><td class="cell">Alpha</td></tr></table>'
DIV_HTML = '<div class="rows"><div class="row"><div class="cell">Alpha</div></div></div>'

ORDERED_COLUMNS_HTML = '<ul class="rows"><li class="name"></li><li class="date"></li></ul>'
REORDERED_COLUMNS_HTML = '<ul class="rows"><li class="date"></li><li class="name"></li></ul>'

COMPACT_HTML = '<div class="listing"><p class="row">Alpha</p></div>'
NOISY_VARIANTS = {
    "whitespace": '<div  class="listing" >\n\t<p class="row">\n  Alpha\n</p>\n</div>\n',
    "comments": '<!-- build 41 --><div class="listing"><p class="row">Alpha<!-- cell --></p></div>',
    "attribute_order": '<div id="main" class="listing" data-x="1"><p class="row" id="r1">Alpha</p></div>',
}

# The three non-structural mutation classes of ARCHITECTURE.md §12, which must not move it.
LINKED_ROW_HTML = '<li class="row"><a class="link" href="/records/1">Read more</a><span class="date">2026-01-01</span></li>'
NON_STRUCTURAL_VARIANTS = {
    "link_label": LINKED_ROW_HTML.replace("Read more", "View record"),
    "url_pattern": LINKED_ROW_HTML.replace('href="/records/1"', 'href="/r/1?ref=list"'),
    "date_format": LINKED_ROW_HTML.replace("2026-01-01", "01 Jan 2026"),
}


def test_skeleton_is_the_tag_and_class_tree() -> None:
    """Tags, classes and nesting survive; text and every other attribute do not."""
    assert skeleton(GOLDEN_HTML) == GOLDEN_SKELETON


def test_hash_is_the_same_constant_in_every_interpreter_run() -> None:
    """A literal digest, so process-to-process drift fails here instead of in a baseline."""
    assert skeleton_hash(GOLDEN_HTML) == GOLDEN_HASH
    assert GOLDEN_HASH == hashlib.sha256(GOLDEN_SKELETON.encode("utf-8")).hexdigest()


def test_changing_visible_text_leaves_the_hash_unchanged() -> None:
    """Copy changes daily; the collector still works. Text must not read as a break."""
    assert skeleton_hash(RETEXTED_HTML) == GOLDEN_HASH


def test_renaming_a_class_changes_the_hash() -> None:
    """A renamed hook is the commonest way a selector-based collector dies."""
    assert skeleton_hash(RENAMED_CLASS_HTML) != GOLDEN_HASH


def test_changing_a_tag_changes_the_hash() -> None:
    """`<table>` to `<div>` is a rebuild, whatever the classes say."""
    assert skeleton_hash(TABLE_HTML) != skeleton_hash(DIV_HTML)


def test_reordering_siblings_changes_the_hash() -> None:
    """Document order is structure: a column swap moves every positional selector."""
    assert skeleton_hash(ORDERED_COLUMNS_HTML) != skeleton_hash(REORDERED_COLUMNS_HTML)


def test_whitespace_comments_and_attribute_order_leave_the_hash_unchanged() -> None:
    """Formatting noise and build-stamp comments are not layout changes."""
    baseline = skeleton_hash(COMPACT_HTML)
    for name, variant in NOISY_VARIANTS.items():
        assert skeleton_hash(variant) == baseline, name


def test_non_structural_mutations_leave_the_hash_unchanged() -> None:
    """Q2: link label, URL pattern and date format are other detectors' work, not this one's."""
    baseline = skeleton_hash(LINKED_ROW_HTML)
    for name, variant in NON_STRUCTURAL_VARIANTS.items():
        assert skeleton_hash(variant) == baseline, name
