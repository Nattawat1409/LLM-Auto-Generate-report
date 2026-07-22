"""LangGraph pipeline wiring all nodes together.

Flow (see docs/graph_draft.md):
    START -> schema (gate: is question DB-related?)
        - not data-related  -> END
        - data-related      -> text2sql -> execute_sql -> verify_correctness
                               -> human_in_the_loop
                                   - re-query -> text2sql
                                   - approve  -> generate_report -> html_details (main flows)
                                                 -> generate_pdf -> personalize
                                                     - free-text = change content / content + style -> generate_report  (skip html details node)
                                                     - free-text = change style only -> html_details
                                                     - not satisfy -> generate_report
                                                     - satisfy      -> END

Three nodes route themselves by returning a `Command(goto=...)`:
    schema, human_in_the_loop, personalize
The rest are linear and wired with static edges.
"""
import os
from pathlib import Path
from dotenv import load_dotenv
from psycopg import Connection
from psycopg.rows import dict_row

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver

from app.models import state
from app.nodes.schema import schema
from app.nodes.text2sql import Text2SQLNode
from app.nodes.executeSQL import executeSQLNode
from app.nodes.verify_correctness import verifyCorrectnessNode
from app.nodes.human_in_the_loop import human_in_the_loop
from app.nodes.generate_report import generateReportNode
from app.nodes.html_details import html_details
from app.nodes.generate_pdf import generate_pdf
from app.nodes.personalize import personalize

# app/.env, regardless of cwd (see app/db/engine.py, app/llm/client.py for the same pattern)
load_dotenv(Path(__file__).resolve().parent / ".env")


def build_graph():
    builder = StateGraph(state)

    # register nodes — names MUST match the goto targets in the Command nodes
    builder.add_node("schema", schema)
    builder.add_node("text2sql", Text2SQLNode)
    builder.add_node("execute_sql", executeSQLNode)
    builder.add_node("verify_correctness", verifyCorrectnessNode)
    builder.add_node("human_in_the_loop", human_in_the_loop)
    builder.add_node("generate_report", generateReportNode)
    builder.add_node("html_details", html_details)
    builder.add_node("generate_pdf", generate_pdf)
    builder.add_node("personalize", personalize)

    # entry
    builder.add_edge(START, "schema")
    builder.add_edge("text2sql", "execute_sql")
    builder.add_edge("verify_correctness", "human_in_the_loop")

    builder.add_edge("generate_report", "html_details")
    builder.add_edge("html_details", "generate_pdf")
    builder.add_edge("generate_pdf", "personalize")

    conn = Connection.connect(
        os.environ["CHECKPOINT_DATABASE_URL"],
        autocommit=True,
        prepare_threshold=0,
        row_factory=dict_row,
    )
    checkpointer = PostgresSaver(conn) # record as check pointer use persistent memory storage

    return builder.compile(checkpointer=checkpointer)


graph = build_graph() # build graph


def close_checkpointer() -> None:
    """Close the long-lived Postgres connection backing the checkpointer.

    Called from api/services/workflow.py on FastAPI shutdown — graph.py itself
    has no lifespan hook to run this automatically.
    """
    graph.checkpointer.conn.close()


#____TEST FLOW FULL GRAPH____ #
if __name__ == "__main__":
    import uuid
    from langgraph.types import Command

    user_question = input("Input your question about classic model schema : ")
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    # pass the user question via this graph — invoke expects a dict matching the state schema
    result = graph.invoke({"user_input": user_question}, config=config)

    # walk interrupts from the CLI: print the payload, ask for the resume dict on stdin
    while "__interrupt__" in result:
        payload = result["__interrupt__"][0].value
        print("\n--- paused ---")
        print(payload)

        if "options" in payload:  # personalize interrupt
            print("\n[1-3] pick an option, [4] describe your own, [5] accept")
            choice = input("Enter your choice (1-5): ").strip()
            feedback = ""
            if choice == "4":
                feedback = input("Describe your preference: ").strip()
            resume = {"choice": choice, "feedback": feedback}
        else:  # human_in_the_loop interrupt
            action = input("\nApprove or Requery? [approve/requery]: ").strip().lower()
            if action == "approve":
                report_type = input("Pick report template (generic/sales/customer/collection_payment): ").strip().lower()
                notes = input("Emphasis / context to include in report (Enter to skip): ").strip()
                resume = {"action": "approve", "report_type": report_type, "notes": notes}
            else:
                feedback = input("What was wrong? Describe how to re-query: ").strip()
                resume = {"action": "requery", "feedback": feedback}

        result = graph.invoke(Command(resume=resume), config=config)

    print("\n--- done ---")
    print(result)