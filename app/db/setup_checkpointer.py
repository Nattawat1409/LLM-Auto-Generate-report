"""One-time setup: create langgraph's PostgresSaver checkpoint tables.

Run manually once per environment (NOT on every app/API startup):
    uv run python -m app.db.setup_checkpointer
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from psycopg import Connection
from psycopg.rows import dict_row
from langgraph.checkpoint.postgres import PostgresSaver

load_dotenv(Path(__file__).resolve().parents[1] / ".env")  # app/.env,


def main() -> None:
    with Connection.connect(
        os.environ["CHECKPOINT_DATABASE_URL"],
        autocommit=True,
        prepare_threshold=0,
        row_factory=dict_row,
    ) as conn:
        PostgresSaver(conn).setup()
    print("Checkpoint tables created/verified.")


if __name__ == "__main__":
    main()
