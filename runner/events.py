"""Which conversion events to send, and sending them with a confirmed flush (spec step 8)."""

from __future__ import annotations

from runner.config import EVENT_OVER_BUDGET, EVENT_VERIFIED
from runner.flags import FlagsmithClient


def decide_events(passed: bool, limit_hit: str, runner_error: bool) -> list[str]:
    """integration_verified only if the grader passed; over_budget only if a limit was hit;
    nothing at all when the runner itself failed."""
    if runner_error:
        return []
    events = []
    if passed:
        events.append(EVENT_VERIFIED)
    if limit_hit != "none":
        events.append(EVENT_OVER_BUDGET)
    return events


def send_events(
    client: FlagsmithClient, events: list[str], trial_id: str, stack: str
) -> tuple[list[str], bool]:
    """Track each event, flush, and report (events_sent, flush_confirmed).

    events_sent only lists events whose flush returned without raising. With nothing to send we
    still return confirmed=True (nothing outstanding). The exposure event recorded earlier by
    get_experiment_flag is in the same buffer, so the flush covers it too."""
    for e in events:
        client.send_event(e, trial_id, stack)
    try:
        client.flush()
    except Exception:  # noqa: BLE001 - any failure means delivery is unconfirmed
        return [], False
    return list(events), True
