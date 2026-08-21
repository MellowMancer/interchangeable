"""Label rows from Bright Data Scraper Studio, through the self-healing loop."""

import json
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

from ixq.domain import Collector, CollectorKind
from ixq.pipeline.ports import CollectorCheck
from ixq.settings import HEAL_DB_NAME


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
    """One label, as the product collector returns it.

    Every field the collector returns is declared here, including ones no pipeline stage
    reads. `bdheal` computes its null rates over `model_fields`, so a field left to
    `extra="allow"` is outside drift monitoring entirely — it could go null across the
    whole corpus without a signal firing. Declaring it is what puts it under watch.
    """

    product_name: str | None = None
    active_substance: str | None = None
    ma_holder: str | None = None
    section_4_3_contraindications: str | None = None
    section_4_4_warnings: str | None = None
    section_4_5_interactions: str | None = None
    section_4_6_pregnancy_lactation: str | None = None
    section_6_1_excipients: str | None = None
    last_updated: str | None = None
    emc_last_updated: str | None = None
    company_id: int | None = None
    ingredient_id: int | None = None
    atc_code: str | None = None
    legal_status: str | None = None
    section_8_ma_number: str | None = None
    discontinued: bool | None = None


SCHEMAS: dict[CollectorKind, type[BaseModel]] = {
    CollectorKind.SEARCH: SearchRow,
    CollectorKind.PRODUCT: ProductRow,
}


class HealerLabelSource:
    """A `LabelSource` and `CollectorMaintainer` backed by `bdheal`.

    Holds one schema per collector id because the port addresses collectors by id while
    the row shape depends on the collector's role.

    `run` alone is a pass-through with no side effects — it captures no baseline and
    records no heal event, which is why driving only `rows()` left the reliability screen
    permanently empty. The loop lives in `ensure_healthy`, called once per collector per
    run rather than once per product.
    """

    def __init__(
        self,
        healer: Healer,
        schemas: Mapping[str, type[BaseModel]],
        collectors: Mapping[str, Collector] | None = None,
        goldens: "GoldenStore | None" = None,
    ) -> None:
        self._healer = healer
        self._schemas = dict(schemas)
        self._collectors = dict(collectors or {})
        self._goldens = goldens

    def rows(self, collector_id: str, urls: Sequence[str]) -> list[dict[str, Any]]:
        """Run one collector against the given URLs and return its validated rows."""
        return self._healer.run(self._spec(collector_id, urls), urls).rows

    def ensure_healthy(self, collector_id: str) -> CollectorCheck:
        """Judge the collector against its anchor, and repair it in place if it has moved."""
        collector = self._collectors.get(collector_id)
        if collector is None or not collector.anchor_url:
            return CollectorCheck(
                collector_id=collector_id,
                broken=False,
                reason="no anchor_url configured — drift cannot be judged",
            )
        if collector_id not in self._schemas:
            # `sitemap` and `discovery` are valid kinds with no row shape yet. Raising
            # here would abort the whole run over a collector nothing is asking to use.
            return CollectorCheck(
                collector_id=collector_id,
                broken=False,
                reason="no row schema for this collector kind — not checked",
            )

        anchor = [collector.anchor_url]
        spec = self._spec(collector_id, anchor)
        # Bound, not inlined: a second `run` is a second billable job against the one page
        # whose baseline must stay clean, and it would store goldens from a run `detect`
        # never judged. The docs are explicit that a duplicate run is two jobs for one
        # answer.
        result = self._healer.run(spec, anchor)
        verdict = self._healer.detect(spec, result)
        if not verdict.broken:
            if self._goldens is not None and collector.old_layout_url:
                self._goldens.save(collector_id, result.rows)
            return CollectorCheck(collector_id=collector_id, broken=False)

        event = self._healer.heal(spec, verdict)
        if not event.promoted:
            return CollectorCheck(
                collector_id=collector_id, broken=True, reason=event.error or event.status
            )

        golden = self._goldens.load(collector_id) if self._goldens else []
        if not (collector.old_layout_url and golden):
            return CollectorCheck(
                collector_id=collector_id,
                broken=True,
                healed=True,
                promoted_unverified=True,
                reason="promoted without the non-regression check: "
                + ("no golden records" if collector.old_layout_url else "no old_layout_url"),
            )

        report = self._healer.verify(spec, golden, collector.old_layout_url)
        return CollectorCheck(
            collector_id=collector_id,
            broken=True,
            healed=report.non_regression_passed,
            reason=None
            if report.non_regression_passed
            else "healed layout fails against the previous one — rolled back",
        )

    def _spec(self, collector_id: str, urls: Sequence[str]) -> CollectorSpec:
        schema = self._schemas.get(collector_id)
        if schema is None:
            raise KeyError(
                f"no row schema for collector {collector_id!r}; known: {sorted(self._schemas)}"
            )
        return CollectorSpec(
            collector_id=collector_id,
            name=collector_id,
            anchor_urls=list(urls),
            row_schema=schema,
        )


class GoldenStore:
    """Known-good rows per collector, captured from a healthy anchor run.

    On disk rather than in the database: they are an input to `verify`, not something the
    comparison is derived from, and keeping them out of the schema avoids a migration for
    data that is regenerated on the next healthy run anyway.
    """

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def save(self, collector_id: str, rows: Sequence[dict[str, Any]]) -> None:
        """Replace this collector's goldens with the rows of a run that detect passed."""
        self._directory.mkdir(parents=True, exist_ok=True)
        self._path(collector_id).write_text(json.dumps(list(rows), ensure_ascii=False))

    def load(self, collector_id: str) -> list[dict[str, Any]]:
        """The stored goldens, or an empty list before a collector's first healthy run."""
        path = self._path(collector_id)
        return json.loads(path.read_text()) if path.exists() else []

    def _path(self, collector_id: str) -> Path:
        """`.name` because an id reaches this as a path segment.

        Ids are operator-controlled config rather than untrusted input, so this is not a
        live injection — but `c_../../x` would escape the directory, and that class of
        mistake is impossible in the database this store deliberately sits beside.
        """
        return self._directory / f"{Path(collector_id).name}.json"


def label_source(
    db_path: Path,
    collectors: Mapping[CollectorKind, str],
    roster: Sequence[Collector] = (),
) -> HealerLabelSource:
    """Wire a live `HealerLabelSource` over the `bdata` CLI.

    `bdheal` keeps its baselines and heal events in its own database beside this one, so
    an app schema bump can never refuse or rebuild a file holding heal history.
    """
    healer = Healer(
        studio=BdataStudioClient(runner=SubprocessRunner(), clock=SystemClock()),
        store=SqliteHealStore(heal_connect(db_path.with_name(HEAL_DB_NAME))),
        clock=SystemClock(),
    )
    return HealerLabelSource(
        healer,
        {cid: SCHEMAS[kind] for kind, cid in collectors.items() if kind in SCHEMAS},
        collectors={c.id: c for c in roster},
        goldens=GoldenStore(db_path.parent / "goldens"),
    )
