"""S1 — resolve a substance to the products that share it."""

import re
from collections import Counter
from collections.abc import Iterable, Sequence

from ixq.domain import Product, Source, Substance
from ixq.pipeline.ports import LabelSource, Repository

DOSAGE_FORM = re.compile(
    r"\b(?:powder|solvent|solution|diluent|suspension|granules|vehicle)\b", re.I
)
"""Words that make an `and` a presentation, not a combination.

`Cefotaxime 1g Powder and Solvent for Solution for Injection` is one substance in two
containers. Reading it as a combination drops the product silently — the same class of
loss the `/` branch was narrowed to avoid.
"""

COMBINATION = re.compile(r"([A-Za-z]{4,})\s*(?:/|\band\b)\s*([A-Za-z]{4,})")
"""A combination joins two substance names, with `/` or `and`. A concentration joins a
number and a unit.

Matching a bare `/` conflates the two: of 31 ramipril products, 6 contain a `/` and none
is a combination — they are `Ramipril 2.5 mg/5 ml Oral solution`. Dropping those removes
three manufacturers that publish only oral solutions.

The name is *not* required to contain the substance: `Tritace` is ramipril's originator
brand, and excluding brands would drop the reference product from every comparison.
"""

STRENGTHS = re.compile(r"\d+\s*(?:mg|micrograms?|g)\s*/\s*\d+\s*(?:mg|micrograms?|g)\b", re.I)
"""Two strengths joined by `/`, which only a combination has.

`COMBINATION` requires a word either side of the join, so it cannot see a branded
combination that names no ingredient at all: `Exforge 5mg/80mg` is amlodipine and
valsartan, and it reads to that rule exactly like a single-substance tablet. Of the 32
products EMC returns for amlodipine, seven are combinations and it caught none.

Safe for the same reason the `/` branch was narrowed: a concentration is a strength over a
*volume* — `Ramipril 2.5 mg/5 ml` — so requiring a mass unit on both sides separates the
two. Checked against the ramipril corpus, where it matches nothing.
"""


def _joins_substances(left: str, right: str) -> bool:
    """Whether this join is between two substance names rather than two presentations.

    Judged on the words **immediately either side** of the join, not on how many
    presentation words the name contains anywhere. A global count admits
    `Amoxicillin and Clavulanic Acid Powder for Oral Suspension` — a genuine combination
    that merely also names its presentation — into a single-substance comparison, which
    is a worse error than the dropped `Powder and Solvent` it was meant to prevent.
    """
    return not (DOSAGE_FORM.fullmatch(left) or DOSAGE_FORM.fullmatch(right))


def is_combination(product_name: str) -> bool:
    """Whether a name denotes two active substances rather than one.

    A name may contain several joins — `Amoxicillin and Clavulanic Acid Powder and
    Solvent` has two — so every one is examined and any single substance join settles it.
    """
    if STRENGTHS.search(product_name):
        return True
    return any(
        _joins_substances(left, right)
        for left, right in COMBINATION.findall(product_name)
    )


def collect(
    substance: Substance,
    source: Source,
    collector_id: str,
    labels: LabelSource,
    repository: Repository,
) -> list[Product]:
    """Find every single-substance product of `substance` and persist it.

    Combination products are excluded here rather than downstream: comparing a
    combination against a single-ingredient product is the resolution error that makes
    every later divergence meaningless.

    The caller owns the transaction boundary — writes here are not durable until it
    commits, which lets one substance's whole product set land atomically.

    Precondition: `source` must already be persisted — `products.source_id` is a foreign
    key, and `init` loads the roster. The substance is saved here because this stage is
    what establishes it as one worth tracking.
    """
    repository.save_substance(substance)
    rows = labels.rows(collector_id, [source.search_for(substance.name)])
    return list(_products(rows, substance, source, repository))


def _products(
    rows: Iterable[dict], substance: Substance, source: Source, repository: Repository
) -> Iterable[Product]:
    seen: set[str] = set()
    for row in rows:
        name = (row.get("product_name") or "").strip()
        ident = source.external_id_from(row.get("product_url") or "")
        if not name or not ident or ident in seen or is_combination(name):
            continue
        seen.add(ident)
        product = Product(
            source_id=source.id,
            external_id=ident,
            substance_id=substance.id,
            name=name,
            ma_holder=row.get("company") or None,
        )
        repository.save_product(product)
        yield product


PRESENTATION = re.compile(
    r"(?P<strength>\d+(?:\.\d+)?)\s*(?P<unit>mg|micrograms?|g)\b(?!\s*/)", re.I
)
"""A product's strength, when its name states one. `(?!\\s*/)` skips a concentration's
numerator — `1 mg/ml` states a strength per volume, which is not a tablet's 1 mg.
"""

FORM = ("oral suspension", "oral solution", "capsule", "tablet")
"""Dosage forms, longest first so `oral solution` is not read as a bare `solution`."""


def _presentation(name: str) -> tuple[str, str] | None:
    """The (strength, form) a product name states, or None when it states neither."""
    strength = PRESENTATION.search(name)
    form = next((f for f in FORM if f in name.lower()), None)
    if not strength or not form:
        return None
    return f"{float(strength['strength']):g} {strength['unit'].lower()}", form


def shortlist(products: Sequence[Product], cap: int) -> list[Product]:
    """The `cap` products that make the strongest comparison, not the first `cap` found.

    The comparison's premise is that its columns are substitutable for one another, so the
    selection maximises *distinct manufacturers at one presentation*: the commonest
    strength and form among what was found, then one product per holder.

    Both halves matter. Taking discovery order gave ramipril three Aurobindo products out
    of seven, which spends fetches on a holder already represented while leaving others
    uncollected. And mixing presentations imports differences that are not the
    manufacturer's choice — ramipril's one refrigerated label is an oral solution, and
    reading that beside tablets invites "these disagree about storage" when what differs
    is the formulation.

    Falls back rather than starves: once every holder at the chosen presentation is taken,
    remaining slots go to unrepresented holders at any presentation, then to anything left.
    A substance whose names state no presentation at all still returns `cap` products.
    """
    if not cap or len(products) <= cap:
        return list(products)

    presentations = Counter(
        found for found in map(_presentation, (p.name for p in products)) if found
    )
    commonest = presentations.most_common(1)[0][0] if presentations else None

    chosen: list[Product] = []
    taken: set[str] = set()
    held: set[str] = set()

    def take(candidates: Iterable[Product], *, one_per_holder: bool) -> None:
        for product in candidates:
            if len(chosen) == cap:
                return
            holder = product.ma_holder or product.external_id
            if product.external_id in taken:
                continue
            if one_per_holder and holder in held:
                continue
            held.add(holder)
            taken.add(product.external_id)
            chosen.append(product)

    take((p for p in products if _presentation(p.name) == commonest), one_per_holder=True)
    take(products, one_per_holder=True)
    take(products, one_per_holder=False)
    return chosen
