"""Closed vocabularies. Every state a signal, heal or mutation may be in, named once."""

from enum import StrEnum


class SignalKind(StrEnum):
    """The four break detectors. None of them names a problem domain — that is the point."""

    SCHEMA = "schema"
    ROW_COUNT = "row_count"
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
    ROWS_LOST = "rows_lost"
    FIELDS_MISSING = "fields_missing"
    UNKNOWN = "unknown"


class HealStatus(StrEnum):
    """Bright Data's heal state machine, plus the two terminal states we record ourselves."""

    AWAITING_APPROVAL = "awaiting_approval"
    DONE = "done"
    REJECTED = "rejected"
    FAILED = "failed"


# The statuses that end a heal cycle. A gated cycle writes two rows and an unattended or
# failed one writes a single row, so a cycle's outcome is read from its terminal-most row
# and never from how many rows it left behind. Derived from `HealStatus` rather than
# listed, because it was listed twice — the facade's promote/rollback decision and the
# benchmark's `healed` count — and a fifth status would have reached only one of them.
TERMINAL_STATUSES: frozenset[HealStatus] = frozenset(HealStatus) - {HealStatus.AWAITING_APPROVAL}

# Which fired signal names the failure, in precedence order. A moved tag-and-class tree is
# *why* the other three fired, so crediting a symptom would send the heal looking for a
# field on a page whose rows it can no longer find, and would tell the coverage matrix
# that a detector caught a class it only saw the consequences of. `diagnose` maps it to a
# failure class and the benchmark credits a detector by it: one order, two readers.
SIGNAL_PRECEDENCE: tuple[SignalKind, ...] = (
    SignalKind.SKELETON,
    SignalKind.SCHEMA,
    SignalKind.ROW_COUNT,
    SignalKind.NULL_RATE,
)


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
# THROTTLE: the one refusal that clears up on its own, which is why it gets its own word
# in an operator-facing reason. All three codes, not just the observed one: a policy
# keyed to a single literal calls the vendor's own documented codes something else.
THROTTLE_CODES: frozenset[str] = frozenset(
    {
        "global_rate_limit",
        "bucket_rate_limit",
        "rate_limit",  # observed live in a real payload, though absent from the reference
    }
)

# REFUSAL: the target would not serve us. Retrying is the answer; healing cannot unblock
# a fetch. Throttling is a refusal too, so the set is composed rather than re-listed.
TARGET_REFUSAL_CODES: frozenset[str] = THROTTLE_CODES | {
    "blocked",
    "captcha_timeout",
    "unspecified",  # an error payload the CLI reported without naming a code
}

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


# "This sample cannot be trusted": the target refused part of it, or might have. Three
# readers need it — `detect` to suppress the volume signals, `verify` to refuse to score,
# and `healer` to refuse to store a baseline from a truncated run. Composed here rather
# than spelled three ways, so a fifth code class lands in one place.
UNTRUSTWORTHY_SAMPLE_CODES: frozenset[str] = TARGET_REFUSAL_CODES | AMBIGUOUS_CODES
