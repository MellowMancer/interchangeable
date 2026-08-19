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


# Row-level `error_code` classes, taken from Bright Data's published reference
# (docs.brightdata.com/datasets/scraper-studio/error-codes), not guessed. An earlier
# hand-rolled set got four of five names wrong — `rate_limit` for `global_rate_limit` /
# `bucket_rate_limit`, `captcha` for `captcha_timeout` — and missed four codes entirely.
#
# REFUSAL: the target would not serve us. Retrying is the answer; healing cannot unblock
# a fetch.
TARGET_REFUSAL_CODES: frozenset[str] = frozenset(
    {
        "blocked",
        "captcha_timeout",
        "global_rate_limit",
        "bucket_rate_limit",
        "rate_limit",  # observed live in a real payload, though absent from the reference
        "unspecified",  # an error payload the CLI reported without naming a code
    }
)

# COLLECTOR: the scraper's own code failed. Retrying reproduces it exactly; a heal is the
# only thing that fixes it. `parse_error` was observed 19 times in one real payload —
# the price parser failing on pages that had loaded perfectly well.
COLLECTOR_FAULT_CODES: frozenset[str] = frozenset(
    {"bad_input", "parse_error", "wait_element_timeout"}
)

# AMBIGUOUS: Bright Data marks these "either/both — debug required", and a real payload
# proved why. 980 `dead_page` rows came from the collector resolving relative links
# against the site root instead of the current page, so every link off page 2 onward
# 404'd — the collector's fault, under a code the vendor documents as the target's.
# Whether it is one or the other depends on something `detect` cannot see, so the policy
# is: report it, retry once, and treat it as extraction evidence only if it survives.
AMBIGUOUS_CODES: frozenset[str] = frozenset(
    {"dead_page", "crawl_error", "ajax_request_error", "timeout"}
)
