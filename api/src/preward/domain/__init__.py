"""Core entities. No I/O, no framework imports, no dependencies on outer layers."""

from preward.domain.concept import Placement
from preward.domain.document import Document
from preward.domain.occurrence import Occurrence, found_in
from preward.domain.product import Product
from preward.domain.section import Section
from preward.domain.source import Source
from preward.domain.substance import Substance

__all__ = [
    "Document",
    "Occurrence",
    "Placement",
    "Product",
    "Section",
    "Source",
    "Substance",
    "found_in",
]
