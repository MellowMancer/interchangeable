"""Failure class, template id, and the exact prompt that leaves the process.

The golden strings here are a contract, not a formality. The rendered prompt is what
Bright Data's AI actually acts on, and a heal cycle costs minutes and credits — a vague
or mis-selected prompt does not merely fail, it can promote a collector fitted to the
wrong reading of the page.

Two rules the assertions exist to pin. First, only `FIRED` is evidence: a detector that
abstained because the sample was incomplete has said nothing, and a verdict carrying
nothing but abstentions falls through to the generic template rather than raising.
Second, the prompt is sent to a third party, so it may name the caller's schema fields
and the structural symptom and nothing else — no signal detail, no page content, no
credential (G6).
"""


import pytest
from conftest import FAKE_API_KEY, SampleRow
from pydantic import BaseModel

from bdheal.diagnose import _FAILURE_BY_KIND, TEMPLATES, classify, diagnose
from bdheal.models import CollectorSpec, DetectVerdict, Signal
from bdheal.vocabulary import SIGNAL_PRECEDENCE, FailureClass, SignalKind, SignalOutcome


# Deliberately carries raw page content and a row count: whatever a detector puts in a
# detail, none of it may reach a prompt bound for a third party.
DETAIL = "<li class=\"row\">41 of 60 rows did not validate</li>"

CREDENTIAL_WORDS = ("api_key", "apikey", "token", "secret", "bearer", "password")

FIELD_LIST = "- title\n- url\n- published"

STRUCTURE_CHANGED_PROMPT = (
    "The page's tag and class structure changed, so the selectors this collector uses no "
    "longer match. Re-locate the repeating row container and re-derive every selector from "
    "the current page.\n"
    "Extract these fields for every row, using exactly these names:\n"
    f"{FIELD_LIST}\n"
    "Return one object per row, with these fields and no others."
)

SCHEMA_MISMATCH_PROMPT = (
    "Rows are still being found, but their fields no longer match the shape this collector "
    "declares. Re-derive the selector for each field so it holds the same kind of content it "
    "held before.\n"
    "Extract these fields for every row, using exactly these names:\n"
    f"{FIELD_LIST}\n"
    "Return one object per row, with these fields and no others."
)

EMPTY_RESULT_PROMPT = (
    "The collector returns no rows where it previously returned rows. Re-locate the repeating "
    "row container on the current page and extract one object from each repetition.\n"
    "Extract these fields for every row, using exactly these names:\n"
    f"{FIELD_LIST}\n"
    "Return one object per row, with these fields and no others."
)

FIELDS_MISSING_PROMPT = (
    "Rows are still being found, but one or more fields now come back empty across the "
    "sample. Re-locate those fields on the current page without changing how rows are "
    "found.\n"
    "Extract these fields for every row, using exactly these names:\n"
    f"{FIELD_LIST}\n"
    "Return one object per row, with these fields and no others."
)

GENERIC_PROMPT = (
    "The collector stopped producing usable rows and the cause could not be narrowed to a "
    "single symptom. Re-derive the repeating row container and every field selector from the "
    "current page.\n"
    "Extract these fields for every row, using exactly these names:\n"
    f"{FIELD_LIST}\n"
    "Return one object per row, with these fields and no others."
)

# signal kind that fired -> failure class, template id, rendered prompt
CASES: tuple[tuple[SignalKind, FailureClass, str, str], ...] = (
    (
        SignalKind.SKELETON,
        FailureClass.STRUCTURE_CHANGED,
        "structure_changed.v1",
        STRUCTURE_CHANGED_PROMPT,
    ),
    (
        SignalKind.SCHEMA,
        FailureClass.SCHEMA_MISMATCH,
        "schema_mismatch.v1",
        SCHEMA_MISMATCH_PROMPT,
    ),
    (
        SignalKind.ZERO_ROWS,
        FailureClass.EMPTY_RESULT,
        "empty_result.v1",
        EMPTY_RESULT_PROMPT,
    ),
    (
        SignalKind.NULL_RATE,
        FailureClass.FIELDS_MISSING,
        "fields_missing.v1",
        FIELDS_MISSING_PROMPT,
    ),
)

ALL_PROMPTS = (
    STRUCTURE_CHANGED_PROMPT,
    SCHEMA_MISMATCH_PROMPT,
    EMPTY_RESULT_PROMPT,
    FIELDS_MISSING_PROMPT,
    GENERIC_PROMPT,
)


class OtherRow(BaseModel):
    """A second caller's schema, declared out of alphabetical order to pin field ordering."""

    headline: str
    reference: str
    issued: str | None = None


def _signal(kind: SignalKind, outcome: SignalOutcome = SignalOutcome.FIRED) -> Signal:
    """One detector's reading, with a detail no prompt is allowed to repeat."""
    return Signal(kind=kind, outcome=outcome, detail=DETAIL)


def _verdict(*signals: Signal, broken: bool = True, incomplete: bool = False) -> DetectVerdict:
    """A verdict shaped exactly as `detect` builds one."""
    return DetectVerdict(
        broken=broken,
        signals=list(signals),
        incomplete=incomplete,
        retry_requested=incomplete,
        reason=DETAIL if incomplete else None,
    )


@pytest.mark.parametrize(("kind", "failure_class", "template_id", "prompt"), CASES)
def test_each_failure_class_selects_its_template_and_renders_its_prompt(
    spec: CollectorSpec,
    kind: SignalKind,
    failure_class: FailureClass,
    template_id: str,
    prompt: str,
) -> None:
    """The table the whole feature is: one fired signal in, one exact prompt out."""
    diagnosis = diagnose(spec, _verdict(_signal(kind)))

    assert diagnosis is not None
    assert diagnosis.failure_class is failure_class
    assert diagnosis.template_id == template_id
    assert diagnosis.prompt == prompt


def test_a_verdict_with_no_recognised_class_falls_through_to_the_generic_template(
    spec: CollectorSpec,
) -> None:
    """Broken with nothing named is still broken. Refusing to answer would be the defect."""
    diagnosis = diagnose(spec, _verdict())

    assert diagnosis is not None
    assert diagnosis.failure_class is FailureClass.UNKNOWN
    assert diagnosis.template_id == TEMPLATES[FailureClass.UNKNOWN].template_id == "generic.v1"
    assert diagnosis.prompt == GENERIC_PROMPT


def test_an_abstaining_detector_is_not_evidence() -> None:
    """`INCONCLUSIVE` means the detector could not see, not that it saw a break."""
    verdict = _verdict(
        _signal(SignalKind.ZERO_ROWS, SignalOutcome.INCONCLUSIVE),
        _signal(SignalKind.NULL_RATE, SignalOutcome.INCONCLUSIVE),
        incomplete=True,
    )

    assert classify(verdict) is FailureClass.UNKNOWN


def test_a_healthy_verdict_produces_no_prompt(spec: CollectorSpec) -> None:
    """Nothing broke, so there is nothing to say — and a heal cycle costs credits."""
    assert diagnose(spec, _verdict(broken=False)) is None


def test_a_target_side_refusal_alone_produces_no_prompt(spec: CollectorSpec) -> None:
    """Healing cannot unblock a fetch. A refused sample is a retry, never a prompt."""
    verdict = _verdict(
        _signal(SignalKind.ZERO_ROWS, SignalOutcome.INCONCLUSIVE),
        broken=False,
        incomplete=True,
    )

    assert verdict.retry_requested is True
    assert diagnose(spec, verdict) is None


def test_a_schema_break_inside_an_incomplete_sample_still_produces_a_prompt(
    spec: CollectorSpec,
) -> None:
    """A malformed row is malformed regardless of what the target did to its siblings.

    `detect` already suppresses the volume detectors when the sample is incomplete, so a
    signal that survived to `FIRED` is extraction evidence by construction. Dropping it
    here because a sibling row was refused is the silence the loop exists to prevent.
    """
    verdict = _verdict(
        _signal(SignalKind.SCHEMA),
        _signal(SignalKind.ZERO_ROWS, SignalOutcome.INCONCLUSIVE),
        incomplete=True,
    )
    diagnosis = diagnose(spec, verdict)

    assert diagnosis is not None
    assert diagnosis.failure_class is FailureClass.SCHEMA_MISMATCH
    assert diagnosis.prompt == SCHEMA_MISMATCH_PROMPT


def test_the_structural_signal_wins_when_several_fired() -> None:
    """A moved tree is why the other three fired. Naming a symptom would misdirect the heal."""
    verdict = _verdict(*(_signal(kind) for kind in SignalKind))

    assert classify(verdict) is FailureClass.STRUCTURE_CHANGED


def test_every_failure_class_maps_to_a_template() -> None:
    """A class with no template would raise at the moment a heal was most needed."""
    assert set(TEMPLATES) == set(FailureClass)
    assert len({template.template_id for template in TEMPLATES.values()}) == len(FailureClass)
    assert all(template.instruction for template in TEMPLATES.values())


@pytest.mark.parametrize("kind", list(SignalKind))
def test_the_prompt_names_the_callers_fields_in_declaration_order(kind: SignalKind) -> None:
    """The prompt is rendered from `row_schema`, so a second caller gets a second prompt."""
    spec = CollectorSpec(
        collector_id="c_other0000000000000",
        name="another collector",
        anchor_urls=["https://example.test/other"],
        row_schema=OtherRow,
    )
    diagnosis = diagnose(spec, _verdict(_signal(kind)))

    assert diagnosis is not None
    assert "- headline\n- reference\n- issued" in diagnosis.prompt
    for field in SampleRow.model_fields:
        assert field not in diagnosis.prompt


@pytest.mark.parametrize("kind", list(SignalKind))
def test_the_prompt_repeats_no_signal_detail(spec: CollectorSpec, kind: SignalKind) -> None:
    """Details carry counts and page content. The prompt leaves the process; they do not."""
    diagnosis = diagnose(spec, _verdict(_signal(kind), incomplete=True))

    assert diagnosis is not None
    assert DETAIL not in diagnosis.prompt
    assert "41 of 60" not in diagnosis.prompt


@pytest.mark.parametrize("prompt", ALL_PROMPTS)
def test_no_prompt_carries_a_credential(monkeypatch: pytest.MonkeyPatch, prompt: str) -> None:
    """G6: the prompt is sent to a third party and persisted. It never reads the environment."""
    monkeypatch.setenv("BRIGHTDATA_API_KEY", FAKE_API_KEY)

    assert FAKE_API_KEY not in prompt
    for word in CREDENTIAL_WORDS:
        assert word not in prompt.lower()


@pytest.mark.parametrize("kind", list(SignalKind))
def test_diagnosing_the_same_verdict_twice_renders_the_same_prompt(
    spec: CollectorSpec, kind: SignalKind
) -> None:
    """Determinism: the golden strings only mean anything if the render is reproducible."""
    verdict = _verdict(_signal(kind))

    assert diagnose(spec, verdict) == diagnose(spec, verdict)


def test_every_ranked_detector_names_a_failure_class() -> None:
    """The precedence order lives in `vocabulary`; this module only says what each rank means.

    Mapping by key rather than by position is deliberate: zipping two tuples would make a
    reorder of the shared order silently repoint every detector at the wrong template.
    """
    assert set(_FAILURE_BY_KIND) == set(SIGNAL_PRECEDENCE)
