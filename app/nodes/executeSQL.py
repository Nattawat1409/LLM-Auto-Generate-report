from models.states import state
from db import engine
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from langgraph.graph import END


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
        # surface the error so downstream can tell "query FAILED" from "0 rows found"
        return {"execute_sql": None , "execute_error": str(error)}

    # return keys match the state schema (models/states/state.py)
    return {"execute_sql": rows, "execute_error": None}


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
    print(f"Result rows: {result['execute_sql']}")
    print(f"Result row count: {len(result['execute_sql'])}")