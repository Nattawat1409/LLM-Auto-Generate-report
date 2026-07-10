"""LangGraph pipeline wiring all nodes together.

Flow (see docs/graph_draft.md):
    START -> schema (gate: is question DB-related?)
        - not data-related  -> END
        - data-related      -> text2sql -> execute_sql -> verify_correctness
                               -> human_in_the_loop
                                   - re-query -> text2sql
                                   - approve  -> generate_report -> html_details
                                                 -> generate_pdf -> personalize
                                                     - not satisfy -> generate_report
                                                     - satisfy      -> END

Three nodes route themselves by returning a `Command(goto=...)`:
    schema, human_in_the_loop, personalize
The rest are linear and wired with static edges.
"""
from langgraph.graph import StateGraph, START, END

from models import state
from nodes.schema import schema
from nodes.text2sql import Text2SQLNode
from nodes.executeSQL import executeSQLNode
from nodes.verify_correctness import verifyCorrectnessNode
from nodes.human_in_the_loop import human_in_the_loop
from nodes.generate_report import generateReportNode
from nodes.html_details import html_details
from nodes.generate_pdf import generate_pdf
from nodes.personalize import personalize

from pathlib import Path # import current path of dir 


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

    # schema routes itself: -> "text2sql" or END (Command)

    # linear data path
    builder.add_edge("text2sql", "execute_sql")
    # execute_sql routes itself: -> "verify_correctness" (ok / exhausted) or
    #   "text2sql" (retry the invalid SQL) via Command
    builder.add_edge("verify_correctness", "human_in_the_loop")

    # human_in_the_loop routes itself: -> "generate_report" or "text2sql" (Command)

    # linear report path
    builder.add_edge("generate_report", "html_details")
    builder.add_edge("html_details", "generate_pdf")
    builder.add_edge("generate_pdf", "personalize")

    # personalize routes itself: -> "generate_report" or END (Command)
    builder.add_edge("personalize",END)
    
    return builder.compile()


graph = build_graph() # build graph 


if __name__ == "__main__":
    user_question = input("Input your question about classic model schema : ")

    #pass the user question via this graph — invoke expects a dict matching the state schema
    final_state = graph.invoke({"user_input": user_question})
    print(final_state)
