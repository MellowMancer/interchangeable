"""Core entities. No I/O, no framework imports, no dependencies on outer layers."""

from ixq.domain.appearance import Appearance, Shape, described_in
from ixq.domain.collector import Collector, CollectorKind
from ixq.domain.concept import COMPARABLE, UNCLASSIFIED, Concept, Placement
from ixq.domain.document import Document, revision_date
from ixq.domain.occurrence import Context, Occurrence, found_in, in_context
from ixq.domain.product import Product, variant
from ixq.domain.section import Clause, Section, clauses, prepared
from ixq.domain.source import Source
from ixq.domain.substance import Substance

__all__ = [
    "COMPARABLE",
    "UNCLASSIFIED",
    "Appearance",
    "Clause",
    "Collector",
    "CollectorKind",
    "Concept",
    "Context",
    "described_in",
    "Document",
    "Occurrence",
    "in_context",
    "Placement",
    "Product",
    "variant",
    "Section",
    "Shape",
    "Source",
    "Substance",
]
