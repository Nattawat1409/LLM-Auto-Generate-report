from typing import Literal

from app.models.states import state
from app.db import engine
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from langgraph.types import Command

# how many times we let text2sql fix its own invalid SQL before giving up
MAX_SQL_RETRIES = 2


def executeSQLNode(state: state) -> Command[Literal["verify_correctness", "text2sql"]]:
    """Execute the generated SQL against Postgres and route based on the result.

    - success        -> verify_correctness (with the fetched rows)
    - SQL failed and retries left -> text2sql, feeding the DB error back so the
      LLM can rewrite its own query (self-correction loop)
    - SQL failed and retries exhausted -> verify_correctness, carrying the error
      so it is reported as a failure instead of being mistaken for "0 rows".
    """

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
        retries = state.get("sql_retry_count") or 0

        if retries < MAX_SQL_RETRIES:
            # hand the DB error + the broken SQL back to text2sql so it can fix itself
            return Command(
                goto="text2sql",
                update={
                    "execute_sql": None,
                    "execute_error": str(error),
                    "sql_retry_count": retries + 1,
                    "requery_feedback": (
                        f"The previous SQL failed with this PostgreSQL error:\n{error}\n\n"
                        f"The invalid SQL was:\n{sql_query}\n\n"
                        "Rewrite it as valid PostgreSQL that fixes this specific error. "
                        "Keep the same intent."
                    ),
                },
            )

        # out of retries — let verify_correctness report the failure honestly
        return Command(
            goto="verify_correctness",
            update={"execute_sql": None, "execute_error": str(error)},
        )

    # success — clear any stale retry feedback so it doesn't leak into a later requery
    return Command(
        goto="verify_correctness",
        update={"execute_sql": rows, "execute_error": None, "requery_feedback": ""},
    )


# test standalone function #
# if __name__ == "__main__":
#     result = executeSQLNode({"output_text2SQL": "SELECT COUNT(*) FROM offices"})
#     print(result)

# Test function incorporate with each other (wired to text2sql) #
if __name__ == "__main__":
    from app.nodes.text2sql import Text2SQLNode

    text2sql_result = Text2SQLNode({"user_input": "generate report for number of offices in the database and their locations"})
    result = executeSQLNode({"output_text2SQL": text2sql_result["output_text2SQL"]})
    print(f"Generated SQL: {text2sql_result['output_text2SQL']}")
    print(f"Result rows: {result['execute_sql']}")
    print(f"Result row count: {len(result['execute_sql'])}")