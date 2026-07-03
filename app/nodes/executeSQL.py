from models.states import state
from db import engine
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

def executeSQLNode(state: state) -> dict:
    """This function implement execute SQL syntax from outpute generated getting into actual database Postgresql locate on pgAdmin and return the result back to user"""

    sql_query = state.get("output_text2SQL")

    # pool connection always working as 1 time per call [open once -> fetch -> close port connection]
    try:
        with engine.connect() as connection:
            result = connection.execute(text(sql_query))
            # Fetch all rows while the connection is still open, then it's
            # released back to the pool as soon as this block exits.
            rows = result.fetchall()
    except SQLAlchemyError as error:
        print(f"The error from SQL execution: {error}")
        return {"rows": [], "row_count": 0, "sql_query": sql_query, "error": str(error)}

    result_execute_sql = rows
    state['execute_sql'] = result_execute_sql     # get the result after fetch query

    return {"execute_sql": result_execute_sql, "len_execute_query": len(result_execute_sql), "sql_query": sql_query, "error": None}


# test standalone function #
# if __name__ == "__main__":
#     result = executeSQLNode({"output_text2SQL": "SELECT COUNT(*) FROM offices"})
#     print(result)

# Test function incorporate with each other (wired to text2sql) #
if __name__ == "__main__":
    from nodes.text2sql import Text2SQLNode

    text2sql_result = Text2SQLNode({"user_input": "generate report for number of offices in the database and their locations"})
    result = executeSQLNode({"output_text2SQL": text2sql_result["output_sql"]})
    print(f"Generated SQL: {text2sql_result['output_sql']}")
    print(f"Result number of offices: {result['rows']}")
    print(f"Result number of displayed rows: {result['row_count']}")