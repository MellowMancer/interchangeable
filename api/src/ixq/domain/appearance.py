"""What a manufacturer says its product looks like, read from §3.

No product photograph of any UK generic in this corpus exists — verified across EMC,
MHRA, dm+d, DailyMed and the manufacturers' own sites. What every label does carry is
§3 *Pharmaceutical form*: the holder's own regulated description of the thing in the
blister. Parsed, it drives a drawing; unparsed, it is still published as prose.

**§3 is product metadata, never a placement.** `Placement` is the vocabulary of the
comparison, and a safety concept cannot be filed in a description of a capsule's colour.
Nothing here is importable as a section a concept was found in, and `SECTION_CODE` is
deliberately not a `Placement` member.
"""

import re
from dataclasses import dataclass
from enum import StrEnum

SECTION_CODE = "3"
"""The publisher's own numbering for the pharmaceutical form.

Kept beside the entity it feeds so storage and the parser name the same section, and so
nothing has to guess the string. It is not in `Placement` and must never be added to it.
"""


class Shape(StrEnum):
    """The outline a glyph can honestly draw, and nothing beyond it.

    Not a dosage form: `product.variant` already reads forms out of product names for a
    different purpose (telling two of one holder's columns apart). This is the *drawn
    outline*, so it exists only where the label states enough to draw one. A label saying
    only "tablet" states no outline — a circle would be our invention — and that product
    is reported as described but not drawn rather than guessed at.
    """

    CAPSULE = "capsule"
    OBLONG = "oblong"
    ROUND = "round"


SHAPE_WORDS: tuple[tuple[str, Shape], ...] = (
    ("capsule-shaped", Shape.OBLONG),
    ("capsule shaped", Shape.OBLONG),
    ("capsule", Shape.CAPSULE),
    ("oblong", Shape.OBLONG),
    ("oval", Shape.OBLONG),
    ("elliptical", Shape.OBLONG),
    ("caplet", Shape.OBLONG),
    ("round", Shape.ROUND),
    ("circular", Shape.ROUND),
)
"""Outline words, most specific first — the order is load-bearing.

`capsule` sits above the outline adjectives, below only the two hyphenated forms that mean
the opposite. A label writing "Oval hard capsules" is describing a capsule with an oval
outline; scanned in the other order the adjective won and the glyph drew a tablet.

A "capsule-shaped tablet" is an oblong tablet, not a capsule, so it has to be recognised
before the bare word `capsule` can claim it. Scanned in list order rather than by
position in the text, because the specific phrase contains the general word.
"""

COLOUR_WORDS = (
    "white", "red", "orange", "yellow", "pink", "brown", "green", "blue",
    "grey", "gray", "black", "purple", "violet", "ivory", "cream", "beige",
)
"""Colour vocabulary, as labels write it.

Code rather than `config/*.yaml` for the same reason `product.STRENGTH` and `product.FORM`
are: this is the grammar the parser reads, not a tunable lexicon whose entries a reviewer
would weigh. A word absent here yields no colour, which surfaces as "described but not
drawn" — the visible gap, never a default fill.
"""

MODIFIERS = ("pale", "dark", "light", "deep", "bright", "off")

COLOUR = re.compile(
    rf"\b(?:({'|'.join(MODIFIERS)})[\s-]+)?({'|'.join(COLOUR_WORDS)})\b", re.I
)

HALF = re.compile(r"(?:[,\s]+\w+){0,2}[,\s]+(cap|body)\b", re.I)
"""What follows a colour when the label binds it to one half of a capsule.

Up to two words may intervene, separated by whitespace or a comma: labels write "red
opaque body" and also "White, opaque body", and requiring whitespace alone silently lost
the binding on the second — drawing that capsule inside out. The bound
reading is preferred over the stated order because the two disagree — 7142 opens
"Orange/White" (cap first) and 14717 opens "Red opaque body" (body first), so reading
either as cap-then-body by position would draw one of them inside out.
"""

CAPSULE_HALVES = re.compile(r"\bcap\b(?=.*\bbody\b)|\bbody\b(?=.*\bcap\b)", re.I | re.S)
"""A capsule named by its two halves rather than by the word "capsule".

14717 says only "Red opaque body and red opaque cap" — `cap` and `body` are the regulated
terms for the two halves of a hard capsule, and a tablet has neither. Both are required,
so a stray "cap" cannot on its own turn a tablet into a capsule.
"""

DIMENSIONS = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:mm)?\s*[x×]\s*(\d+(?:[.,]\d+)?)\s*mm", re.I)
"""A stated `L x W mm`. A lone measurement is not read: which axis it names is unstated."""

INK = re.compile(
    r"\b(?:print|printed|imprint|imprinted|mark|marked|engrav\w*|deboss\w*)\s+(?:in|with)\s+\w+"
    r"|\b\w+(?:\s+edible)?\s+ink\b",
    re.I,
)
"""The colour of the *printing*, which is not the colour of the product.

7142 ends "with black edible ink" and 14717 "printed in black". Read as product colour
those draw a black capsule, so the phrase is blanked before colours are scanned.
"""

SIZE = re.compile(r"\bsize\s+['\"‘’“”]?\w+['\"‘’“”]?", re.I)
"""A capsule shell size. 7142's `size '4'` is quoted exactly like an imprint and is not one."""

QUOTES = "'\"‘’“”"
QUOTED = re.compile(rf"[{QUOTES}]([^{QUOTES}]{{1,16}})[{QUOTES}]")
"""What the label puts in quotation marks — the imprint, in its own words."""

NO_SHAPE = "shape"
NO_COLOUR = "colour"


@dataclass(frozen=True, slots=True)
class Appearance:
    """One label's §3 description, and what could be read out of it.

    `source_text` is the section verbatim and is always present, so a description that
    parsed to nothing is still published rather than dropped. Everything else is what the
    label states and only what it states: `length_mm` is `None` on a label that gives no
    dimensions, which is unknown, not a size to be inferred from the others.
    """

    source_text: str
    shape: Shape | None
    colours: tuple[str, ...]
    """Product colours, normalised to lower case and a single space ("pale red").

    Ordered cap-then-body where the label binds each half to a colour, otherwise in the
    order the label states them. A capsule of one colour yields one entry, not two.
    """

    length_mm: float | None = None
    width_mm: float | None = None
    imprints: tuple[str, ...] = ()

    @property
    def drawable(self) -> bool:
        """Whether the label states enough to draw. Colour and outline, nothing else."""
        return self.shape is not None and bool(self.colours)

    @property
    def unparsed(self) -> tuple[str, ...]:
        """What could not be read, named — the reason a description is not drawn.

        Derived rather than stored so it cannot disagree with the fields it describes.
        Dimensions and imprints are absent from it deliberately: a label that states no
        size has not failed to parse, it has said nothing about size.
        """
        missing = []
        if self.shape is None:
            missing.append(NO_SHAPE)
        if not self.colours:
            missing.append(NO_COLOUR)
        return tuple(missing)


def described_in(section_text: str) -> Appearance:
    """The appearance a §3 section describes, reading only what it states.

    A pure function beside the entity it builds, like `found_in`: the prose is
    company-authored and dirty — 8066 opens `Tablets mg 5mg Pale red oblong tablet` — so
    what it yields has to be testable against real strings with no storage present.

    Nothing is inferred to fill a gap. An unreadable colour or outline comes back as an
    `Appearance` carrying the text and an empty field, never a default, because a glyph
    drawn from a guess claims something the label does not.
    """
    return Appearance(
        source_text=section_text,
        shape=_shape(section_text),
        colours=_colours(section_text),
        length_mm=_dimension(section_text, 1),
        width_mm=_dimension(section_text, 2),
        imprints=_imprints(section_text),
    )


def _shape(text: str) -> Shape | None:
    """The stated outline, or the capsule its two named halves imply."""
    for word, shape in SHAPE_WORDS:
        # `s?` so "capsules" counts; the closing boundary so "rounded" does not.
        if re.search(rf"\b{re.escape(word)}s?\b", text, re.I):
            return shape
    return Shape.CAPSULE if CAPSULE_HALVES.search(text) else None


def _colours(text: str) -> tuple[str, ...]:
    """Product colours in drawing order, with the printing's own colour excluded."""
    body = INK.sub(" ", text)
    halves = _halves(body)
    if "cap" in halves and "body" in halves:
        return _distinct([halves["cap"], halves["body"]])
    return _distinct([_named(found) for found in COLOUR.finditer(body)])


def _halves(text: str) -> dict[str, str]:
    """Colour bound to `cap` or `body` where the label binds one, first mention winning."""
    bound: dict[str, str] = {}
    for found in COLOUR.finditer(text):
        part = HALF.match(text, found.end())
        if part:
            bound.setdefault(part.group(1).lower(), _named(found))
    return bound


def _named(found: re.Match[str]) -> str:
    """One colour match as a single normalised phrase, so `Gray` and `grey` are one word."""
    word = found.group(2).lower().replace("gray", "grey")
    return f"{found.group(1).lower()} {word}" if found.group(1) else word


def _distinct(colours: list[str]) -> tuple[str, ...]:
    """The colours in the order first stated, each once."""
    return tuple(dict.fromkeys(colours))


def _dimension(text: str, group: int) -> float | None:
    """One axis of a stated `L x W mm`, or None where the label gives no dimensions."""
    found = DIMENSIONS.search(text)
    return float(found.group(group).replace(",", ".")) if found else None


def _imprints(text: str) -> tuple[str, ...]:
    """What the label quotes as printed on the product, shell sizes excluded."""
    return tuple(dict.fromkeys(QUOTED.findall(SIZE.sub(" ", text))))
