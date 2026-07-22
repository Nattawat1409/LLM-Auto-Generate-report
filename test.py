"""
Demo: how `thread_id` + a checkpointer give each conversation/report its own
isolated, resumable state in LangGraph — this is the same mechanism app/graph.py
uses so two Gradio browser sessions (or two report requests) never mix state.

Run: uv run python test.py
"""
from typing_extensions import TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph


class State(TypedDict):
    counter: int
    history: list[str]


def my_node(state: State, config: RunnableConfig) -> dict:
    # RunnableConfig is a TypedDict (a plain dict) — index/`.get()` it,
    # never dot-access it like an object.
    thread_id = config["configurable"]["thread_id"]

    counter = state.get("counter", 0) + 1
    history = state.get("history", []) + [f"call #{counter}"]

    print(f"[thread={thread_id}] call #{counter}")
    return {"counter": counter, "history": history}


builder = StateGraph(State)
builder.add_node("my_node", my_node)
builder.add_edge(START, "my_node")
builder.add_edge("my_node", END)

# InMemorySaver, not SqliteSaver: this is a throwaway demo script, no need for
# state to survive past this process (app/graph.py uses SqliteSaver instead).
graph = builder.compile(checkpointer=InMemorySaver())


def run(thread_id: str) -> dict:
    """Every call needs a thread_id — the graph won't run without one once a
    checkpointer is attached, since it has to know which thread's state to load."""
    config = {"configurable": {"thread_id": thread_id}}
    return graph.invoke({}, config=config)


if __name__ == "__main__":
    print("== Thread A, called twice — same thread_id resumes prior state ==")
    print(run("thread-A"))
    print(run("thread-A"))

    print("\n== Thread B, called once — a different thread_id starts fresh ==")
    print(run("thread-B"))

    print("\n== Back to Thread A — picks up at counter=2, not reset by Thread B ==")
    print(run("thread-A"))
