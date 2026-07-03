from db.schema import get_schema_text
from llm.client import llm
from models.states import state
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

# define the structured output model for the LLM to convert SQL query
class Text2SQLOutput(BaseModel):
    question: str = Field(description="The natural language question to convert to SQL.")
    output_sql: str = Field(description="The generated correctSQL query from the natural language question.")

structured_answer_llm = llm.with_structured_output(Text2SQLOutput)

# function to convert user question into SQL query using LLM
def Text2SQLNode(state: state) -> dict:
    """
    this function implement text to sql by getting user question and convert into correct approach SQL query to reseponse back
    """

    question = state["user_input"]  # question from user input
    schema_text = get_schema_text()

    # prompt tell LLM applied faw shout and inject S
    response = structured_answer_llm.invoke([
        SystemMessage(content=(
            "You're the expert of SQL query generator, you will help me to generate SQL query from my question.\n"
            "Use only the following real database schema — do not assume any other tables or columns:\n"
            f"{schema_text}\n\n"
            "Rule: never use SELECT COUNT(*). Always count by the table's unique identifier column instead.\n\n"
            "Examples:\n"
            "Q: how many employees are there?\n"
            "A: SELECT COUNT(employeenumber) FROM employees;\n\n"
            "Q: how many customers do we have?\n"
            "A: SELECT COUNT(customernumber) FROM customers;\n\n"
            "Q: how many orders have been placed?\n"
            "A: SELECT COUNT(ordernumber) FROM orders;"
        )),
        HumanMessage(content=question),
    ])

    output_text2SQL = response.output_sql
    state["output_text2SQL"] = output_text2SQL  #update value of output_text2SQL in state.py
    return {"question": question, "output_sql": output_text2SQL}



# test standalone function #
if __name__ == "__main__":
    result = Text2SQLNode({"user_input": "how many number of offices are there in the database?"})
    print(f"Generated SQL: {result['output_sql']}")
    print(f"Actual Node Answer: {result['actual_node_answer']}")