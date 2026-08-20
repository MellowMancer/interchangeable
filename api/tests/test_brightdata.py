"""The Bright Data seam, exercised without bdata, npx, or a network."""

from typing import Any

import pytest
from bdheal import CollectorSpec, RunResult

from ixq.adapters.brightdata import SCHEMAS, HealerLabelSource, ProductRow, SearchRow
from ixq.domain import CollectorKind


class StubHealer:
    """Records the spec it was handed and replays canned rows."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self.specs: list[CollectorSpec] = []

    def run(self, spec: CollectorSpec, urls) -> RunResult:
        self.specs.append(spec)
        from datetime import UTC, datetime

        return RunResult(
            collector_id=spec.collector_id,
            fetched_at=datetime.now(UTC),
            rows=self._rows,
            errors=[],
            error_codes=[],
        )


def test_rows_are_returned_and_the_spec_carries_the_right_schema() -> None:
    healer = StubHealer([{"product_name": "Example 10mg Tablets"}])
    source = HealerLabelSource(healer, {"c_product": ProductRow})

    rows = source.rows("c_product", ["https://example.test/product/987"])

    assert rows == [{"product_name": "Example 10mg Tablets"}]
    assert healer.specs[0].row_schema is ProductRow
    assert healer.specs[0].anchor_urls == ["https://example.test/product/987"]


def test_an_unknown_collector_is_refused_by_name() -> None:
    """Silently returning nothing would look like a label with no contraindications."""
    source = HealerLabelSource(StubHealer([]), {"c_product": ProductRow})

    with pytest.raises(KeyError, match="c_search"):
        source.rows("c_search", ["https://example.test"])


def test_rows_keep_fields_the_collector_added_itself() -> None:
    """The generator names its own fields and echoes its input; rejecting those breaks it."""
    row = {"product_name": "X", "input": {"url": "y"}, "run_id": "abc"}
    source = HealerLabelSource(StubHealer([row]), {"c_product": ProductRow})

    assert source.rows("c_product", ["u"]) == [row]


def test_every_collector_role_that_returns_rows_has_a_schema() -> None:
    assert SCHEMAS[CollectorKind.SEARCH] is SearchRow
    assert SCHEMAS[CollectorKind.PRODUCT] is ProductRow


def test_a_label_missing_a_section_still_validates() -> None:
    """A missing field is a signal for the stage that needed it, not a validation error."""
    assert ProductRow(product_name="X").section_4_3_contraindications is None
