"""Closed vocabularies. Every state a signal, heal or mutation may be in, named once."""

from enum import StrEnum


class SignalKind(StrEnum):
    """The four break detectors. None of them names a problem domain — that is the point."""

    SCHEMA = "schema"
    ZERO_ROWS = "zero_rows"
    SKELETON = "skeleton"
    NULL_RATE = "null_rate"


class SignalOutcome(StrEnum):
    """Whether a detector reached a conclusion.

    `INCONCLUSIVE` exists because a throttled run is an incomplete sample: the
    volume-based detectors must abstain rather than call a break they cannot see.
    """

    FIRED = "fired"
    INCONCLUSIVE = "inconclusive"


class FailureClass(StrEnum):
    """What diagnose concluded went wrong. Selects the prompt template."""

    STRUCTURE_CHANGED = "structure_changed"
    SCHEMA_MISMATCH = "schema_mismatch"
    EMPTY_RESULT = "empty_result"
    FIELDS_MISSING = "fields_missing"
    UNKNOWN = "unknown"


class HealStatus(StrEnum):
    """Bright Data's heal state machine, plus the two terminal states we record ourselves."""

    AWAITING_APPROVAL = "awaiting_approval"
    DONE = "done"
    REJECTED = "rejected"
    FAILED = "failed"


class MutationClass(StrEnum):
    """The nine benchmark perturbations. Structure and text only, never meaning."""

    CLASS_RENAME = "class_rename"
    TABLE_TO_DIV = "table_to_div"
    COLUMN_REORDER = "column_reorder"
    LINK_LABEL = "link_label"
    URL_PATTERN = "url_pattern"
    DATE_FORMAT = "date_format"
    FIELD_SPLIT_MERGE = "field_split_merge"
    WRAPPER_NESTING = "wrapper_nesting"
    PAGINATION = "pagination"


class ExpectedSignal(StrEnum):
    """The detector a mutation class is declared to trip.

    `NONE` is a legitimate declaration: a class no detector can see is published as a
    coverage gap, not hidden as a benchmark failure.
    """

    SKELETON = "skeleton"
    SCHEMA = "schema"
    SCHEMA_OR_NULL_RATE = "schema_or_null_rate"
    NONE = "none"
