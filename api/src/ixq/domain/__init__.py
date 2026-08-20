"""Core entities. No I/O, no framework imports, no dependencies on outer layers."""

from ixq.domain.concept import UNCLASSIFIED, Concept, Placement
from ixq.domain.document import Document
from ixq.domain.occurrence import Occurrence, found_in
from ixq.domain.product import Product
from ixq.domain.section import Section
from ixq.domain.source import Source
from ixq.domain.substance import Substance

__all__ = [
    "UNCLASSIFIED",
    "Concept",
    "Document",
    "Occurrence",
    "Placement",
    "Product",
    "Section",
    "Source",
    "Substance",
    "found_in",
]
