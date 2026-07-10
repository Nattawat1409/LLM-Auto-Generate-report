from db.schema import get_schema_text
from llm.client import llm
from models import state
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

# define the structured output model for the LLM to convert SQL query
class Text2SQLOutput(BaseModel):
    question: str = Field(description="The natural language question convert to SQL.")
    output_sql: str = Field(description="The generated correctSQL query from the natural language question.")

# to update new specific value of temperature by no affect llm.client.py
sql_llm = llm.model_copy(update={"temperature": 0}) # deterministic response without randomness
structured_answer_llm = sql_llm.with_structured_output(Text2SQLOutput)

# function to convert user question into SQL query using LLM
def Text2SQLNode(state: state) -> dict:
    """
    this function implement text to sql by getting user question and convert into correct approach SQL query to reseponse back
    """
    is_related = state.get('is_question_relate') # get return value from "schema" node
    
    
    if is_related:
        human_content = state['user_input']
        schema_text = get_schema_text()  # let llm read schema if question related

        # in case human not satisfy 
        get_human_feedback = state.get("requery_feedback","") # default value = none 
        
        if get_human_feedback:
            human_content += (f"\n\nThe previous SQL did not match the intent. "f"Re-query following this feedback:\n{get_human_feedback}")


        # prompt tell LLM applied few-shot and inject schema
        response = structured_answer_llm.invoke([
            SystemMessage(content=(
                "You're the expert of SQL query generator, you will help me to generate SQL query from my question.\n"
                "The database is PostgreSQL vesion 16.13. Use correct syntax and functions ONLY. and must support to window function\n"
                "- NEVER use SQLite/MySQL functions like STRFTIME, DATE_FORMAT, or YEAR().\n"
                "Use only the following real database schema — do not assume any other tables or columns:\n"
                f"{schema_text}\n\n"
                "Rule: never use SELECT COUNT(*). Always count by the table's unique identifier column instead.\n\n"
                
                #add additional rules 
                "Rule: NEVER join two one-to-many tables directly in the same query when aggregating both "
                "(e.g. a customer's orderdetails AND payments — both join back to customers via orders/customernumber). "
                "Joining them together multiplies rows (row explosion) and produces WRONG SUM()/COUNT() results, "
                "even though the SQL runs without error.\n"
                "Instead: aggregate each one-to-many relationship in its own CTE first (grouped down to one row "
                "per entity), THEN join the already-aggregated CTEs together.\n\n"

                #add more example
                "Examples:\n"
                "Q: how many employees are there?\n"
                "A: SELECT COUNT(employeenumber) FROM employees;\n\n"
                "Q: how many customers do we have?\n"
                "A: SELECT COUNT(customernumber) FROM customers;\n\n"
                "Q: how many orders have been placed?\n"
                "A: SELECT COUNT(ordernumber) FROM orders;\n\n"

                # add more few shot
                "Q: which customers have outstanding balance (total billed exceeds total paid)?\n"
                "A: WITH billed AS (\n"
                "     SELECT o.customernumber, SUM(od.quantityordered * od.priceeach) AS total_billed\n"
                "     FROM orders o JOIN orderdetails od ON od.ordernumber = o.ordernumber\n"
                "     GROUP BY o.customernumber\n"
                "   ),\n"
                "   paid AS (\n"
                "     SELECT customernumber, SUM(amount) AS total_paid\n"
                "     FROM payments GROUP BY customernumber\n"
                "   )\n"
                "   SELECT c.customername, b.total_billed - COALESCE(p.total_paid, 0) AS outstanding_balance\n"
                "   FROM customers c\n"
                "   JOIN billed b ON b.customernumber = c.customernumber\n"
                "   LEFT JOIN paid p ON p.customernumber = c.customernumber\n"
                "   WHERE b.total_billed - COALESCE(p.total_paid, 0) > 0\n"
                "   ORDER BY outstanding_balance DESC;"
            )),
            HumanMessage(content=human_content),
        ])

    # return key must match the state schema so downstream nodes read state["output_text2SQL"]
    return {"output_text2SQL": response.output_sql}



# test standalone function #
if __name__ == "__main__":
    from nodes.schema import schema
    qusetion = "List customers who have exceeded their credit limit based on total orders placed, showing how much over the limit they are."
    read_question = schema({"user_input": qusetion})
    result = Text2SQLNode({
        "user_input": qusetion,
        "is_question_relate": read_question 
        })

    # result = Text2SQLNode({"user_input": "how many number of offices are there in the database?"})
    print(f"Generated SQL: \n{result['output_text2SQL']}")