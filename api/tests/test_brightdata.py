"""The Bright Data seam, exercised without bdata, npx, or a network."""

from types import SimpleNamespace
from typing import Any

import pytest
from bdheal import CollectorSpec, RunResult

from ixq.adapters.brightdata import SCHEMAS, HealerLabelSource, ProductRow, SearchRow
from ixq.domain import Collector, CollectorKind


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


class _StubHealer:
    """Records which of the four `Healer` methods the adapter actually drove."""

    def __init__(self, *, broken: bool = False, promoted: bool = True, passes: bool = True):
        self.calls: list[str] = []
        self._broken, self._promoted, self._passes = broken, promoted, passes

    def run(self, spec, urls):
        self.calls.append(f"run:{urls[0]}")
        return SimpleNamespace(rows=[{"product_name": "X"}], errors=[])

    def detect(self, spec, result):
        self.calls.append("detect")
        return SimpleNamespace(broken=self._broken)

    def heal(self, spec, verdict):
        self.calls.append("heal")
        return SimpleNamespace(promoted=self._promoted, error=None, status="done")

    def verify(self, spec, golden, old_layout_url):
        self.calls.append("verify")
        return SimpleNamespace(non_regression_passed=self._passes)


ANCHOR = "https://example.test/anchor"


def _source(**kw) -> HealerLabelSource:
    healer = kw.pop("healer")
    collector = Collector(id="c_p", source_id="emc", kind=CollectorKind.PRODUCT, **kw)
    return HealerLabelSource(healer, {"c_p": ProductRow}, {"c_p": collector})


def test_a_healthy_collector_is_detected_against_its_anchor_not_the_product() -> None:
    """The baseline is keyed on the collector, so a varying anchor rewrites it every run."""
    healer = _StubHealer()

    check = _source(healer=healer, anchor_url=ANCHOR).ensure_healthy("c_p")

    assert healer.calls == [f"run:{ANCHOR}", "detect"]
    assert check.broken is False


def test_detect_is_what_captures_a_baseline_so_rows_alone_records_nothing() -> None:
    """`rows()` drives only `run`, which has no side effects — the original defect."""
    healer = _StubHealer()

    _source(healer=healer, anchor_url=ANCHOR).rows("c_p", ["https://example.test/1"])

    assert healer.calls == ["run:https://example.test/1"]
    assert "detect" not in healer.calls


def test_a_broken_collector_is_healed_in_place() -> None:
    healer = _StubHealer(broken=True)

    check = _source(healer=healer, anchor_url=ANCHOR).ensure_healthy("c_p")

    assert healer.calls == [f"run:{ANCHOR}", "detect", "heal"]
    assert check.healed is True


def test_a_heal_without_an_old_layout_is_reported_unverified_not_clean() -> None:
    """A fix that repairs today's layout by breaking yesterday's has healed nothing."""
    healer = _StubHealer(broken=True)

    check = _source(healer=healer, anchor_url=ANCHOR).ensure_healthy("c_p")

    assert check.promoted_unverified is True
    assert "verify" not in healer.calls
    assert "no old_layout_url" in (check.reason or "")


def test_a_collector_with_no_anchor_is_not_judged_at_all() -> None:
    """Silence is better than a verdict reached by hashing a different page each run."""
    healer = _StubHealer()

    check = _source(healer=healer).ensure_healthy("c_p")

    assert healer.calls == [] and check.broken is False
    assert "no anchor_url" in (check.reason or "")
