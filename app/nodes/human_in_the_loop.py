from typing import Literal
from langgraph.types import Command, interrupt
from models import state

# the report templates the user can pick (report/templates/{name}.html)
# "generic" fallback for ad-hoc queries + 3 fixed formats
VALID_TEMPLATES = ("generic", "sales", "customer", "collection_payment")

    # define next node depend on user satisfication
def human_in_the_loop(state: state) -> Command[Literal["generate_report", "text2sql"]]:
    """
    HITL: user reviews fetched data, then either
      - approve + pick template + add emphasis/context notes  -> generate_report
      - requery + explain what was wrong                      -> text2sql

    Pauses the graph via interrupt(), surfacing the SQL/data/verdict so a UI
    (or any caller) can render Screen 2 before resuming with the user's decision.
    """
    # bring the important data display to the screen from previous node 
    response = interrupt({
        "sql": state.get("output_text2SQL"),
        "data": state.get("execute_sql"),
        "execute_error": state.get("execute_error"),
        "is_correct": state.get("is_correct_verify_correctness"),
        "detail": state.get("detail_verify_correctness"),
    })

    action = (response.get("action") or "").strip().lower()

    if action == "approve":
        # pick which of the 3 templates to render this report as
        report_type = (response.get("report_type") or "").strip().lower()
        if report_type not in VALID_TEMPLATES:
            report_type = "generic"  # fallback default if caller sent something invalid
        notes = (response.get("notes") or "").strip()
        return Command(
            goto="generate_report", # return to next node #
            update={
                "hitl_action": "approve",
                "report_type": report_type, # which template generate_report / html_details will use
                "human_notes": notes, # add more additional details and context of SQL data let LLM know
            },
        )

    # action == "requery" — read requery_feedback
    feedback = (response.get("feedback") or "").strip()
    return Command(
        goto="text2sql", # return to frist node #
        update={
            "hitl_action": "requery",
            "requery_feedback": feedback, # get feedback to refine actual user needed
        },
    )

# UNIT TEST ------------------------------------------------------------------------------------
if __name__ == "__main__":
    # minimal graph to exercise the interrupt()/resume contract in isolation.
    # generate_report/text2sql are stand-ins so Command(goto=...) has a valid target;
    # the real graph (graph.py) wires the actual nodes.
    from langgraph.graph import StateGraph, START, END
    from langgraph.checkpoint.memory import InMemorySaver

    builder = StateGraph(state)
    builder.add_node("human_in_the_loop", human_in_the_loop)
    builder.add_node("generate_report", lambda s: {})
    builder.add_node("text2sql", lambda s: {})
    builder.add_edge(START, "human_in_the_loop")
    builder.add_edge("generate_report", END)
    builder.add_edge("text2sql", END)
    test_graph = builder.compile(checkpointer=InMemorySaver())

    config = {"configurable": {"thread_id": "smoke-test-hitl"}}
    seed_state = {
        "output_text2SQL": "SELECT customernumber, customername, country FROM customers LIMIT 5;",
        "execute_sql": [(103, 'Atelier graphique', 'FR'), (112, 'Signal Gift Stores', 'US'),
                        (114, 'Australian Collectors, Co.', 'AU'), (119, 'La Rochelle Gifts', 'FR'),
                        (121, 'Baane Mini Imports', 'NO')],
        "is_correct_verify_correctness": True,
        "detail_verify_correctness": "First 5 customer orders in 2004 by order number.",
    }

    result = test_graph.invoke(seed_state, config=config)
    print("Interrupt payload:", result.get("__interrupt__"))

    resumed = test_graph.invoke(
        Command(resume={"action": "approve", "report_type": "customer", "notes": "test note"}),
        config=config,
    )
    print("\nResumed state:", resumed)
