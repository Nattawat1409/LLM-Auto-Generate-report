from app.db.schema import get_schema_text
from app.llm.client import llm
from app.models import state
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

# define the structured output model for the LLM to convert SQL query
class Text2SQLOutput(BaseModel):
    question: str = Field(description="The natural language question convert to SQL.")
    output_sql: str = Field(description="The generated correctSQL query from the natural language question.")

# to update new specific value of temperature by no affect llm.client.py
sql_llm = llm.model_copy(update={"temperature": 0})             # make it deterministic
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
                "   ORDER BY outstanding_balance DESC;\n\n"

                # sales-report rule: revenue alone leaves the report's qty/orders columns blank
                "Rule: For SALES / revenue questions, NEVER return revenue by itself. For every "
                "grouping (product line, product, month, sales rep) also return the quantity sold "
                "(SUM(quantityordered)) and the order count (COUNT(DISTINCT ordernumber)) next to the "
                "revenue, and for top products also return the product's product line. This lets the "
                "sales report fill its 'quantity'/'orders'/'product line' columns instead of leaving "
                "them blank.\n\n"

                "Q: give me a sales report / sales performance overview\n"
                "A: WITH line_items AS (\n"
                "     SELECT o.ordernumber, o.orderdate, p.productname, pl.productline,\n"
                "            od.quantityordered, od.quantityordered * od.priceeach AS line_revenue,\n"
                "            e.firstname || ' ' || e.lastname AS rep_name, ofc.city AS office_city\n"
                "     FROM orders o\n"
                "     JOIN orderdetails od ON od.ordernumber = o.ordernumber\n"
                "     JOIN products p ON p.productcode = od.productcode\n"
                "     JOIN productlines pl ON pl.productline = p.productline\n"
                "     JOIN customers c ON c.customernumber = o.customernumber\n"
                "     LEFT JOIN employees e ON e.employeenumber = c.salesrepemployeenumber\n"
                "     LEFT JOIN offices ofc ON ofc.officecode = e.officecode\n"
                "   )\n"
                "   SELECT 'Total' AS section, NULL AS name, NULL AS product_line,\n"
                "          SUM(line_revenue) AS revenue, SUM(quantityordered) AS quantity,\n"
                "          COUNT(DISTINCT ordernumber) AS orders, 1 AS sort_key\n"
                "   FROM line_items\n"
                "   UNION ALL\n"
                "   SELECT 'Monthly', TO_CHAR(orderdate, 'YYYY-MM'), NULL,\n"
                "          SUM(line_revenue), SUM(quantityordered), COUNT(DISTINCT ordernumber), 2\n"
                "   FROM line_items GROUP BY TO_CHAR(orderdate, 'YYYY-MM')\n"
                "   UNION ALL\n"
                "   SELECT 'By Product Line', productline, NULL,\n"
                "          SUM(line_revenue), SUM(quantityordered), COUNT(DISTINCT ordernumber), 3\n"
                "   FROM line_items GROUP BY productline\n"
                "   UNION ALL\n"
                "   SELECT 'Top Products', productname, productline,\n"
                "          SUM(line_revenue), SUM(quantityordered), COUNT(DISTINCT ordernumber), 4\n"
                "   FROM line_items GROUP BY productname, productline\n"
                "   UNION ALL\n"
                "   SELECT 'By Sales Rep', rep_name, office_city,\n"
                "          SUM(line_revenue), SUM(quantityordered), COUNT(DISTINCT ordernumber), 5\n"
                "   FROM line_items GROUP BY rep_name, office_city\n"
                "   ORDER BY sort_key, revenue DESC;\n\n"

                # collection/payment rule: the report needs billed AND paid separately, not just the net
                "Rule: For COLLECTION / PAYMENT / outstanding-balance reports, return for each customer "
                "the total billed, the total paid, AND the outstanding balance as THREE SEPARATE columns "
                "(not just the net balance). Aggregate billed and paid in their own CTEs first, then join "
                "them (per the row-explosion rule above). Return every customer that has orders (do not "
                "filter to balance > 0) so the report's 'ยอดตั้งบิลรวม' (total billed) and 'เก็บได้แล้ว' "
                "(collected) KPIs and columns are complete.\n\n"

                "Q: which customers still owe us money? show billed vs paid and outstanding balance\n"
                "A: WITH billed AS (\n"
                "     SELECT o.customernumber, SUM(od.quantityordered * od.priceeach) AS total_billed\n"
                "     FROM orders o JOIN orderdetails od ON od.ordernumber = o.ordernumber\n"
                "     GROUP BY o.customernumber\n"
                "   ),\n"
                "   paid AS (\n"
                "     SELECT customernumber, SUM(amount) AS total_paid\n"
                "     FROM payments GROUP BY customernumber\n"
                "   )\n"
                "   SELECT c.customername,\n"
                "          b.total_billed,\n"
                "          COALESCE(p.total_paid, 0) AS total_paid,\n"
                "          b.total_billed - COALESCE(p.total_paid, 0) AS outstanding_balance\n"
                "   FROM customers c\n"
                "   JOIN billed b ON b.customernumber = c.customernumber\n"
                "   LEFT JOIN paid p ON p.customernumber = c.customernumber\n"
                "   ORDER BY outstanding_balance DESC;"
            )),
            HumanMessage(content=human_content),
        ])

    # return key must match the state schema so downstream nodes read state["output_text2SQL"]
    return {"output_text2SQL": response.output_sql}



# test standalone function #
if __name__ == "__main__":
    from app.nodes.schema import schema
    qusetion = "List customers who have exceeded their credit limit based on total orders placed, showing how much over the limit they are."
    read_question = schema({"user_input": qusetion})
    result = Text2SQLNode({
        "user_input": qusetion,
        "is_question_relate": read_question 
        })

    # result = Text2SQLNode({"user_input": "how many number of offices are there in the database?"})
    print(f"Generated SQL: \n{result['output_text2SQL']}")