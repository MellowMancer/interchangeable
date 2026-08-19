"""Every type that crosses a boundary — caller to package, use case to port.

Pydantic lives here and only here. The caller's `row_schema` failing validation *is* a
detect signal, so the boundary has to produce structured per-field errors rather than a
stack trace. Types that never leave the module that computes them are frozen dataclasses
in that module instead.

The fields, their types and their constraints are the contract every other feature is
written against. A violation raises `ValueError`, which `ValidationError` subclasses, so
a caller guards this whole surface without importing pydantic.
"""

from datetime import datetime
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeFloat,
    NonNegativeInt,
    StringConstraints,
)

from bdheal.vocabulary import (
    TERMINAL_STATUSES,
    FailureClass,
    HealStatus,
    MutationClass,
    SignalKind,
    SignalOutcome,
)

# A caller-supplied string that names something. Stored trimmed, so `" c1 "` and `"c1"`
# cannot become two collectors in the store.
NonBlankStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

class _Boundary(BaseModel):
    """Shared configuration for every boundary model.

    `extra="forbid"` because a mistyped field name silently becoming an ignored extra is
    exactly the class of bug the schema-validation detect signal exists to catch. Models
    stay mutable: `model_copy(update=...)` is the store's update idiom.
    """

    model_config = ConfigDict(extra="forbid")


# A fraction of a whole: an accuracy or a null rate. Outside 0.0..1.0 it is a bug upstream.
Ratio = Annotated[float, Field(ge=0.0, le=1.0)]


class CollectorSpec(_Boundary):
    """One collector as the caller describes it: its id, its anchors, its row schema."""

    collector_id: NonBlankStr
    name: str
    anchor_urls: list[NonBlankStr] = Field(min_length=1)
    row_schema: type[BaseModel]


class RowError(_Boundary):
    """One input row that produced no usable record — target-side or schema-side.

    `error_code` is Bright Data's per-row outcome (`rate_limit` and friends);
    `field_errors` is the caller's schema rejecting the row, keyed by field name.
    """

    index: int
    message: str
    error_code: str | None = None
    field_errors: dict[str, str] = {}


class RunResult(_Boundary):
    """The outcome of one collector run: validated rows, failed rows, and when.

    `rows` carries validated *data*, not `row_schema` instances, so the result stays
    serialisable and round-trips through `model_dump()`. Callers who want instances
    re-validate with their own schema.
    """

    collector_id: NonBlankStr
    fetched_at: datetime
    rows: list[dict[str, Any]] = []
    errors: list[RowError] = []
    error_codes: list[str] = []


class Signal(_Boundary):
    """One detector's reading of a run, with the evidence in plain words."""

    kind: SignalKind
    outcome: SignalOutcome
    detail: str


def fired_signals(signals: list[Signal]) -> list[Signal]:
    """The signals that are evidence. Only `FIRED` counts; an abstention never does.

    The package's central rule, in one place. `detect` needs it before a verdict exists
    (to set `broken`), and `diagnose` needs it after — so it lives here rather than in
    either. It was written independently in both, which meant a third `SignalOutcome`
    member had to be remembered twice, and a miss means detect says broken while diagnose
    classifies `UNKNOWN` and sends the generic prompt.
    """
    return [signal for signal in signals if signal.outcome is SignalOutcome.FIRED]


class DetectVerdict(_Boundary):
    """Whether the collector is broken, and everything that led to the answer.

    `incomplete` and `retry_requested` keep "the target refused part of the sample" from
    ever being read as "the site broke" — healing against a truncated sample is the
    expensive failure mode. `incomplete` covers every target-side refusal, not only
    rate-limiting: blocked, captcha and timeout leave the sample just as untrustworthy.
    """

    broken: bool
    signals: list[Signal] = []
    incomplete: bool = False
    retry_requested: bool = False
    ambiguous_codes: tuple[str, ...] = ()
    reason: str | None = None

    @property
    def fired(self) -> list[Signal]:
        """The signals that are evidence — see `fired_signals`."""
        return fired_signals(self.signals)

    @property
    def fired_kinds(self) -> set[SignalKind]:
        """The kinds of the fired signals, for classification."""
        return {signal.kind for signal in self.fired}


class HealEvent(_Boundary):
    """One trip through the Bright Data heal gate. Written on every terminal outcome."""

    collector_id: NonBlankStr
    status: HealStatus
    created_at: datetime
    prompt: str | None = None
    preview_result: dict[str, Any] | None = None
    promoted: bool = False
    failure_class: FailureClass | None = None
    template_id: str | None = None
    attempts: NonNegativeInt = 1
    error: str | None = None
    id: int | None = None


def latest_settled(events: list[HealEvent]) -> HealEvent | None:
    """The terminal-most heal row, or `None` while the cycle is still at the gate.

    A gated cycle leaves two rows before verification settles it with a third, so a row
    count is not a cycle count and the last row is not the outcome. The facade reads this
    to decide promote or roll back and the benchmark reads it to count a heal as kept —
    written independently in both, which is how the two could have disagreed about the
    same cycle.
    """
    settled = [event for event in events if event.status in TERMINAL_STATUSES]
    return settled[-1] if settled else None


class VerifyReport(_Boundary):
    """How well a healed collector matches golden records — new layout and old.

    `non_regression_passed` is the overfit check: a heal that fixes today's layout by
    breaking yesterday's has not healed anything.
    """

    field_accuracy: Ratio
    non_regression_passed: bool
    attempts: NonNegativeInt
    elapsed_s: NonNegativeFloat


class Baseline(_Boundary):
    """The last known-good shape of a collector's output. Detect compares against this."""

    collector_id: NonBlankStr
    captured_at: datetime
    row_count: NonNegativeInt
    null_rates: dict[str, Ratio] = {}
    skeleton_hash: str | None = None


class BenchCase(_Boundary):
    """One benchmark case's outcome, persisted per case so a multi-hour run resumes.

    `caught_by` is what actually fired, against `expected_signals` which the generator
    declared. The two disagreeing is the coverage matrix's whole subject.

    A **set** of kinds, not an enumerated combination: a class catchable by two detectors
    is `{SCHEMA, NULL_RATE}`, and one nothing catches is the empty set — an honest gap.
    Enumerating combinations (`schema_or_null_rate`, `none`) meant a fifth detector would
    multiply the vocabulary and force `coverage` to decode names by hand; membership is
    just `caught_by in expected_signals`.

    **Required, with no default.** The empty set is a deliberate declaration that nothing
    catches this class, so a forgotten field would persist as a coverage claim rather than
    fail as a construction error.
    """

    run_id: NonBlankStr
    case_id: NonBlankStr
    mutation: MutationClass
    expected_signals: frozenset[SignalKind]
    caught_by: SignalKind | None = None
    healed: bool = False
    field_accuracy: Ratio | None = None
    non_regression_passed: bool | None = None
    attempts: NonNegativeInt = 0
    elapsed_s: NonNegativeFloat = 0.0
    completed_at: datetime | None = None
