"""Interfaces the use cases depend on. Implementations live in the adapters layer."""

from typing import Protocol

from preward.domain import Document, Page, Record, Signal, Source


class Repository(Protocol):
    """The pipeline's persistence boundary.

    One port rather than one-per-aggregate: there is a single backing store and a
    single reason to change. Nothing above this line may know that SQL exists.
    """

    def save_source(self, source: Source) -> None:
        """Insert or update a source."""
        ...

    def save_document(self, document: Document) -> None:
        """Insert a document, keyed by content hash. Idempotent on re-fetch."""
        ...

    def save_page(self, document_sha256: str, page: Page) -> None:
        """Insert or replace one page of extracted text."""
        ...

    def save_record(self, record: Record) -> Record:
        """Insert or update a record, returning it with its assigned id."""
        ...

    def save_signal(self, signal: Signal) -> Signal:
        """Insert a signal, returning it with its assigned id."""
        ...

    def signals_for_record(self, record_id: int) -> list[Signal]:
        """Every signal for a record, oldest event first. This is the ladder."""
        ...
