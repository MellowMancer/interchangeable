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


class CollectorCreateError(StudioError):
    """`scraper create` failed after the AI-generation trigger.

    Bright Data leaves the half-built collector behind and exposes no programmatic
    delete, so the message must name the orphaned id for manual removal in the web UI.
    """
