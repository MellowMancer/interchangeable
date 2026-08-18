"""Failure class to prompt template. Deterministic: the same verdict renders the same prompt.

The rendered prompt is sent to Bright Data and persisted in a heal event, so it may
contain the caller's field names and nothing else — never a credential, never argv (G6).
"""

from dataclasses import dataclass

from bdheal.models import CollectorSpec, DetectVerdict
from bdheal.vocabulary import FailureClass

TEMPLATE_IDS: dict[FailureClass, str] = {
    FailureClass.STRUCTURE_CHANGED: "structure_changed.v1",
    FailureClass.SCHEMA_MISMATCH: "schema_mismatch.v1",
    FailureClass.EMPTY_RESULT: "empty_result.v1",
    FailureClass.FIELDS_MISSING: "fields_missing.v1",
    FailureClass.UNKNOWN: "generic.v1",
}


@dataclass(frozen=True, slots=True)
class Diagnosis:
    """What broke, which template says so, and the prompt that came out of it."""

    failure_class: FailureClass
    template_id: str
    prompt: str


def classify(verdict: DetectVerdict) -> FailureClass:
    """Pick the failure class from the fired signals. Unrecognised falls through to UNKNOWN."""
    raise NotImplementedError


def diagnose(spec: CollectorSpec, verdict: DetectVerdict) -> Diagnosis | None:
    """Render the heal prompt for a broken verdict. A healthy verdict yields `None`."""
    raise NotImplementedError
