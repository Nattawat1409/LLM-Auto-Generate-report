import csv
import io
from pathlib import Path

from sqlalchemy import inspect

from app.db.engine import engine

# get real schema text from the actual database #
def get_schema_text() -> str:
    inspector = inspect(engine)
    lines = []
    for table_name in inspector.get_table_names():
        columns = inspector.get_columns(table_name)
        col_defs = ", ".join(f"{col['name']} {col['type']}" for col in columns)
        lines.append(f"{table_name}({col_defs})")
    return "\n".join(lines)



# test standalone function #
if __name__ == "__main__":
    print("=== schema text ===")
    print(get_schema_text())
    print("\n=== schema csv ===")
    # write to db/schema.csv next to this file
    out = Path(__file__).resolve().parent / "schema.csv"
    test_path = Path(__file__).resolve().parent
    print(f"here is the path : {test_path}")
