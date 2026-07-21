from app.db.schema import get_schema_text
from app.models import state
from langchain_core.messages import HumanMessage, SystemMessage
from app.llm import llm
from langgraph.types import Command
from langgraph.graph import END
from typing import Literal
from pydantic import BaseModel, Field


class SchemaAnswer(BaseModel):
    answer: bool = Field(description="True if the question can be answered from the DB schema, else False")
    
    # if question doesn't exist within database -> END node 
    # otherwise goto -> text2SQL (if data is exist within database)

structured_answer_llm = llm.with_structured_output(SchemaAnswer)

def schema(state:state)-> Command[Literal["text2sql", "__end__"]]:
    """Gate before text2sql: is the user's question answerable from the DB schema?"""
    user_question = state.get("user_input")
    schema_structure = get_schema_text()

    response = structured_answer_llm.invoke([
        SystemMessage(content=(
            "Decide whether the user's question can be answered using ONLY this database schema."
            "Answer True if it can, False if it asks for data not present in the schema.\n"
            f"here is the real database schema — do not assume any other tables or columns:\n {schema_structure}"
        )),
        HumanMessage(content=user_question),
    ])
    
    # define path 
    if response.answer:
        goto_path = "text2sql"
    else:
        goto_path = END

    return Command(
        goto=goto_path,
        update={"is_question_relate": bool(response.answer)},
    )

# test standalone function #
if __name__ == "__main__":
    user_input = input("Input your question : ")
    result = schema({"user_input": user_input})     # schema() needs a state dict, not a bare string
    print("is_question_relate:", result.update["is_question_relate"])
    print("goto:", result.goto)


