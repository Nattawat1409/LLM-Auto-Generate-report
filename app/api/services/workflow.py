"""Start/resume the compiled graph.

This is the ONLY module allowed to import app.graph (see CLAUDE.md "API service
responsibilities"). Every call site that touches the graph goes through
run_in_threadpool since graph.invoke()/get_state() are synchronous and would
otherwise block the event loop (see CLAUDE.md "Architecture decision —
LangGraph in-process").
"""
import uuid
from typing import Optional

from starlette.concurrency import run_in_threadpool
from langgraph.types import Command

from app.graph import graph, close_checkpointer
from app.api.schemas.reports import SessionView

# setting up thread-id
def _config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}

# define if have interrupts show otherwise display "None"
def _interrupt_value(result: dict) -> Optional[dict]:
    interrupts = result.get("__interrupt__")
    return interrupts[0].value if interrupts else None # if have return interupt otherwise return "None"


async def start_report(question: str) -> SessionView:
    thread_id = str(uuid.uuid4())
    result = await run_in_threadpool(
        graph.invoke, {"user_input": question}, config=_config(thread_id)
    )
    return SessionView.from_state(thread_id, result, _interrupt_value(result))


async def resume(thread_id: str, resume_payload: dict) -> SessionView:
    """Resume whichever interrupt the graph is currently paused at.

    Used for both /review (human_in_the_loop) and /personalize — the graph
    itself resumes wherever its checkpoint says it's paused, regardless of
    which named endpoint the caller used. Callers validate the current status
    matches the expected step before calling this (see routers/reports.py).
    """
    result = await run_in_threadpool(
        graph.invoke, Command(resume=resume_payload), config=_config(thread_id)
    )
    return SessionView.from_state(thread_id, result, _interrupt_value(result))


async def get_snapshot(thread_id: str):
    return await run_in_threadpool(graph.get_state, _config(thread_id))


async def shutdown() -> None:
    await run_in_threadpool(close_checkpointer)