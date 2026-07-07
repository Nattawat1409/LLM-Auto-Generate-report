from models.states import state
from db.schema import get_schema_text
from llm.client import llm
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field



# define the structured output model for the LLM to judge the result
class VerifyCorrectnessOutput(BaseModel):
    is_correct: bool = Field(description="Whether the fetched data correctly and sufficiently answers the user's question.")
    reasoning: str = Field(description="Short explanation of why the data does or does not answer the question.")
    detail_report: str = Field(description="Response for Report format explanation of the data and the result from the query, including any discrepancies or issues found, formatted as a report for documentation purposes.")

structured_verify_llm = llm.with_structured_output(VerifyCorrectnessOutput)

def verifyCorrectnessNode(state: state) -> dict:
    """
    Sanity-checks the execute_sql result before it goes to human_in_the_loop:
    first deterministic checks (execution error, zero rows), then an LLM check
    on whether the returned data actually answers the original question.
    """
    # get user question
    user_question = state.get("user_input")
    sql_output = state.get("output_text2SQL")
    execute_sql_result = state.get("execute_sql")

    #details roughtly schema 
    schema_text = get_schema_text()

    response = structured_verify_llm.invoke([
        SystemMessage(content=(
            "You are an expert in SQL query result verification. Your task is to determine whether the provided SQL query result correctly and sufficiently answers the user's question.\n"
            "You will be given the following information:\n"
            f"User's question: {user_question}\n"
            f"Generated SQL query: {sql_output}\n"
            f"SQL query result: {execute_sql_result}\n"
            f"Database schema: {schema_text}\n\n"
            "Please provide a structured response indicating whether the result is correct, along with reasoning and detailed explanation as a report for document task to see the changing of the data and the result from the query.\n"
        )),
        HumanMessage(content=user_question),
    ])

    # return keys must match the state schema (models/states/state.py) so the
    # next nodes read from state.get(...)
    return {
        "is_correct_verify_correctness": response.is_correct,   # bool: is verify true or false
        "detail_verify_correctness": response.detail_report,    # detail for report / html_details
    }

# test standalone function (wire 3 function corporate together) #
if __name__ == "__main__":
    from nodes.text2sql import Text2SQLNode # from other module
    from nodes.executeSQL import executeSQLNode # from other module
    
    user_input = "generate report for number of offices in the database and their locations" # test it for i can generate the report 
    text2sql_result = Text2SQLNode({"user_input": user_input})
    exec_result = executeSQLNode({"output_text2SQL": text2sql_result["output_sql"]}) # return dict : output_sql
    verify_result = verifyCorrectnessNode({
        "user_input": user_input,
        **text2sql_result,
        **exec_result,
    })
    
    print(verify_result)
