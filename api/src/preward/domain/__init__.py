"""Core entities. No I/O, no framework imports, no dependencies on outer layers."""

from preward.domain.document import Document, Page
from preward.domain.record import Record
from preward.domain.signal import Signal
from preward.domain.source import Source
from preward.domain.tier import ExtractionMethod, Tier

__all__ = [
    "Document",
    "ExtractionMethod",
    "Page",
    "Record",
    "Signal",
    "Source",
    "Tier",
]
