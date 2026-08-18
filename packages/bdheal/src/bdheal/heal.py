"""The heal gate: heal, then awaiting_approval, then approve or reject.

The collector id is byte-identical before and after — Bright Data heals in place. A heal
event is written through `HealStore` on every terminal outcome, rejection and failure
included, because a heal log with only successes in it is not an audit trail.
"""

from bdheal.diagnose import Diagnosis
from bdheal.models import CollectorSpec, HealEvent
from bdheal.ports import Clock, HealStore, StudioClient


def heal(
    spec: CollectorSpec,
    diagnosis: Diagnosis,
    studio: StudioClient,
    store: HealStore,
    clock: Clock,
    *,
    auto_approve: bool = False,
) -> HealEvent:
    """Send the prompt to Bright Data. Returns the pending event, or a promoted one if unattended."""
    raise NotImplementedError


def approve(
    spec: CollectorSpec,
    event: HealEvent,
    studio: StudioClient,
    store: HealStore,
    clock: Clock,
    *,
    reject: bool = False,
) -> HealEvent:
    """Promote or reject a pending heal, anchored on the collector's first anchor URL."""
    raise NotImplementedError
