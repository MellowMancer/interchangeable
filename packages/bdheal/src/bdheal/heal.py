"""The heal gate: heal, then awaiting_approval, then approve or reject.

The collector id is byte-identical before and after — Bright Data heals in place. A heal
event is written through `HealStore` on every terminal outcome, rejection and failure
included, because a heal log with only successes in it is not an audit trail.

The gate owns two decisions the adapter must not: whether a status counts as *promoted*,
and whether an outcome is worth remembering. `studio.py` reports what the CLI said; what
that means for the collector is decided here, one layer in.
"""

from collections.abc import Callable
from typing import Any

from bdheal.diagnose import Diagnosis
from bdheal.errors import NotPendingError, StudioError
from bdheal.models import CollectorSpec, HealEvent
from bdheal.ports import Clock, HealStore, StudioClient
from bdheal.vocabulary import HealStatus

# The one status that means the live collector actually changed. It lives here rather
# than in the adapter because "promoted" is a judgement about the collector, not a field
# the CLI returns: a fifth status, or a rule that reads "promoted and verified", is a
# change to the gate's policy and belongs where the policy is.
PROMOTED_STATUS = HealStatus.DONE


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
    return _record(
        lambda: studio.heal(spec, diagnosis.prompt, auto_approve=auto_approve),
        spec,
        store,
        clock,
        {
            "prompt": diagnosis.prompt,
            "failure_class": diagnosis.failure_class,
            "template_id": diagnosis.template_id,
        },
    )


def approve(
    spec: CollectorSpec,
    event: HealEvent,
    studio: StudioClient,
    store: HealStore,
    clock: Clock,
    *,
    reject: bool = False,
) -> HealEvent:
    """Promote or reject a pending heal, anchored on the collector's first anchor URL.

    Refuses an event that is not waiting at the gate: a second `approve` on a settled heal
    is a paid call that decides nothing, and the CLI would accept it.
    """
    if event.status is not HealStatus.AWAITING_APPROVAL:
        raise NotPendingError(
            f"heal for {event.collector_id} is {event.status}, not awaiting approval"
        )
    return _record(
        lambda: studio.approve(spec, spec.anchor_urls[0], reject=reject),
        spec,
        store,
        clock,
        {
            "prompt": event.prompt,
            "failure_class": event.failure_class,
            "template_id": event.template_id,
            "attempts": event.attempts,
        },
    )


def _record(
    call: Callable[[], HealEvent],
    spec: CollectorSpec,
    store: HealStore,
    clock: Clock,
    audit: dict[str, Any],
) -> HealEvent:
    """Make one gate call and persist its outcome. A failure is recorded, then re-raised.

    `audit` is what the CLI's envelope cannot know — which diagnosis this heal answers —
    and it is carried onto every row so a rejection or a failure reads back as evidence.
    """
    try:
        settled = call()
    except StudioError as exc:
        store.save_heal_event(_failure(spec, clock, audit, exc))
        raise
    return store.save_heal_event(
        settled.model_copy(update={**audit, "promoted": _promoted(settled.status)})
    )


def _failure(
    spec: CollectorSpec, clock: Clock, audit: dict[str, Any], exc: StudioError
) -> HealEvent:
    """The row a failed gate call leaves behind. There is no envelope, so the clock dates it."""
    return HealEvent(
        collector_id=spec.collector_id,
        status=HealStatus.FAILED,
        created_at=clock.now(),
        promoted=False,
        error=str(exc),
        **audit,
    )


def _promoted(status: HealStatus) -> bool:
    """Whether this outcome changed the live collector — the gate's call, not the CLI's."""
    return status is PROMOTED_STATUS
