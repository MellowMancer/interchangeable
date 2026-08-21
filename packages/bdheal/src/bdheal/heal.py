"""The heal gate: heal, then awaiting_approval, then approve or reject.

The collector id is byte-identical before and after — Bright Data heals in place. A heal
event is written through `HealStore` on every terminal outcome, rejection and failure
included, because a heal log with only successes in it is not an audit trail.

The gate owns two decisions the adapter must not: whether a status counts as *promoted*,
and whether an outcome is worth remembering. `studio.py` reports what the CLI said; what
that means for the collector is decided here, one layer in.

It also owns the obligation to close what it opened. Bright Data allows one open job per
collector, so a heal that raised on its way out leaves the collector *occupied*, not
merely unhealed: on 2026-08-20 an envelope this package could not parse left a completed
repair parked at the approval gate, and for the next five hours every heal on that
collector was refused. The repair itself was fine. Nothing here may exit through an
exception without first trying to reject whatever it left waiting.
"""

from collections.abc import Callable
from typing import Any

from bdheal.diagnose import Diagnosis
from bdheal.errors import GateBusyError, NotPendingError, StudioError
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
        studio,
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
        studio,
        store,
        clock,
        {
            "prompt": event.prompt,
            "failure_class": event.failure_class,
            "template_id": event.template_id,
            "attempts": event.attempts,
        },
    )


def release_gate(spec: CollectorSpec, studio: StudioClient) -> HealEvent:
    """Reject whatever is parked at this collector's approval gate, freeing it for the next heal.

    Deliberately takes no `HealEvent`: `approve` needs one and refuses anything not
    `awaiting_approval`, and the case this exists for is precisely the one where the event
    was never built — the envelope that would have carried it is what raised. What is
    pending is Bright Data's state, not ours, so the collector's own anchor is enough to
    name it. Rejecting rather than approving because an unreviewed repair must not be
    promoted by a cleanup, and because a gate nobody closes costs the collector's
    availability until a human notices.
    """
    return studio.approve(spec, spec.anchor_urls[0], reject=True)


def _record(
    call: Callable[[], HealEvent],
    spec: CollectorSpec,
    studio: StudioClient,
    store: HealStore,
    clock: Clock,
    audit: dict[str, Any],
) -> HealEvent:
    """Make one gate call and persist its outcome. A failure is recorded, then re-raised.

    `audit` is what the CLI's envelope cannot know — which diagnosis this heal answers —
    and it is carried onto every row so a rejection or a failure reads back as evidence.

    Every failure also releases the gate, and the second clause catches `Exception` rather
    than a named type on purpose: the outage this prevents was caused by an exception
    nobody had anticipated on this path, so narrowing the net to the types already thought
    of would leave exactly the hole that cost five hours of a collector's availability.
    Nothing is swallowed — the original error is re-raised either way.
    """
    try:
        settled = call()
    except StudioError as exc:
        store.save_heal_event(_failure(spec, clock, audit, exc))
        _release_or_note(spec, studio, exc)
        raise
    except Exception as exc:
        _release_or_note(spec, studio, exc)
        raise
    return store.save_heal_event(
        settled.model_copy(update={**audit, "promoted": _promoted(settled.status)})
    )


def _release_or_note(spec: CollectorSpec, studio: StudioClient, failure: Exception) -> None:
    """Try to free the gate; if that fails too, say so on the error already on its way out.

    The cleanup must not become the failure the caller sees. Raising here would replace a
    parse error with "no job pending" and send whoever reads it debugging the wrong call,
    and `raise ... from` inside this handler would do the same to the traceback's headline.
    A note travels with the original exception instead, so a rejection that did not work
    is visible without displacing the reason it was attempted. `Exception`, for the same
    reason the caller's net is that wide: anything this rejection can raise — a refusal, a
    timeout, a shape nobody foresaw — would otherwise replace the failure being reported.
    """
    try:
        release_gate(spec, studio)
    except Exception as cleanup:
        failure.add_note(f"the pending heal gate could not be rejected: {cleanup}")


def _failure(
    spec: CollectorSpec, clock: Clock, audit: dict[str, Any], exc: StudioError
) -> HealEvent:
    """The row a failed gate call leaves behind. There is no envelope, so the clock dates it."""
    return HealEvent(
        collector_id=spec.collector_id,
        status=_failure_status(exc),
        created_at=clock.now(),
        promoted=False,
        error=str(exc),
        **audit,
    )


def _failure_status(exc: StudioError) -> HealStatus:
    """Which terminal state a failed gate call left behind — refused to start, or lost.

    `failed` reads as a repair that was attempted and did not work. A collector still
    holding an earlier job never got that far, and a later run may find it free, so the
    two must be tellable apart by anyone reading the log or counting heals.
    """
    return HealStatus.GATE_BUSY if isinstance(exc, GateBusyError) else HealStatus.FAILED


def _promoted(status: HealStatus) -> bool:
    """Whether this outcome changed the live collector — the gate's call, not the CLI's."""
    return status is PROMOTED_STATUS
