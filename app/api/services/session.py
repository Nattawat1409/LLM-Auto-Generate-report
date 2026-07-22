"""thread_id lifecycle + reading persisted state via the checkpointer.

Never imports app.graph directly — reads state through
workflow.get_snapshot(), the only function allowed to touch the compiled
graph (see CLAUDE.md "API service responsibilities").
"""
from typing import Optional

from app.api.services import workflow
from app.api.schemas.reports import SessionView
from app.api.errors import SessionNotFoundError


def _interrupt_value(snapshot) -> Optional[dict]:
    for task in snapshot.tasks:
        if task.interrupts:
            return task.interrupts[0].value
    return None


async def get_session_view(thread_id: str) -> SessionView:
    snapshot = await workflow.get_snapshot(thread_id)
    if not snapshot.values:
        # LangGraph doesn't error on an unknown thread_id — it returns an
        # empty snapshot, which is otherwise indistinguishable from "done".
        raise SessionNotFoundError(thread_id)
    return SessionView.from_state(thread_id, snapshot.values, _interrupt_value(snapshot))
