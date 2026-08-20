"""Label rows from Bright Data Scraper Studio, through the self-healing loop."""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from bdheal import CollectorSpec, Healer
from bdheal.clock import SystemClock
from bdheal.process import SubprocessRunner
from bdheal.store import SqliteHealStore
from bdheal.store import connect as heal_connect
from bdheal.studio import BdataStudioClient
from pydantic import BaseModel, ConfigDict

from ixq.domain import CollectorKind


class _Row(BaseModel):
    """Rows are validated, not constrained.

    `extra="allow"` because the collector adds fields we did not ask for — it echoes its
    input, and its generator names fields itself. Rejecting those would turn a working
    collector into a run of validation errors. Every field is optional for the same
    reason: a *missing* field is the pipeline's signal that something moved, and that
    judgement belongs in the stage that knows what it needed, not here.
    """

    model_config = ConfigDict(extra="allow")


class SearchRow(_Row):
    """One search hit: a product and who holds its authorisation."""

    product_name: str | None = None
    product_url: str | None = None
    company: str | None = None


class ProductRow(_Row):
    """One label, as the product collector returns it."""

    product_name: str | None = None
    active_substance: str | None = None
    ma_holder: str | None = None
    section_4_3_contraindications: str | None = None
    section_4_4_warnings: str | None = None
    section_4_5_interactions: str | None = None
    section_4_6_pregnancy_lactation: str | None = None
    last_updated: str | None = None


SCHEMAS: dict[CollectorKind, type[BaseModel]] = {
    CollectorKind.SEARCH: SearchRow,
    CollectorKind.PRODUCT: ProductRow,
}


class HealerLabelSource:
    """A `LabelSource` backed by `bdheal`, so a moved layout is repaired, not fatal.

    Holds one schema per collector id because the port addresses collectors by id while
    the row shape depends on the collector's role.
    """

    def __init__(self, healer: Healer, schemas: Mapping[str, type[BaseModel]]) -> None:
        self._healer = healer
        self._schemas = dict(schemas)

    def rows(self, collector_id: str, urls: Sequence[str]) -> list[dict[str, Any]]:
        """Run one collector against the given URLs and return its validated rows."""
        schema = self._schemas.get(collector_id)
        if schema is None:
            raise KeyError(
                f"no row schema for collector {collector_id!r}; known: {sorted(self._schemas)}"
            )
        spec = CollectorSpec(
            collector_id=collector_id,
            name=collector_id,
            anchor_urls=list(urls),
            row_schema=schema,
        )
        return self._healer.run(spec, urls).rows


def label_source(db_path: Path, collectors: Mapping[CollectorKind, str]) -> HealerLabelSource:
    """Wire a live `HealerLabelSource` over the `bdata` CLI.

    `bdheal` keeps its baselines and heal events in its own `bdheal_`-prefixed tables in
    the same file, which is what lets a run's history sit beside the labels it produced.
    """
    healer = Healer(
        studio=BdataStudioClient(runner=SubprocessRunner(), clock=SystemClock()),
        store=SqliteHealStore(heal_connect(db_path)),
        clock=SystemClock(),
    )
    return HealerLabelSource(
        healer, {cid: SCHEMAS[kind] for kind, cid in collectors.items() if kind in SCHEMAS}
    )
