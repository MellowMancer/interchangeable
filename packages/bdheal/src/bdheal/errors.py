"""The package's error contract.

It lives in the innermost layer so a use case can catch what an adapter raises without
importing outward. No message here may carry an API key, token or argv (G6).
"""


class BdhealError(Exception):
    """Base for every error this package raises."""


class StudioError(BdhealError):
    """A `bdata` invocation failed."""


class StudioResponseError(StudioError):
    """`bdata` returned output that is not the documented JSON shape."""


class GateBusyError(StudioError):
    """Bright Data refused a heal because an earlier job on that collector is still open.

    A `StudioError` subclass so every caller already guarding on the base type keeps
    working, and its own type because this is the one refusal that is *recoverable*: the
    collector is fine, it is merely occupied. On 2026-08-20 a heal raised on its way out
    of the approval gate, so nothing ever answered the approval Bright Data was parked at,
    and for the next five hours every heal on that collector came back "Another refactor
    job is still in progress / Status: 409". Rejecting the pending gate freed it at once.
    Told apart from a heal that failed on its merits, that recovery can be automatic.
    """


class CollectorCreateError(StudioError):
    """`scraper create` failed after the AI-generation trigger.

    Bright Data leaves the half-built collector behind and exposes no programmatic
    delete, so the message must name the orphaned id for manual removal in the web UI.
    """


class VerificationIncompleteError(BdhealError):
    """A verification pass the target refused part of, so no score can be published.

    Raised rather than returned because `VerifyReport` has no third value: reporting
    `non_regression_passed=False` for a sample that was throttled or blocked would accuse
    a heal of overfitting on evidence that was never gathered, and reporting `True` would
    publish a check nobody performed. The caller retries; only the loop can decide that.
    """


class NotPendingError(BdhealError):
    """`approve` was called on a heal that is not waiting at the gate.

    Every gate call is paid, so approving an already-settled event spends money to decide
    something already decided. Raised before anything reaches the CLI.
    """
