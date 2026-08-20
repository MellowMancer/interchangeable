"""S1 — resolve a substance to the products that share it."""

import re
from collections.abc import Iterable

from ixq.domain import Product, Source, Substance
from ixq.pipeline.ports import LabelSource, Repository

COMBINATION = re.compile(r"[A-Za-z]{4,}\s*(?:/|\band\b)\s*[A-Za-z]{4,}")
"""A combination joins two substance names, with `/` or `and`. A concentration joins a
number and a unit.

Matching a bare `/` conflates the two: of 31 ramipril products, 6 contain a `/` and none
is a combination — they are `Ramipril 2.5 mg/5 ml Oral solution`. Dropping those removes
three manufacturers that publish only oral solutions.

The name is *not* required to contain the substance: `Tritace` is ramipril's originator
brand, and excluding brands would drop the reference product from every comparison.
"""

PRODUCT_ID = re.compile(r"/product/(\d+)")


def is_combination(product_name: str) -> bool:
    """Whether a name denotes two active substances rather than one."""
    return bool(COMBINATION.search(product_name))


def external_id(url: str) -> str | None:
    """The publisher's product id, read out of a product URL."""
    found = PRODUCT_ID.search(url or "")
    return found.group(1) if found else None


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

    Precondition: `source` must already be persisted — `products.source_id` is a foreign
    key, and `init` loads the roster. The substance is saved here because this stage is
    what establishes it as one worth tracking.
    """
    repository.save_substance(substance)
    rows = labels.rows(collector_id, [source.search_for(substance.name)])
    return [p for p in _products(rows, substance, source, repository)]


def _products(
    rows: Iterable[dict], substance: Substance, source: Source, repository: Repository
) -> Iterable[Product]:
    seen: set[str] = set()
    for row in rows:
        name = (row.get("product_name") or "").strip()
        ident = external_id(row.get("product_url") or row.get("product_page_url") or "")
        if not name or not ident or ident in seen or is_combination(name):
            continue
        seen.add(ident)
        yield repository.save_product(
            Product(
                source_id=source.id,
                external_id=ident,
                substance_id=substance.id,
                name=name,
                ma_holder=(row.get("company") or row.get("ma_holder") or None),
            )
        )
