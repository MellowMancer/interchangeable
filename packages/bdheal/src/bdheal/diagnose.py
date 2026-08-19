"""Failure class to prompt template. Deterministic: the same verdict renders the same prompt.

The rendered prompt is sent to Bright Data and persisted in a heal event, so it may
contain the caller's field names and nothing else — never a credential, never argv (G6).
That is why nothing from the verdict itself is interpolated: a signal's detail carries
counts and page content, and a prompt is the one string in this package that leaves the
process by design.

Only `FIRED` is evidence. A detector that abstained because the sample was incomplete has
said nothing, so a verdict carrying nothing but abstentions is not broken and `diagnose`
returns no prompt at all. (`classify` still answers `UNKNOWN` for such a verdict — the
generic template is what an unrecognised *fired* signal falls through to, not what an
abstention produces.) What a target-side refusal must *not* do is
produce a prompt on its own: healing cannot unblock a fetch. `detect` already enforces
that by suppressing the volume detectors when the sample is incomplete, so a signal that
survives to `FIRED` is extraction evidence whatever happened to its siblings.
"""

from dataclasses import dataclass

from pydantic import BaseModel

from bdheal.models import CollectorSpec, DetectVerdict
from bdheal.vocabulary import FailureClass, SignalKind

@dataclass(frozen=True, slots=True)
class _Template:
    """A failure class's template id and the instruction it renders.

    One table, not two keyed alike: nothing checked that the instruction table covered
    `FailureClass`, and a miss surfaces as a `KeyError` at render time — the moment a heal
    is most needed. Coverage is now structural; a class cannot be added with only one half.
    """

    template_id: str
    instruction: str


TEMPLATES: dict[FailureClass, _Template] = {
    FailureClass.STRUCTURE_CHANGED: _Template(
        "structure_changed.v1",
        "The page's tag and class structure changed, so the selectors this collector uses no "
        "longer match. Re-locate the repeating row container and re-derive every selector from "
        "the current page.",
    ),
    FailureClass.SCHEMA_MISMATCH: _Template(
        "schema_mismatch.v1",
        "Rows are still being found, but their fields no longer match the shape this collector "
        "declares. Re-derive the selector for each field so it holds the same kind of content it "
        "held before.",
    ),
    FailureClass.EMPTY_RESULT: _Template(
        "empty_result.v1",
        "The collector returns no rows where it previously returned rows. Re-locate the repeating "
        "row container on the current page and extract one object from each repetition.",
    ),
    FailureClass.FIELDS_MISSING: _Template(
        "fields_missing.v1",
        "Rows are still being found, but one or more fields now come back empty across the "
        "sample. Re-locate those fields on the current page without changing how rows are "
        "found.",
    ),
    FailureClass.UNKNOWN: _Template(
        "generic.v1",
        "The collector stopped producing usable rows and the cause could not be narrowed to a "
        "single symptom. Re-derive the repeating row container and every field selector from the "
        "current page.",
    ),
}

# Which fired signal names the failure, in precedence order: a moved tag-and-class tree is
# why the other three fired, so naming one of the symptoms instead would send the heal
# looking for a field on a page whose rows it can no longer find.
_PRECEDENCE: tuple[tuple[SignalKind, FailureClass], ...] = (
    (SignalKind.SKELETON, FailureClass.STRUCTURE_CHANGED),
    (SignalKind.SCHEMA, FailureClass.SCHEMA_MISMATCH),
    (SignalKind.ZERO_ROWS, FailureClass.EMPTY_RESULT),
    (SignalKind.NULL_RATE, FailureClass.FIELDS_MISSING),
)


PROMPT_TEMPLATE = (
    "{instruction}\n"
    "Extract these fields for every row, using exactly these names:\n"
    "{fields}\n"
    "Return one object per row, with these fields and no others."
)


@dataclass(frozen=True, slots=True)
class Diagnosis:
    """What broke, which template says so, and the prompt that came out of it."""

    failure_class: FailureClass
    template_id: str
    prompt: str


def classify(verdict: DetectVerdict) -> FailureClass:
    """Pick the failure class from the fired signals. Unrecognised falls through to UNKNOWN."""
    fired = verdict.fired_kinds
    for kind, failure_class in _PRECEDENCE:
        if kind in fired:
            return failure_class
    return FailureClass.UNKNOWN


def diagnose(spec: CollectorSpec, verdict: DetectVerdict) -> Diagnosis | None:
    """Render the heal prompt for a broken verdict. A healthy verdict yields `None`."""
    if not verdict.broken:
        return None
    failure_class = classify(verdict)
    return Diagnosis(
        failure_class=failure_class,
        template_id=TEMPLATES[failure_class].template_id,
        prompt=_render(failure_class, spec.row_schema),
    )


def _render(failure_class: FailureClass, row_schema: type[BaseModel]) -> str:
    """The template filled with the caller's field names, in the order they were declared."""
    fields = "\n".join(f"- {field}" for field in row_schema.model_fields)
    return PROMPT_TEMPLATE.format(instruction=TEMPLATES[failure_class].instruction, fields=fields)
